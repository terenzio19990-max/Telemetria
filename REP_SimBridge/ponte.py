#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REP SIM BRIDGE — ponte tra i simulatori di guida e Race Engineer Pro.

Legge i dati che i giochi mettono a disposizione dei programmi esterni e li
manda, già messi in una forma unica, a:
  - Race Engineer Pro (pagina 🎮 Sim racing), sullo stesso PC o su un altro;
  - telefoni e tablet della stessa rete Wi-Fi, che aprono una pagina con il
    cruscotto live (serve quando non c'è un secondo schermo).

Giochi:  Assetto Corsa · Assetto Corsa Competizione · Assetto Corsa EVO ·
         iRacing · Le Mans Ultimate · rFactor 2 (con il suo plugin) ·
         Automobilista 2 · Forza Motorsport (Data Out UDP)

Solo libreria standard di Python 3.8+: niente da installare oltre a Python.
Il ponte LEGGE e basta: non scrive mai nella memoria dei giochi.

Avvio:   python ponte.py            (oppure doppio clic su AVVIA_PONTE.bat)
Opzioni: --porta 8977   porta per il programma e i telefoni
         --solo-pc      accetta collegamenti solo da questo PC (niente telefoni)
         --forza-porta 5300   porta UDP su cui Forza manda i dati
         --f1-porta 20777     porta UDP su cui F1 25 manda i dati
         --registra FILE      salva i dati grezzi (per segnalare un problema)
         --configura-acc      prepara ACC a mandare la classifica completa
         --demo               nessun gioco: simula una sessione per provare tutto
         --diagnosi [FILE]    scrive il controllo dei dati letti (da mandare se qualcosa non torna)
         --cartella-setup DIR dove stanno i setup se il ponte non li trova da solo
         --cartella-giri DIR  dove archiviare i giri (di serie: Documenti\\RaceEngineerPro\\giri_sim)
         --senza-archivio     non scrive i giri su disco
                              (Le Mans Ultimate: ...\\UserData\\player\\Settings)
"""
import base64, ctypes, glob, hashlib, json, math, os, re, socket, struct, subprocess, sys, threading, time

VERSIONE = '2.1'
DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import strutture as ST

IS_WIN = os.name == 'nt'
for _s in (sys.stdout, sys.stderr):          # console di Windows: mai fermarsi per un carattere
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass
ORA = time.monotonic
STERZO_ACC = 540.0     # ACC dà lo sterzo −1…1: per i gradi si usa la rotazione tipica GT3 (540°)


def ms_ora():
    return int(time.time() * 1000)


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# ════════════════════════════════════════════════════════════════════════════
#  MEMORIA CONDIVISA (Windows). Si APRE soltanto: se il gioco non l'ha creata
#  non la si crea al suo posto (mmap di Python lo farebbe, e il gioco poi
#  potrebbe trovarsi una memoria della misura sbagliata).
# ════════════════════════════════════════════════════════════════════════════
MAPPE_FINTE = {}          # per le prove: nome → bytearray


class Mappa:
    FILE_MAP_READ = 0x0004

    def __init__(self, nome):
        self.nome = nome
        self.h = self.addr = None
        self.size = 0
        if nome in MAPPE_FINTE:
            self.finta = MAPPE_FINTE[nome]
            self.size = len(self.finta)
            return
        self.finta = None
        if not IS_WIN:
            raise OSError('memoria condivisa disponibile solo su Windows')
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenFileMappingW.restype = ctypes.c_void_p
        k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
        k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.k32 = k32
        h = k32.OpenFileMappingW(self.FILE_MAP_READ, 0, nome)
        if not h:
            raise OSError('non presente: ' + nome)
        addr = k32.MapViewOfFile(h, self.FILE_MAP_READ, 0, 0, 0)
        if not addr:
            k32.CloseHandle(h)
            raise OSError('non leggibile: ' + nome)
        self.h, self.addr = h, addr
        self.size = self._dimensione()

    def _dimensione(self):
        class MBI(ctypes.Structure):
            _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                        ('AllocationProtect', ctypes.c_uint32), ('PartitionId', ctypes.c_uint16),
                        ('RegionSize', ctypes.c_size_t), ('State', ctypes.c_uint32), ('Protect', ctypes.c_uint32),
                        ('Type', ctypes.c_uint32)]
        m = MBI()
        self.k32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        if self.k32.VirtualQuery(ctypes.c_void_p(self.addr), ctypes.byref(m), ctypes.sizeof(m)):
            return int(m.RegionSize)
        return 0

    def leggi(self, n=None, da=0):
        n = self.size - da if n is None else min(n, self.size - da)
        if n <= 0:
            return b''
        if self.finta is not None:
            return bytes(self.finta[da:da + n])
        return ctypes.string_at(self.addr + da, n)

    def chiudi(self):
        if self.finta is None and self.addr:
            try:
                self.k32.UnmapViewOfFile(self.addr)
                self.k32.CloseHandle(self.h)
            except Exception:
                pass
        self.addr = self.h = None


def leggi_struct(mappa, tipo, da=0):
    """Legge una struttura; se la memoria è più corta, completa con zeri."""
    n = ctypes.sizeof(tipo)
    b = mappa.leggi(n, da)
    if len(b) < n:
        b = b + b'\0' * (n - len(b))
    return tipo.from_buffer_copy(b)


def processi():
    """Nomi dei programmi in esecuzione (minuscoli). Solo Windows."""
    if 'PROCESSI_FINTI' in globals():
        return PROCESSI_FINTI
    if not IS_WIN:
        return set()
    try:
        out = subprocess.run(['tasklist', '/fo', 'csv', '/nh'], capture_output=True, text=True, timeout=5,
                             creationflags=0x08000000).stdout
        return {r.split('","')[0].strip('"').lower() for r in out.splitlines() if r}
    except Exception:
        return set()


def txt(v):
    """Stringa da campo C: char[] (bytes), uint16[] (wchar_t) o ubyte[]."""
    try:
        if isinstance(v, bytes):
            b = v.split(b'\0', 1)[0]
            try:
                return b.decode('utf-8').strip()          # LMU, ACC, AMS2: UTF-8
            except UnicodeDecodeError:
                return b.decode('latin-1', 'ignore').strip()   # giochi vecchi: latin-1 (o nome tagliato a metà di una lettera)
        a = list(v)
        if a and isinstance(a[0], int):
            if max(a + [0]) > 255 or ctypes.sizeof(v) == 2 * len(a):
                s = ''.join(chr(c) for c in a)
            else:
                s = bytes(a).decode('latin-1', 'ignore')
            return s.split('\0', 1)[0].strip()
    except Exception:
        pass
    return ''


def num(x, d=None):
    try:
        x = float(x)
        return x if math.isfinite(x) else d
    except Exception:
        return d


def r1(x, n=1):
    x = num(x)
    return None if x is None else round(x, n)


PSI_BAR = 0.0689476


def danni(corpo=None, motore=None, sosp=None, freni=None, aero=None, scala=1.0, grezzo=None):
    """Danni in una forma unica: ogni voce 0 (integra) … 1 (distrutta).
    'scala' serve ai giochi che non usano 0..1 (valore che vale «distrutto»)."""
    def n(x):
        if x is None:
            return None
        x = num(x, 0) / scala
        return round(max(0.0, min(1.0, x)), 3)
    d = {'body': n(corpo), 'engine': n(motore), 'aero': n(aero),
         'susp': [n(x) for x in sosp] if sosp else None, 'brakes': [n(x) for x in freni] if freni else None}
    if grezzo is not None:
        d['raw'] = [r1(x, 2) for x in grezzo]
    return d


# ════════════════════════════════════════════════════════════════════════════
#  CANALI ESTESI (ponte 2.0) — nel fotogramma sotto la chiave 'e'.
#  Stessi nomi per tutti i giochi; un canale che il gioco non dà manca.
#    sdeg  angolo del volante in gradi        sdegStima  1 se stimato (ACC)
#    tc tcMax tcCut tcCutMax tcSlip  abs absMax  map mapMax  mig migMax
#    arbF arbFMax arbR arbRMax  (barre regolabili dall'abitacolo: LMU)
#    tcA absA escA  interventi in questo istante (0/1)   lim  limitatore box
#    drs  0 no · 1 disponibile · 2 aperto
#    ers {soc 0..1, mode, modeMax, regen, kw, chg, ve energia virtuale 0..1, temp}
#    eng {wT, oT, oP, fP, boost, exT}
#    yaw °/s · roll, pitch ° · vG g · sus[4] mm · rh[2 o 4] mm
#    sr[4] slip ratio · sa[4] angolo di deriva ° · load[4] N · cam[4] ° · grip[4]
#    dfF dfR drag N · gapA gapB s (auto davanti / dietro) · lc lift&coast 0..1
#    mfd {fuel, set, p[4]}  cosa è impostato per il prossimo pit (ACC)
# ════════════════════════════════════════════════════════════════════════════
DEG = 57.29578


def pressione_bar(x):
    """Pressione gomma in bar, qualunque unità mandi il gioco: psi (20–35), kPa (130–250), bar (1–3)."""
    if x is None or x <= 0:
        return None
    if x > 60:
        return r1(x / 100.0, 3)          # kPa
    if x > 5:
        return r1(x * PSI_BAR, 3)        # psi
    return r1(x, 3)                      # già bar


def pulito(d):
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            v = pulito(v)
            if not v:
                continue
        if isinstance(v, list) and (not v or all(x is None for x in v)):
            continue
        out[k] = v
    return out


def listaNZ(a, fatt=1.0, n=1):
    """come lista, ma None se il gioco lascia il campo sempre a zero (in ACC alcuni campi «non usati»)"""
    try:
        return lista(a, fatt, n) if any(abs(x) > 1e-9 for x in a) else None
    except TypeError:
        return None


def lista(a, fatt=1.0, n=1, somma=0.0):
    try:
        return [r1(x * fatt + somma, n) if x is not None else None for x in a]
    except TypeError:
        return None


def livello(v, massimo=None):
    """Livelli dei menu (TC 3, ABS 2...): interi, None se il gioco dà 0/−1 per «non c'è»."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 and (massimo is None or massimo > 0 or v > 0) else None


# ════════════════════════════════════════════════════════════════════════════
#  BANDIERE E PENALITÀ — nel fotogramma: 'fl' e 'pen', uguali per tutti i giochi
#    fl  {f: green|yellow|dyellow|blue|white|black|bw|meatball|red|chequered|sc|fcy|none,
#         sett: [gialla nei settori 1..3], lastLap: 1 ultimo giro, motivo}
#    pen {tempo: s da scontare, tipo: testo, n: penalità ricevute, inc: incidenti,
#         tl: avvertimenti limiti pista, tlMax: al prossimo scatta la penalità}
# ════════════════════════════════════════════════════════════════════════════
BANDIERA_AC = {0: 'none', 1: 'blue', 2: 'yellow', 3: 'black', 4: 'white', 5: 'chequered', 6: 'bw'}
PENALITA_ACC = {1: 'Drive-through (taglio)', 2: 'Stop & go 10 s (taglio)', 3: 'Stop & go 20 s (taglio)', 4: 'Stop & go 30 s (taglio)',
                5: 'Squalifica (tagli)', 6: 'Giro migliore cancellato (taglio)', 7: 'Drive-through (velocità in corsia box)',
                8: 'Stop & go 10 s (velocità box)', 9: 'Stop & go 20 s (velocità box)', 10: 'Stop & go 30 s (velocità box)',
                11: 'Squalifica (velocità box)', 12: 'Giro migliore cancellato (velocità box)', 13: 'Squalifica: pit obbligatorio saltato',
                14: 'Tempo aggiunto a fine gara', 15: 'Squalifica: comportamento', 16: 'Squalifica: ingresso box', 17: 'Squalifica: uscita box',
                18: 'Squalifica: contromano', 19: 'Drive-through: turno pilota', 20: 'Squalifica: turno pilota', 21: 'Squalifica: limite turno pilota'}
BANDIERA_AMS2 = {0: 'none', 1: 'green', 2: 'blue', 3: 'white', 4: 'white', 5: 'red', 6: 'yellow', 7: 'dyellow', 8: 'bw', 9: 'meatball', 10: 'black', 11: 'chequered'}
FCY_RF = {1: 'Safety car in arrivo', 2: 'Corsia box chiusa', 3: 'Box aperti ai primi', 4: 'Box aperti', 5: 'Ultimo giro dietro la safety car', 6: 'Si riparte', 7: 'Gara sospesa'}


def bandiera_iracing(bits, auto=0):
    b = int(bits or 0) | int(auto or 0)
    if b & 0x10:
        f = 'red'
    elif b & 0x20000 or b & 0x10000:
        f = 'black'
    elif b & 0x100000:
        f = 'meatball'
    elif b & 0x1:
        f = 'chequered'
    elif b & (0x4000 | 0x8000):
        f = 'sc'
    elif b & 0x100:
        f = 'dyellow'
    elif b & (0x8 | 0x40):
        f = 'yellow'
    elif b & 0x20:
        f = 'blue'
    elif b & 0x2:
        f = 'white'
    elif b & (0x4 | 0x400):
        f = 'green'
    else:
        f = 'none'
    return {'f': f, 'lastLap': 1 if b & 0x2 else 0, 'motivo': 'detriti in pista' if b & 0x40 else None}


PIOGGIA_ACC = {0: 0.0, 1: 0.15, 2: 0.35, 3: 0.55, 4: 0.8, 5: 1.0}
GRIP_ACC = {0: ('green', 0.0), 1: ('fast', 0.0), 2: ('optimum', 0.0), 3: ('greasy', 0.1), 4: ('damp', 0.3), 5: ('wet', 0.6), 6: ('flooded', 1.0)}


# ════════════════════════════════════════════════════════════════════════════
#  GIRI: rileva la fine di ogni giro, i settori, la benzina usata e registra
#  la traccia del giro (velocità, gas, freno… a distanza fissa) per l'analisi.
#  Uguale per tutti i giochi: ognuno gli passa i suoi valori a ogni lettura.
# ════════════════════════════════════════════════════════════════════════════
class Giri:
    PASSO_M = 3.0              # un campione della traccia ogni 3 m
    # colonne della traccia: 0 d · 1 t ms · 2 v · 3 gas% · 4 freno% · 5 marcia · 6 giri · 7 sterzo% · 8 x · 9 y
    # 10 latG · 11 lonG · 12 sterzo ° · 13 TC attivo · 14 ABS attivo · 15 imbardata °/s · 16 sosp. ant mm
    # 17 sosp. post mm · 18 altezza ant mm · 19 altezza post mm · 20 batteria % · 21 deriva ant ° · 22 deriva post °
    # 23 slip ratio ant · 24 slip ratio post · 25 frizione% · 26 posizione laterale m (+/− dal centro, LMU/rF2)
    # 27 distanza centro→bordo dal lato della macchina m (LMU/rF2)
    # 28 gomme ant °C · 29 gomme post °C · 30 pressione ant bar · 31 pressione post bar · 32 freni ant °C · 33 freni post °C
    # 34 carico ant N · 35 carico post N · 36 rollio ° · 37 beccheggio ° · 38 G verticale · 39 coppia al volante
    # 40 cordolo · 41 aderenza usata ant (LMU) · 42 aderenza usata post (LMU) · 43 ibrido kW · 44 pressione freno ant · 45 coppia motore Nm
    # 46 tamponi ant · 47 tamponi post (dal vivo: stima del ponte o taratura da file .ld) · 48 force feedback % (LMU) · 49/50 terzo elemento ant/post mm (LMU)
    # 51 quota m (altezza della macchina: per la pista in 3D; iRacing non la manda)

    def __init__(self):
        self.reset()

    def reset(self):
        self.storia_ms = []; self.storia_fuel = []; self.cur_max = 0; self.pos_prec = None; self.fuel_prec = None
        self.perche_box = None; self.t_salto = -99
        self.prev_laps = None
        self.t0 = ORA()
        self.split_ms = []
        self.prev_sec = None
        self.fuel0 = None
        self.valido = True
        self.pit = False
        self.vmax = 0.0
        self.traccia = []
        self.ult_d = -1e9
        self.attesa = None        # giro chiuso che aspetta il tempo ufficiale dal gioco
        self.gomme = []
        self.lun = 0.0            # lunghezza pista stimata (m)
        self.d0 = None
        self.last_visto = None
        self.ultimo_cur = None
        self.riass = self._riass_nuovo()

    @staticmethod
    def _riass_nuovo():
        return {'n': 0, 'tcA': 0, 'absA': 0, 'tcOn': False, 'absOn': False, 'ti': [0.0] * 4, 'tm': [0.0] * 4, 'to': [0.0] * 4,
                'nt': 0, 'btMax': [0.0] * 4, 'rhMin': [None, None], 'susMax': [0.0] * 4, 'soc0': None, 'soc1': None,
                've0': None, 've1': None, 'elet': None, 'lim': 0, 'coast': 0.0, 'full': 0.0, 'tempo': 0.0, 'tpMax': [0.0] * 4,
                'water': 0.0, 'oil': 0.0}

    def _accumula(self, f, dt):
        r = self.riass
        x = f.get('e') or {}
        r['n'] += 1
        r['tempo'] += dt
        for k in ('tc', 'abs'):
            on = bool(x.get(k + 'A'))
            if on and not r[k + 'On']:
                r[k + 'A'] += 1                     # conta gli interventi, non i fotogrammi
            r[k + 'On'] = on
        thr, brk = f.get('thr') or 0, f.get('brk') or 0
        if thr < 0.05 and brk < 0.05 and (f.get('v') or 0) > 40:
            r['coast'] += dt
        if thr > 0.97:
            r['full'] += dt
        if f.get('ti') and f.get('tm') and f.get('to') and all(v is not None for v in f['ti'] + f['tm'] + f['to']):
            for i in range(4):
                r['ti'][i] += f['ti'][i]; r['tm'][i] += f['tm'][i]; r['to'][i] += f['to'][i]
            r['nt'] += 1
        if f.get('bt'):
            r['btMax'] = [max(a, b or 0) for a, b in zip(r['btMax'], f['bt'])]
        if f.get('tp'):
            r['tpMax'] = [max(a, b or 0) for a, b in zip(r['tpMax'], f['tp'])]
        rh = x.get('rh')
        if rh:
            fr = rh[0] if len(rh) == 2 else min(rh[0], rh[1])
            re_ = rh[1] if len(rh) == 2 else min(rh[2], rh[3])
            r['rhMin'] = [fr if r['rhMin'][0] is None else min(r['rhMin'][0], fr), re_ if r['rhMin'][1] is None else min(r['rhMin'][1], re_)]
        if x.get('sus'):
            r['susMax'] = [max(a, abs(b or 0)) for a, b in zip(r['susMax'], x['sus'])]
        e = x.get('ers') or {}
        if e.get('soc') is not None:
            if r['soc0'] is None:
                r['soc0'] = e['soc']
            r['soc1'] = e['soc']
        if e.get('ve') is not None:
            if r['ve0'] is None:
                r['ve0'] = e['ve']
            r['ve1'] = e['ve']
        el = {k: x.get(k) for k in ('tc', 'tcCut', 'tcSlip', 'abs', 'map', 'mig', 'arbF', 'arbR') if x.get(k) is not None}
        if f.get('bb') is not None:
            el['bb'] = f['bb']
        if e.get('mode') is not None:
            el['ers'] = e['mode']
        if el:
            r['elet'] = el
        eng = x.get('eng') or {}
        if eng.get('wT'):
            r['water'] = max(r['water'], eng['wT'])
        if eng.get('oT'):
            r['oil'] = max(r['oil'], eng['oT'])

    def _riass_chiudi(self):
        r = self.riass
        out = {'tcA': r['tcA'], 'absA': r['absA'], 'coast': round(r['coast'], 1), 'full': round(r['full'], 1),
               'btMax': [round(v) for v in r['btMax']] if any(r['btMax']) else None,
               'tpMax': [round(v, 3) for v in r['tpMax']] if any(r['tpMax']) else None,
               'rhMin': [r1(v) for v in r['rhMin']] if r['rhMin'][0] is not None else None,
               'susMax': [r1(v) for v in r['susMax']] if any(r['susMax']) else None, 'elet': r['elet'],
               'water': r1(r['water']) or None, 'oil': r1(r['oil']) or None}
        if r['nt']:
            out['ti'] = [r1(v / r['nt']) for v in r['ti']]; out['tm'] = [r1(v / r['nt']) for v in r['tm']]
            out['to'] = [r1(v / r['nt']) for v in r['to']]
        if r['soc0'] is not None:
            out['soc'] = [r1(r['soc0'], 3), r1(r['soc1'], 3)]
        if r['ve0'] is not None:
            out['ve'] = [r1(r['ve0'], 4), r1(r['ve1'], 4)]
        return pulito(out)

    def aggiorna(self, f, lun_pista, n_settori):
        """f = fotogramma normalizzato. Ritorna un evento 'lap' o None."""
        ev = None
        laps = f.get('lap')
        cur = f.get('cur')
        el = (ORA() - self.t0) * 1000.0
        if laps is None:
            return None
        if self.prev_laps is None:
            self.prev_laps = laps
            self.fuel0 = f.get('fuel')
        # ── giro chiuso ──
        if laps > self.prev_laps:
            ms_proprio = getattr(self, 'cur_max', 0) or (self.ultimo_cur if getattr(self, 'ultimo_cur', None) else el)
            self.attesa = {
                'n': laps, 'quando': ORA(), 'last_prima': self.last_visto,
                'ms_proprio': ms_proprio, 'split': list(self.split_ms), 'valido': self.valido,
                'pit': self.pit, 'perche_box': getattr(self, 'perche_box', None), 'vmax': self.vmax, 'fuel': (self.fuel0 - f['fuel']) if (
                    self.fuel0 is not None and f.get('fuel') is not None and self.fuel0 >= f['fuel']) else None,
                'traccia': self.traccia, 'gomme': self._media_gomme(), 'lun': lun_pista or self.lun,
                'nsec': n_settori, 'ufficiali': None, 'riass': self._riass_chiudi()
            }
            self.riass = self._riass_nuovo()
            if self.traccia and self.d0 is not None:
                self.lun = max(self.lun, self.traccia[-1][0])
            self.t0 = ORA()
            self.split_ms = []
            self.prev_sec = f.get('sec')
            self.fuel0 = f.get('fuel')
            self.valido = True
            self.cur_max = 0
            self.perche_box = 'corsia box' if f.get('pit') else None
            self.t_nuovo = ORA()                     # per 1,5 s il «non valido» è ancora quello del giro chiuso
            self.pit = bool(f.get('pit'))
            self.vmax = 0.0
            self.traccia = []
            self.ult_d = -1e9
            self.gomme = []
            self.d0 = None
            self.odo = 0.0
        elif laps < self.prev_laps:          # sessione ricominciata
            self.t0 = ORA(); self.split_ms = []; self.traccia = []; self.valido = True; self.d0 = None
            self.fuel0 = f.get('fuel'); self.attesa = None
        self.prev_laps = laps
        # ── il tempo ufficiale arriva a volte con un attimo di ritardo (iRacing) ──
        if self.attesa:
            a = self.attesa
            last = f.get('last')
            # pronto solo quando il gioco ha AGGIORNATO il tempo: prima bastava che fosse vicino al tempo
            # misurato da noi, e con giri costanti (entro 0,6 s) veniva preso il tempo del giro PRIMA
            pronto = bool(last and last > 0 and last != a['last_prima'])
            if getattr(self, 'last_sincrono', False) and last and last > 0:
                pronto = True                                  # LMU/rF2: tempo e numero di giri arrivano nello stesso aggiornamento
            if not pronto and ORA() - a['quando'] > 3.0 and last and last > 0 and a['last_prima'] is None:
                pronto = abs(last - a['ms_proprio']) < 400        # primo giro: non c'era un tempo prima con cui confrontarlo
            if pronto or ORA() - a['quando'] > 3.0:
                ms = last if pronto else a['ms_proprio']
                if pronto and f.get('_settori_ufficiali'):
                    a['ufficiali'] = f['_settori_ufficiali']
                elif not pronto:
                    a['ufficiali'] = None
                ev = self._evento(a, ms)
                self.attesa = None
        self.last_visto = f.get('last')
        if cur is not None:
            if cur == getattr(self, '_cur_raw', None) and cur > 0:
                cur = cur + min(400.0, (ORA() - self._cur_t) * 1000.0)
            else:
                self._cur_raw = cur; self._cur_t = ORA()
        self.ultimo_cur = cur
        if cur is not None and cur > getattr(self, 'cur_max', 0) and cur < 3600000:
            self.cur_max = cur
        # ── ritorno ai box dal menu, reset, rifornimento: il giro non è un giro vero ──
        xy = (f.get('x'), f.get('y'))
        pp = getattr(self, 'pos_prec', None)
        vv = f.get('v') or 0
        if pp and xy[0] is not None and pp[0] is not None:
            dtp = max(0.02, ORA() - pp[2])
            salto = math.hypot(xy[0] - pp[0], xy[1] - pp[1])
            if dtp < 1.0 and salto > max(150.0, vv / 3.6 * dtp * 3 + 50):
                self.t_salto = ORA()                 # da confermare: un dato sballato per un attimo non è un ritorno ai box
        self.pos_prec = (xy[0], xy[1], ORA())
        if ORA() - getattr(self, 't_salto', -99) < 3.0 and (f.get('pit') or f.get('garage') or vv < 5):
            self.pit = True; self.valido = False; self.perche_box = 'ritorno ai box dal menu'
        fu = f.get('fuel'); fp = getattr(self, 'fuel_prec', None)
        if fu is not None and fp is not None and fu > fp + 1.0 and (f.get('pit') or f.get('garage') or vv < 10):
            self.pit = True; self.perche_box = self.perche_box or 'rifornimento'
        self.fuel_prec = fu
        if f.get('pit') and not self.perche_box:
            self.perche_box = 'corsia box' if vv > 3 else 'fermo ai box'
        # ── settori ──
        sec = f.get('sec')
        if sec is not None and self.prev_sec is not None and sec != self.prev_sec and sec > self.prev_sec:
            self.split_ms.append(cur if cur else el)
        self.prev_sec = sec
        if f.get('valid') is False and ORA() - getattr(self, 't_nuovo', 0) > 1.5:
            self.valido = False
        if f.get('pit'):
            self.pit = True
        v = f.get('v') or 0
        self.vmax = max(self.vmax, v)
        # ── traccia a distanza fissa ──
        d = f.get('dist')
        if d is None and f.get('pct') is not None and lun_pista:
            d = f['pct'] * lun_pista
        # nessuna distanza dal gioco né lunghezza nota: contachilometri proprio (velocità × tempo)
        adesso = ORA()
        dt = adesso - getattr(self, 't_prec', adesso)
        self.t_prec = adesso
        if 0 < dt < 1:
            self.odo = getattr(self, 'odo', 0.0) + (v / 3.6) * dt
            self._accumula(f, dt)
        if d is None:
            d = getattr(self, 'odo', 0.0)
        if d is not None and v > 3:
            if self.d0 is None:
                self.d0 = d
            t_ora = cur if cur is not None else (ORA() - self.t0) * 1000.0
            indietro = bool(self.traccia) and t_ora < self.traccia[-1][1] - 500
            if (d - self.ult_d >= self.PASSO_M or d < self.ult_d - 50) and not indietro:
                self.ult_d = d
                x = f.get('e') or {}
                sus, rh, sa, sr = x.get('sus'), x.get('rh'), x.get('sa'), x.get('sr')
                def m2(a, i, j):
                    try:
                        return r1((abs(a[i]) + abs(a[j])) / 2.0, 2) if a and a[i] is not None and a[j] is not None else None
                    except (TypeError, IndexError):
                        return None
                rhF = rhR = None
                if rh:
                    rhF, rhR = (rh[0], rh[1]) if len(rh) == 2 else (r1((rh[0] + rh[1]) / 2.0), r1((rh[2] + rh[3]) / 2.0))
                soc = (x.get('ers') or {}).get('soc')
                # cur può valere 0 proprio all'inizio del giro: non va confuso con «manca»
                self.traccia.append([round(d, 1), int(cur if cur is not None else (ORA() - self.t0) * 1000.0), r1(v), r1((f.get('thr') or 0) * 100, 0),
                                     r1((f.get('brk') or 0) * 100, 0), f.get('gear'), f.get('rpm'),
                                     r1((f.get('str') or 0) * 100, 0), r1(f.get('x')), r1(f.get('y')),
                                     r1(f.get('latG'), 2), r1(f.get('lonG'), 2),
                                     r1(x.get('sdeg')), 1 if x.get('tcA') else 0, 1 if x.get('absA') else 0, r1(x.get('yaw')),
                                     m2(sus, 0, 1) if sus else None, m2(sus, 2, 3) if sus else None, rhF, rhR,
                                     r1(soc * 100, 1) if soc is not None else None,
                                     m2(sa, 0, 1) if sa else None, m2(sa, 2, 3) if sa else None,
                                     m2(sr, 0, 1) if sr else None, m2(sr, 2, 3) if sr else None,
                                     r1((f.get('clu') or 0) * 100, 0), r1(x.get('pl'), 2), r1(x.get('te'), 2)] + self._extra(f, x) + [r1(f.get('z'), 2)])
        if f.get('tt') and len(self.gomme) < 4000:
            self.gomme.append((f.get('tt'), f.get('tp')))
        return ev

    @staticmethod
    def _extra(f, x):
        """colonne 28–45: gomme, pressioni, freni, carichi, assetto, volante, cordoli, aderenza, ibrido, coppia"""
        def asse(a, i, j, scala=1.0, cifre=1):
            try:
                v = [a[i], a[j]]
                v = [z for z in v if z is not None]
                return r1(sum(v) / len(v) * scala, cifre) if v else None
            except (TypeError, IndexError):
                return None
        def somma(a, i, j):
            try:
                return r1(a[i] + a[j], 0) if a and a[i] is not None and a[j] is not None else None
            except (TypeError, IndexError):
                return None
        tm = f.get('tm') or f.get('tt'); tp = f.get('tp'); bt = f.get('bt'); ld = x.get('load'); gp = x.get('grip'); bp = x.get('bp')
        ers = x.get('ers') or {}
        return [asse(tm, 0, 1) if tm else None, asse(tm, 2, 3) if tm else None, asse(tp, 0, 1, 1, 3) if tp else None, asse(tp, 2, 3, 1, 3) if tp else None,
                asse(bt, 0, 1, 1, 0) if bt else None, asse(bt, 2, 3, 1, 0) if bt else None, somma(ld, 0, 1), somma(ld, 2, 3),
                r1(x.get('roll'), 2), r1(x.get('pitch'), 2), r1(x.get('vG'), 2), r1(x.get('stTq'), 2), x.get('kerb'),
                asse(gp, 0, 1, 1, 3) if gp else None, asse(gp, 2, 3, 1, 3) if gp else None, r1(ers.get('kw'), 0),
                asse(bp, 0, 1, 1, 3) if bp else None, r1(x.get('engTq'), 0),
                asse(x.get('bump'), 0, 1, 1, 1) if x.get('bump') else None,      # 46/47 tamponi ant/post (0 · 0,5 · 1)
                asse(x.get('bump'), 2, 3, 1, 1) if x.get('bump') else None,
                r1(x.get('ffb'), 1),                                            # 48 force feedback %
                (x.get('h3') or [None, None])[0], (x.get('h3') or [None, None])[1]]

    def _media_gomme(self):
        if not self.gomme:
            return None
        t = [0.0] * 4; p = [0.0] * 4; nt = np_ = 0
        for tt, tp in self.gomme:
            if tt and all(x is not None for x in tt):
                t = [a + b for a, b in zip(t, tt)]; nt += 1
            if tp and all(x is not None for x in tp):
                p = [a + b for a, b in zip(p, tp)]; np_ += 1
        return {'t': [round(x / nt, 1) for x in t] if nt else None, 'p': [round(x / np_, 3) for x in p] if np_ else None}

    def _evento(self, a, ms):
        ms = int(ms or 0)
        storia = getattr(self, 'storia_ms', [])
        ok_ms = sorted(x for x in storia if x > 0)
        rif = ok_ms[len(ok_ms) // 2] if len(ok_ms) >= 2 else None
        lun = a.get('lun') or 0
        anomalo = ms < 5000 or bool(rif and ms < rif * 0.6)      # nessun giro vero dura meno di 5 s; né il 40% meno dei tuoi giri
        if anomalo:
            a['valido'] = False; a['perche_box'] = a.get('perche_box') or ('tempo impossibile (%.1f s)' % (ms / 1000.0))
        else:
            storia.append(ms); self.storia_ms = storia[-8:]
        fus = getattr(self, 'storia_fuel', [])
        if a.get('fuel') is not None and len(fus) >= 2 and a['fuel'] > 3 * sorted(fus)[len(fus) // 2]:
            a['fuel'] = None                               # benzina «consumata» impossibile: non la si usa per i consumi
        elif a.get('fuel') and not a['pit']:
            fus.append(a['fuel']); self.storia_fuel = fus[-8:]
        sett = None
        if a.get('ufficiali'):
            sett = [int(round(x)) for x in a['ufficiali']]
        elif a['nsec'] == 3 and len(a['split']) >= 2 and ms:
            s1, s2 = a['split'][0], a['split'][1] - a['split'][0]
            sett = [int(s1), int(s2), int(ms - a['split'][1])]
        elif a['traccia'] and ms:
            # nessun settore dal gioco: tre terzi di pista, tempi interpolati sulla traccia
            tr = a['traccia']; d0, d1 = tr[0][0], tr[-1][0]; L = d1 - d0
            if L > 100:
                def t_a(d):
                    for i in range(1, len(tr)):
                        if tr[i][0] >= d:
                            p, q = tr[i - 1], tr[i]
                            k = (d - p[0]) / max(0.001, q[0] - p[0])
                            return p[1] + k * (q[1] - p[1])
                    return tr[-1][1]
                t1, t2 = t_a(d0 + L / 3), t_a(d0 + 2 * L / 3)
                sett = [int(t1), int(t2 - t1), int(ms - t2)]
        if sett and (min(sett) <= 0 or abs(sum(sett) - ms) > 50):
            sett = None
        return {'k': 'lap', 'n': a['n'], 'ms': ms, 's': sett, 'valid': a['valido'], 'pit': a['pit'], 'anomalo': bool(anomalo) or None,
                'perche': a.get('perche_box') if (a['pit'] or anomalo) else None,
                'vmax': r1(a['vmax']), 'fuel': r1(a['fuel'], 2), 'gomme': a['gomme'], 'riass': a.get('riass'),
                'lun': r1(a['lun'], 0), 'traccia': a['traccia'], 'ts': ms_ora()}


# ════════════════════════════════════════════════════════════════════════════
#  LETTORI DEI GIOCHI. Ognuno trasforma i dati del suo gioco nello stesso
#  "fotogramma": f (auto, 20 volte al secondo), s (sessione), c (altre auto).
# ════════════════════════════════════════════════════════════════════════════
class Lettore:
    gioco = '?'
    nome = '?'

    def __init__(self):
        self.giri = Giri()
        self.sessione = {}
        self.auto = []
        self.lun_pista = 0.0
        self.n_settori = 3
        self.ultima_sessione_json = None

    def apri(self):
        return False

    def chiudi(self):
        pass

    def leggi(self):
        """Ritorna il fotogramma f oppure None (gioco nei menu / chiuso)."""
        return None

    def comune(self, f):
        f['k'] = 'f'
        f['g'] = self.gioco
        f['ts'] = ms_ora()
        return f


def _ac_normalizza_gomme(ph, grezzo_bar=True):
    tp = [r1(x * PSI_BAR, 3) for x in ph.wheelsPressure] if grezzo_bar else None
    return tp


class LettoreAC(Lettore):
    """Assetto Corsa e Assetto Corsa Competizione: stessa memoria, stesso inizio."""

    def __init__(self):
        super().__init__()
        self.mp = self.mg = self.ms = None
        self.acc = False
        self.ult_statico = 0
        self.st = None
        self.dist_giro0 = None
        self.bcast = None

    def apri(self):
        try:
            self.mp = Mappa('Local\\acpmf_physics')
            self.mg = Mappa('Local\\acpmf_graphics')
            self.ms = Mappa('Local\\acpmf_static')
        except OSError:
            self.chiudi()
            return False
        pr = processi()
        self.acc = 'ac2-win64-shipping.exe' in pr
        if not pr:                         # senza elenco processi: guarda come sono fatti i dati
            g = leggi_struct(self.mg, ST.ACC_GRAPHICS)
            self.acc = 1 <= g.activeCars <= 60 and 0 <= g.playerCarID < 1000
        self.gioco = 'acc' if self.acc else 'ac'
        self.nome = 'Assetto Corsa Competizione' if self.acc else 'Assetto Corsa'
        return True

    def chiudi(self):
        for m in (self.mp, self.mg, self.ms):
            if m:
                m.chiudi()
        self.mp = self.mg = self.ms = None
        if self.bcast:
            self.bcast.chiudi(); self.bcast = None

    def leggi(self):
        ph = leggi_struct(self.mp, ST.ACC_PHYSICS if self.acc else ST.AC_PHYSICS)
        gr = leggi_struct(self.mg, ST.ACC_GRAPHICS if self.acc else ST.AC_GRAPHICS)
        if ORA() - self.ult_statico > 2 or self.st is None:
            self.st = leggi_struct(self.ms, ST.AC_STATIC)
            self.ult_statico = ORA()
        st = self.st
        if gr.status != 2:                     # 2 = in pista dal vivo (0 spento, 1 replay, 3 pausa): niente dati vecchi
            return None
        self.n_settori = st.sectorCount if 1 <= st.sectorCount <= 20 else 3
        if st.trackSPlineLength > 100:
            self.lun_pista = st.trackSPlineLength
        # posizione del giocatore
        x = y = z = None
        if self.acc:
            for i in range(min(max(gr.activeCars, 0), 60)):
                if gr.carID[i] == gr.playerCarID:
                    x, y, z = gr.carCoordinates[i * 3], gr.carCoordinates[i * 3 + 2], gr.carCoordinates[i * 3 + 1]
                    break
        else:
            x, y, z = gr.carCoordinates[0], gr.carCoordinates[2], gr.carCoordinates[1]
        if self.lun_pista < 100 and self.giri.lun > 100:
            self.lun_pista = self.giri.lun
        f = {
            'v': r1(ph.speedKmh), 'rpm': int(ph.rpms), 'rpmMax': int(st.maxRpm) or None, 'gear': int(ph.gear) - 1,
            'thr': r1(ph.gas, 3), 'brk': r1(ph.brake, 3), 'clu': r1(ph.clutch, 3),
            'str': r1(max(-1, min(1, ph.steerAngle if self.acc else ph.steerAngle / 4.0)), 3),
            'fuel': r1(ph.fuel, 2), 'fuelCap': r1(st.maxFuel, 1) or None,
            'latG': r1(ph.accG[0], 2), 'lonG': r1(ph.accG[2], 2), 'x': r1(x), 'y': r1(y), 'z': r1(z),
            'pct': r1(gr.normalizedCarPosition, 5), 'lap': int(gr.completedLaps),
            'cur': int(gr.iCurrentTime) if gr.iCurrentTime > 0 else None,
            'last': int(gr.iLastTime) if 0 < gr.iLastTime < 2147483647 else None,
            'best': int(gr.iBestTime) if 0 < gr.iBestTime < 2147483647 else None,
            'sec': int(gr.currentSectorIndex), 'pos': int(gr.position) or None,
            'pit': bool(gr.isInPitLane or gr.isInPit),
            'valid': bool(gr.isValidLap) if self.acc else (ph.numberOfTyresOut <= 2),
            'bb': r1(ph.brakeBias * 100, 1) if ph.brakeBias > 0 else None,
            'tp': [r1(p * PSI_BAR, 3) for p in ph.wheelsPressure],
            'tt': [r1(t) for t in ph.tyreCoreTemperature],
            'bt': [r1(t) for t in ph.brakeTemp],
            'comp': txt(gr.tyreCompound),
            'tc': r1(ph.tc, 2), 'abs': r1(ph.abs, 2),
            'dmg': danni(corpo=max(ph.carDamage), scala=(100.0 if self.acc else 1.0), grezzo=list(ph.carDamage)),
        }
        if self.acc:
            gname, wet = GRIP_ACC.get(gr.trackGripStatus, ('', None))
            f['wx'] = {'rain': PIOGGIA_ACC.get(gr.rainIntensity), 'wet': wet, 'grip': gname,
                       'rain10': PIOGGIA_ACC.get(gr.rainIntensityIn10min), 'rain30': PIOGGIA_ACC.get(gr.rainIntensityIn30min),
                       'air': r1(ph.airTemp, 1), 'road': r1(ph.roadTemp, 1),
                       'wind': r1(getattr(gr, 'windSpeed', 0), 1) or None, 'windDir': r1(getattr(gr, 'windDirection', 0) * DEG, 0) if getattr(gr, 'windSpeed', 0) else None,
                       'rho': r1(getattr(ph, 'airDensity', 0), 3) or None}
            f['tset'] = int(gr.currentTyreSet) or None
        else:
            f['wx'] = {'grip': r1(gr.surfaceGrip, 3), 'air': r1(ph.airTemp, 1), 'road': r1(ph.roadTemp, 1),
                       'wind': r1(getattr(gr, 'windSpeed', 0), 1) or None, 'windDir': r1(getattr(gr, 'windDirection', 0) * DEG, 0) if getattr(gr, 'windSpeed', 0) else None,
                       'rho': r1(getattr(ph, 'airDensity', 0), 3) or None}
        if not self.acc:
            f['ti'] = [r1(t) for t in ph.tyreTempI]; f['tm'] = [r1(t) for t in ph.tyreTempM]
            f['to'] = [r1(t) for t in ph.tyreTempO]
            if any(w > 0 for w in ph.tyreWear):
                f['tw'] = [r1(max(0.0, min(1.0, (100 - w) / 100.0)), 3) for w in ph.tyreWear]
        else:
            f['fuelLap'] = r1(gr.fuelXLap, 2) or None
        # ── elettronica, telaio, gomme (ponte 2.0) ──
        # ACC non usa tcInAction/absInAction (restano a zero): l'intervento si legge da ph.tc / ph.abs
        # («in azione», 0 quando non lavora) e dalle vibrazioni dell'ABS. Se ph.tc resta sempre acceso è il
        # livello e non l'intervento: allora non lo si usa.
        tcA, absA = bool(ph.tcInAction), bool(ph.absInAction)
        if self.acc:
            st_ = self.__dict__.setdefault('_att', {'tc': [], 'abs': []})
            for k_, v_ in (('tc', ph.tc), ('abs', ph.abs)):
                st_[k_].append(1 if v_ > 0 else 0)
                if len(st_[k_]) > 400: st_[k_].pop(0)
            sempre = lambda k_: len(st_[k_]) > 100 and sum(st_[k_]) / len(st_[k_]) > 0.9
            tcA = tcA or (ph.tc > 0 and not sempre('tc') and ph.gas > 0.2)
            absA = absA or (ph.abs > 0 and not sempre('abs') and ph.brake > 0.1) or (getattr(ph, 'absVibrations', 0) > 0.01 and ph.brake > 0.1)
        x = {
            'tcA': 1 if tcA else 0, 'absA': 1 if absA else 0, 'lim': 1 if ph.pitLimiterOn else 0,
            'yaw': r1(ph.localAngularVel[1] * DEG, 1), 'pitch': r1(ph.pitch * DEG, 2), 'roll': r1(ph.roll * DEG, 2),
            'vG': r1(ph.accG[1], 2), 'sus': lista(ph.suspensionTravel, 1000.0, 1),
            'rh': [r1(ph.rideHeight[0] * 1000, 1), r1(ph.rideHeight[1] * 1000, 1)] if any(ph.rideHeight) else None,
            'sr': lista(ph.slipRatio, 1.0, 3), 'sa': lista(ph.slipAngle, DEG, 2), 'load': listaNZ(ph.wheelLoad, 1.0, 0),
            'cam': listaNZ(ph.camberRAD, DEG, 2),
            'eng': {'boost': r1(ph.turboBoost, 2) if ph.turboBoost else None},
            # canali in più: forze sulla gomma, velocità delle ruote, sporco, forza sul volante, baricentro
            'fx': listaNZ(ph.fx, 1.0, 0), 'fy': listaNZ(ph.fy, 1.0, 0), 'mz': listaNZ(ph.mz, 1.0, 1),
            'ws': listaNZ(ph.wheelAngularSpeed, 1.0, 1), 'dirt': listaNZ(ph.tyreDirtyLevel, 1.0, 2),
            'stTq': r1(ph.finalFF, 3), 'cg': r1(ph.cgHeight * 1000, 1) if ph.cgHeight else None,
            'angv': [r1(ph.localAngularVel[k] * DEG, 1) for k in range(3)], 'out': int(ph.numberOfTyresOut),
        }
        if self.acc:
            x['sdeg'] = r1(ph.steerAngle * STERZO_ACC / 2.0, 1); x['sdegStima'] = 1
            x['tc'] = livello(gr.TC); x['tcCut'] = livello(gr.TCCut); x['abs'] = livello(gr.ABS); x['map'] = livello(gr.EngineMap)
            x['eng']['exT'] = r1(gr.exhaustTemperature) or None
            x['delta'] = (1 if gr.isDeltaPositive else -1) * abs(int(gr.iDeltaLapTime)) if gr.iDeltaLapTime else None
            # ACC 1.8: pressione nei circuiti dei freni, usura di pastiglie e dischi, cordoli
            x['bp'] = lista(ph.brakePressure, 1.0, 3) if any(ph.brakePressure) else None
            x['pad'] = lista(ph.padLife, 1.0, 1) if any(ph.padLife) else None
            x['disc'] = lista(ph.discLife, 1.0, 1) if any(ph.discLife) else None
            x['kerb'] = r1(ph.kerbVibration, 2) if ph.kerbVibration else 0
            x['eng']['wT'] = r1(ph.waterTemp) if ph.waterTemp else None
            x['eB'] = int(ph.engineBrake) if ph.engineBrake else None
            x['mfd'] = {'fuel': r1(gr.mfdFuelToAdd, 1), 'set': int(gr.mfdTyreSet) + 1 if gr.mfdTyreSet >= 0 else None,
                        'p': [r1(v * PSI_BAR, 3) for v in (gr.mfdTyrePressureLF, gr.mfdTyrePressureRF, gr.mfdTyrePressureLR, gr.mfdTyrePressureRR)]}
            x['stint'] = int(gr.driverStintTimeLeft) if gr.driverStintTimeLeft > 0 else None
            x['pitsMancanti'] = int(gr.missingMandatoryPits) if gr.missingMandatoryPits >= 0 else None
            x['fuelLaps'] = r1(gr.fuelEstimatedLaps, 1) or None
            f['delta'] = x['delta']
        else:
            x['sdeg'] = r1(ph.steerAngle * DEG, 1)
            x['tc'] = r1(ph.tc, 2) if ph.tc > 0 else None
            x['abs'] = r1(ph.abs, 2) if ph.abs > 0 else None
            x['drs'] = 2 if ph.drs > 0 else (1 if ph.drsAvailable else 0) if st.hasDRS else None
            if st.hasERS or st.hasKERS:
                x['ers'] = {'soc': r1(ph.kersCharge, 3), 'mode': int(ph.ersPowerLevel), 'modeMax': int(st.ersPowerControllerCount) or None,
                            'regen': int(ph.ersRecoveryLevel), 'chg': 1 if ph.ersIsCharging else 0, 'kw': r1(ph.kersInput * 120, 0)}
            x['map'] = int(ph.engineBrake) if st.engineBrakeSettingsCount else None
        f['e'] = pulito(x)
        fl = BANDIERA_AC.get(int(gr.flag), 'none')
        if self.acc:
            if gr.GlobalRed:
                fl = 'red'
            elif gr.GlobalChequered and fl == 'none':
                fl = 'chequered'
            sett = [bool(gr.GlobalYellow1), bool(gr.GlobalYellow2), bool(gr.GlobalYellow3)]
            if fl == 'none' and gr.GlobalYellow:
                fl = 'yellow'
            if fl == 'none' and gr.GlobalGreen:
                fl = 'green'
            f['fl'] = pulito({'f': fl, 'sett': sett if any(sett) else None, 'lastLap': 1 if gr.GlobalWhite else None})
            f['pen'] = pulito({'tempo': r1(gr.penaltyTime, 1) if gr.penaltyTime > 0 else None,
                               'tipo': PENALITA_ACC.get(int(gr.penalty)) if gr.penalty > 0 else None})
        else:
            f['fl'] = {'f': fl}
            f['pen'] = pulito({'tempo': r1(gr.penaltyTime, 1) if gr.penaltyTime > 0 else None})
        self.sessione = {
            'k': 's', 'g': self.gioco, 'nome': self.nome, 'track': txt(st.track), 'cfg': txt(st.trackConfiguration),
            'trackLen': r1(self.lun_pista, 0) or None, 'car': txt(st.carModel),
            'driver': (txt(st.playerName) + ' ' + txt(st.playerSurname)).strip(),
            'cls': classe_acc(nome=txt(st.carModel)) if self.acc else None,
            'type': {0: 'P', 1: 'Q', 2: 'R', 3: 'HOTLAP', 4: 'TA', 5: 'DRIFT', 6: 'DRAG', 7: 'HOTSTINT'}.get(gr.session, str(gr.session)),
            'left': int(gr.sessionTimeLeft) if gr.sessionTimeLeft > 0 else None,
            'airT': r1(ph.airTemp), 'roadT': r1(ph.roadTemp), 'nsec': self.n_settori,
            'maxRpm': int(st.maxRpm) or None, 'fuelCap': r1(st.maxFuel, 1) or None,
            'autoInfo': pulito({'kw': r1(st.maxPower / 1000.0 if st.maxPower > 5000 else st.maxPower, 0) or None, 'nm': r1(st.maxTorque, 0) or None,
                                'rpm': int(st.maxRpm) or None, 'serbatoio': r1(st.maxFuel, 0) or None}),
            'aiuti': aiuti_ac(st),
        }
        # altre auto
        if self.acc:
            auto = []
            nomi = self.bcast.auto if self.bcast else {}
            for i in range(min(max(gr.activeCars, 0), 60)):
                cid = gr.carID[i]
                a = {'id': cid, 'x': r1(gr.carCoordinates[i * 3]), 'y': r1(gr.carCoordinates[i * 3 + 2]), 'z': r1(gr.carCoordinates[i * 3 + 1]),
                     'me': cid == gr.playerCarID}
                if cid in nomi:
                    a.update(nomi[cid])
                auto.append(a)
            if self.bcast and self.bcast.pista_m and not self.lun_pista:
                self.lun_pista = self.bcast.pista_m
            self.auto = auto
        else:
            self.auto = [{'id': 0, 'x': f['x'], 'y': f['y'], 'me': True, 'pct': f['pct'], 'pos': f['pos'],
                          'lap': f['lap'], 'last': f['last'], 'best': f['best'], 'n': self.sessione['driver']}]
        return self.comune(f)


class LettoreEVO(Lettore):
    gioco = 'acevo'
    nome = 'Assetto Corsa EVO'

    def __init__(self):
        super().__init__()
        self.mp = self.mg = self.ms = None
        self.st = None
        self.ult_statico = 0

    def apri(self):
        try:
            self.mp = Mappa('Local\\acevo_pmf_physics')
            self.mg = Mappa('Local\\acevo_pmf_graphics')
            self.ms = Mappa('Local\\acevo_pmf_static')
            return True
        except OSError:
            self.chiudi()
            return False

    def chiudi(self):
        for m in (self.mp, self.mg, self.ms):
            if m:
                m.chiudi()
        self.mp = self.mg = self.ms = None

    def leggi(self):
        ph = leggi_struct(self.mp, ST.AC_PHYSICS)
        gr = leggi_struct(self.mg, ST.EVO_GRAPHICS)
        if ORA() - self.ult_statico > 2 or self.st is None:
            self.st = leggi_struct(self.ms, ST.EVO_STATIC)
            self.ult_statico = ORA()
        st = self.st
        if gr.status != 2:                     # 2 = in pista dal vivo (0 spento, 1 replay, 3 pausa): niente dati vecchi
            return None
        if st.track_length_m > 100:
            self.lun_pista = st.track_length_m
        gomme = [gr.tyre_lf, gr.tyre_rf, gr.tyre_lr, gr.tyre_rr]
        n = min(int(gr.active_cars), 60)
        me = (gr.player_car_id_a, gr.player_car_id_b)
        x = y = z = None
        auto = []
        for i in range(n):
            ida, idb = gr.car_ids[i * 2], gr.car_ids[i * 2 + 1]
            a = {'id': '%x' % (ida ^ idb), 'x': r1(gr.car_coordinates[i * 3]), 'y': r1(gr.car_coordinates[i * 3 + 2]), 'z': r1(gr.car_coordinates[i * 3 + 1]),
                 'me': (ida, idb) == me}
            if a['me']:
                x, y, z = a['x'], a['y'], a['z']
            auto.append(a)
        self.auto = auto
        f = {
            'v': r1(ph.speedKmh), 'rpm': int(ph.rpms), 'rpmMax': int(ph.currentMaxRpm) or None, 'gear': int(ph.gear) - 1,
            'thr': r1(ph.gas, 3), 'brk': r1(ph.brake, 3), 'clu': r1(ph.clutch, 3),
            'str': r1(max(-1, min(1, gr.steering_percent)), 3),
            'fuel': r1(gr.fuel_liter_current_quantity, 2), 'fuelCap': r1(gr.max_fuel, 1) or None,
            'fuelLap': r1(gr.fuel_liter_per_lap, 2) or None,
            'latG': r1(ph.accG[0], 2), 'lonG': r1(ph.accG[2], 2), 'x': x, 'y': y, 'z': z,
            'pct': r1(gr.npos, 5), 'lap': int(gr.total_lap_count),
            'cur': int(gr.current_lap_time_ms) if gr.current_lap_time_ms > 0 else None,
            'last': int(gr.last_laptime_ms) if gr.last_laptime_ms > 0 else None,
            'best': int(gr.best_laptime_ms) if gr.best_laptime_ms > 0 else None,
            'sec': None, 'pos': int(gr.current_pos) or None, 'pit': bool(gr.is_in_pit_lane or gr.is_in_pit_box),
            'valid': bool(gr.is_valid_lap), 'bb': r1(ph.brakeBias * 100, 1) if ph.brakeBias > 0 else None,
            'tp': [pressione_bar(g.tyre_pressure) for g in gomme],
            'tt': [r1(t) for t in ph.tyreCoreTemperature],
            'ti': [r1(g.tyre_temperature_left if i % 2 else g.tyre_temperature_right) for i, g in enumerate(gomme)],
            'tm': [r1(g.tyre_temperature_center) for g in gomme],
            'to': [r1(g.tyre_temperature_right if i % 2 else g.tyre_temperature_left) for i, g in enumerate(gomme)],
            'bt': [r1(g.brake_temperature_c) for g in gomme], 'comp': txt(gomme[0].tyre_compound_front),
            'delta': int(gr.delta_time_ms),
            'dmg': danni(corpo=max(ph.carDamage), scala=250.0, sosp=list(ph.suspensionDamage), grezzo=list(ph.carDamage)),
        }
        x = {
            'sdeg': r1(gr.steer_degrees, 1), 'tcA': 1 if gr.tc_active else 0, 'absA': 1 if gr.abs_active else 0,
            'escA': 1 if gr.esc_active else 0, 'lim': 1 if ph.pitLimiterOn else 0,
            'tc': r1(ph.tc, 2) if ph.tc > 0 else None, 'abs': r1(ph.abs, 2) if ph.abs > 0 else None,
            'drs': (2 if ph.drs > 0 else 1) if gr.is_drs_available else None,
            'yaw': r1(ph.localAngularVel[1] * DEG, 1), 'pitch': r1(ph.pitch * DEG, 2), 'roll': r1(ph.roll * DEG, 2),
            'vG': r1(gr.g_forces_y, 2), 'sus': lista(ph.suspensionTravel, 1000.0, 1),
            'rh': [r1(ph.rideHeight[0] * 1000, 1), r1(ph.rideHeight[1] * 1000, 1)] if any(ph.rideHeight) else None,
            'sr': lista(ph.slipRatio, 1.0, 3), 'sa': lista(ph.slipAngle, DEG, 2), 'load': listaNZ(ph.wheelLoad, 1.0, 0),
            'cam': listaNZ(ph.camberRAD, DEG, 2),
            'eng': {'wT': r1(gr.water_temperature_c) or None, 'oT': r1(gr.oil_temperature_c) or None,
                    'oP': r1(gr.oil_pressure_bar, 2) or None, 'fP': r1(gr.fuel_pressure_bar, 2) or None,
                    'boost': r1(gr.turbo_boost, 2) or None, 'exT': r1(gr.exhaust_temperature_c) or None},
            'gapA': r1(gr.gap_ahead, 3) or None, 'gapB': r1(gr.gap_behind, 3) or None,
            'diff': {'coast': r1(gr.diff_coast_raw_value, 2), 'power': r1(gr.diff_power_raw_value, 2)},
            'perf': txt(gr.performance_mode_name) or None,
        }
        if gr.has_kers:
            x['ers'] = {'soc': r1(gr.kers_charge_perc, 3), 'chg': 1 if gr.kers_is_charging or gr.battery_is_charging else 0,
                        'kw': r1(gr.kers_current_perc * 100, 0), 'temp': r1(gr.battery_temperature) or None}
        f['e'] = pulito(x)
        fl = BANDIERA_AC.get(int(gr.flag), 'none')
        if fl == 'none':
            fl = BANDIERA_AC.get(int(gr.global_flag), 'none')
        f['fl'] = {'f': fl}
        f['pen'] = pulito({'taglio': r1(gr.race_cut_current_delta, 2) if gr.race_cut_current_delta else None,
                           'restituire': r1(gr.race_cut_gained_time_ms / 1000.0, 2) if gr.race_cut_gained_time_ms > 0 else None,
                           'entro': int(gr.distance_to_deadline) if gr.race_cut_gained_time_ms > 0 and gr.distance_to_deadline > 0 else None})
        self.sessione = {
            'k': 's', 'g': self.gioco, 'nome': self.nome, 'track': txt(st.track), 'cfg': txt(st.track_configuration),
            'trackLen': r1(self.lun_pista, 0) or None, 'lat': r1(st.latitude, 5) or None, 'lon': r1(st.longitude, 5) or None,
            'car': txt(gr.car_model), 'driver': (txt(gr.driver_name) + ' ' + txt(gr.driver_surname)).strip(),
            'type': {0: 'TA', 1: 'R', 2: 'HOTSTINT', 3: 'CRUISE'}.get(st.session, str(st.session)),
            'airT': r1(ph.airTemp), 'roadT': r1(ph.roadTemp), 'nsec': 3,
            'maxRpm': int(ph.currentMaxRpm) or None, 'fuelCap': r1(gr.max_fuel, 1) or None,
        }
        return self.comune(f)


class LettoreIRacing(Lettore):
    """iRacing: memoria "IRSDKMemMapFileName" con variabili descritte da intestazioni."""
    gioco = 'iracing'
    nome = 'iRacing'
    TIPI = {0: ('c', 1), 1: ('?', 1), 2: ('i', 4), 3: ('I', 4), 4: ('f', 4), 5: ('d', 8)}

    def __init__(self):
        super().__init__()
        self.m = None
        self.var = {}
        self.info_ver = -1
        self.yaml = ''
        self.piloti = {}
        self.me = 0
        self.settori_pct = [0, 1 / 3, 2 / 3]
        self.pos_xy = [0.0, 0.0]
        self.t_prec = None
        self.mappa_ok = False

    def apri(self):
        try:
            self.m = Mappa('Local\\IRSDKMemMapFileName')
        except OSError:
            return False
        return True

    def chiudi(self):
        if self.m:
            self.m.chiudi()
        self.m = None

    def _intestazione(self):
        h = struct.unpack_from('<10i', self.m.leggi(40))
        ver, status, tick, info_upd, info_len, info_off, nvars, var_off, nbuf, buflen = h
        bufs = []
        for i in range(min(nbuf, 4)):
            tc, off = struct.unpack_from('<2i', self.m.leggi(8, 48 + i * 16))
            bufs.append((tc, off))
        return status, info_upd, info_len, info_off, nvars, var_off, buflen, bufs

    def _variabili(self, nvars, var_off):
        raw = self.m.leggi(nvars * 144, var_off)
        self.var = {}
        for i in range(nvars):
            b = raw[i * 144:(i + 1) * 144]
            if len(b) < 144:
                break
            tipo, off, cnt = struct.unpack_from('<3i', b)
            nome = b[16:48].split(b'\0', 1)[0].decode('latin-1')
            self.var[nome] = (tipo, off, cnt)

    def _info(self, info_len, info_off):
        self.yaml = self.m.leggi(info_len, info_off).split(b'\0', 1)[0].decode('latin-1', 'ignore')
        y = self.yaml

        def val(k):
            m = re.search(r'^\s*' + k + r':\s*(.*)$', y, re.M)
            return m.group(1).strip() if m else ''
        self.me = int(val('DriverCarIdx') or 0)
        L = val('TrackLength')
        m = re.match(r'([\d.]+)\s*(km|mi)', L)
        if m:
            self.lun_pista = float(m.group(1)) * (1000 if m.group(2) == 'km' else 1609.34)
        self.piloti = {}
        for blocco in re.split(r'\n\s*-\s*CarIdx:', y)[1:]:
            idx = int(re.match(r'\s*(\d+)', blocco).group(1))
            nm = re.search(r'UserName:\s*(.*)', blocco)
            nr = re.search(r'CarNumber:\s*"?([^"\n]*)', blocco)
            car = re.search(r'CarScreenName:\s*(.*)', blocco)
            cls = re.search(r'CarClassShortName:\s*(.*)', blocco)
            self.piloti[idx] = {'n': nm.group(1).strip() if nm else '', 'num': nr.group(1).strip() if nr else '',
                                'car': car.group(1).strip() if car else '', 'cls': cls.group(1).strip() if cls else ''}
        pct = [float(p) for p in re.findall(r'SectorStartPct:\s*([\d.]+)', y)]
        if pct:
            self.settori_pct = pct
        self.n_settori = len(self.settori_pct)
        tn = val('TrackDisplayName') or val('TrackName')
        tc = val('TrackConfigName')
        me = self.piloti.get(self.me, {})
        self.sessione = {'k': 's', 'g': self.gioco, 'nome': self.nome, 'track': tn, 'cfg': tc,
                         'trackId': val('TrackName'), 'trackLen': r1(self.lun_pista, 0) or None, 'car': me.get('car', ''),
                         'driver': me.get('n', ''), 'cls': me.get('cls') or None, 'nsec': self.n_settori, 'sectorPct': self.settori_pct,
                         'airT': r1(num(re.sub(r'[^\d.\-]', '', val('TrackAirTemp') or '')), 1),
                         'roadT': r1(num(re.sub(r'[^\d.\-]', '', val('TrackSurfaceTemp') or '')), 1)}

    def _v(self, buf, nome, i=0, d=None):
        v = self.var.get(nome)
        if not v:
            return d
        tipo, off, cnt = v
        fmt, sz = self.TIPI.get(tipo, ('f', 4))
        if i >= cnt:
            return d
        try:
            return struct.unpack_from('<' + fmt, buf, off + i * sz)[0]
        except struct.error:
            return d

    def _arr(self, buf, nome):
        v = self.var.get(nome)
        if not v:
            return []
        return [self._v(buf, nome, i) for i in range(v[2])]

    def leggi(self):
        status, info_upd, info_len, info_off, nvars, var_off, buflen, bufs = self._intestazione()
        if not (status & 1) or not bufs:
            return None
        if info_upd != self.info_ver:
            self._variabili(nvars, var_off)
            self._info(info_len, info_off)
            self.info_ver = info_upd
        tc, off = max(bufs, key=lambda b: b[0])
        buf = self.m.leggi(buflen, off)
        if 'IsOnTrack' in self.var and not self._v(buf, 'IsOnTrack', d=False) and not self._v(buf, 'IsOnTrackCar', d=False):
            return None                           # nel garage o a guardare: la tua macchina non sta girando
        v = self._v(buf, 'Speed', d=0.0) * 3.6
        yaw = self._v(buf, 'Yaw', d=0.0)
        t = self._v(buf, 'SessionTime', d=0.0)
        # posizione ricavata dalla velocità (iRacing non dà le coordinate dal vivo)
        if self.t_prec is not None and 0 < t - self.t_prec < 1:
            dt = t - self.t_prec
            vs = v / 3.6
            self.pos_xy[0] += vs * math.cos(yaw) * dt
            self.pos_xy[1] += vs * math.sin(yaw) * dt
        self.t_prec = t
        pct = self._v(buf, 'LapDistPct', d=None)
        sec = None
        if pct is not None and pct >= 0:
            sec = 0
            for i, p in enumerate(self.settori_pct):
                if pct >= p:
                    sec = i
        cur = self._v(buf, 'LapCurrentLapTime', d=None)
        last = self._v(buf, 'LapLastLapTime', d=None)
        best = self._v(buf, 'LapBestLapTime', d=None)
        fuel = self._v(buf, 'FuelLevel', d=None)
        fpct = self._v(buf, 'FuelLevelPct', d=None)
        cap = (fuel / fpct) if (fuel and fpct and fpct > 0.01) else None
        pr = [self._v(buf, k + 'press', d=None) for k in ('LF', 'RF', 'LR', 'RR')]
        tm = [self._v(buf, k + 'tempCM', d=None) for k in ('LF', 'RF', 'LR', 'RR')]
        ti = [self._v(buf, k + ('tempCR' if k[0] == 'L' else 'tempCL'), d=None) for k in ('LF', 'RF', 'LR', 'RR')]
        to = [self._v(buf, k + ('tempCL' if k[0] == 'L' else 'tempCR'), d=None) for k in ('LF', 'RF', 'LR', 'RR')]
        wear = [self._v(buf, k + 'wearM', d=None) for k in ('LF', 'RF', 'LR', 'RR')]
        f = {
            'v': r1(v), 'rpm': int(self._v(buf, 'RPM', d=0)), 'gear': self._v(buf, 'Gear', d=0),
            'thr': r1(self._v(buf, 'Throttle', d=0), 3), 'brk': r1(self._v(buf, 'Brake', d=0), 3),
            'clu': r1(1 - (self._v(buf, 'Clutch', d=1) or 0), 3),
            'str': r1(max(-1, min(1, -(self._v(buf, 'SteeringWheelAngle', d=0) or 0) / 3.0)), 3),
            'fuel': r1(fuel, 2), 'fuelCap': r1(cap, 1),
            'latG': r1((self._v(buf, 'LatAccel', d=0) or 0) / 9.81, 2),
            'lonG': r1((self._v(buf, 'LongAccel', d=0) or 0) / 9.81, 2),
            'x': r1(self.pos_xy[0]), 'y': r1(self.pos_xy[1]),
            'pct': r1(pct, 5), 'dist': r1(self._v(buf, 'LapDist', d=None)), 'lap': self._v(buf, 'LapCompleted', d=None),
            'cur': int(cur * 1000) if cur and cur > 0 else None, 'last': int(last * 1000) if last and last > 0 else None,
            'best': int(best * 1000) if best and best > 0 else None, 'sec': sec,
            'pos': self._v(buf, 'PlayerCarPosition', d=None) or None, 'pit': bool(self._v(buf, 'OnPitRoad', d=False)),
            'bb': r1(self._v(buf, 'dcBrakeBias', d=None), 1),
            'delta': int((self._v(buf, 'LapDeltaToBestLap', d=0) or 0) * 1000) if self.var.get('LapDeltaToBestLap') else None,
        }
        V = lambda n, d=None: self._v(buf, n, d=d)
        tre = lambda pre, suf: [V(k + suf) for k in pre]
        sus = tre(('LF', 'RF', 'LR', 'RR'), 'shockDefl')
        rh = tre(('LF', 'RF', 'LR', 'RR'), 'rideHeight')
        warn = V('EngineWarnings', 0) or 0
        x = {
            'sdeg': r1(-(V('SteeringWheelAngle', 0) or 0) * DEG, 1),
            'tc': livello(V('dcTractionControl')), 'tc2': livello(V('dcTractionControl2')), 'abs': livello(V('dcABS')),
            'map': livello(V('dcEngineMap')) if V('dcEngineMap') is not None else livello(V('dcThrottleShape')),
            'absA': 1 if V('BrakeABSactive') else 0, 'lim': 1 if (warn & 0x10) else 0,
            'arbF': r1(V('dcAntiRollFront'), 1), 'arbR': r1(V('dcAntiRollRear'), 1),
            'drs': V('DRS_Status'),
            'yaw': r1((V('YawRate', 0) or 0) * DEG, 1), 'pitch': r1((V('Pitch', 0) or 0) * DEG, 2), 'roll': r1((V('Roll', 0) or 0) * DEG, 2),
            'vG': r1((V('VertAccel', 0) or 0) / 9.81, 2),
            'sus': [r1(s * 1000, 1) if s is not None else None for s in sus],
            'rh': [r1(s * 1000, 1) if s is not None else None for s in rh],
            'eng': {'wT': r1(V('WaterTemp')), 'oT': r1(V('OilTemp')), 'oP': r1((V('OilPress') or 0) / 100.0, 2) or None,
                    'fP': r1((V('FuelPress') or 0) / 100.0, 2) or None, 'boost': r1((V('ManifoldPress') or 0), 2) or None,
                    'volt': r1(V('Voltage'), 1), 'fuelH': r1(V('FuelUsePerHour'), 1)},
            'bp': [r1(b, 2) if b is not None else None for b in tre(('LF', 'RF', 'LR', 'RR'), 'brakeLinePress')] if V('LFbrakeLinePress') is not None else None,
            'sv': [r1(b * 1000, 0) if b is not None else None for b in tre(('LF', 'RF', 'LR', 'RR'), 'shockVel')] if V('LFshockVel') is not None else None,
            'stTq': r1(V('SteeringWheelTorque'), 2), 'stPct': r1(V('SteeringWheelPctTorque'), 3),
            'kerb': 1 if any((V('Tire' + k + '_RumblePitch') or 0) > 0 for k in ('LF', 'RF', 'LR', 'RR')) else 0,
            'brkRaw': r1(V('BrakeRaw'), 3), 'thrRaw': r1(V('ThrottleRaw'), 3),
        }
        soc = V('EnergyERSBatteryPct')
        if soc is not None:
            x['ers'] = {'soc': r1(soc, 3), 'mode': livello(V('dcMGUKDeployMode')), 'regen': livello(V('dcMGUKRegenGain')),
                        'kw': r1((V('PowerMGU_K', 0) or 0) / 1000.0, 0)}
        f['e'] = pulito(x)
        cflags = self._arr(buf, 'CarIdxSessionFlags')
        f['fl'] = pulito(bandiera_iracing(V('SessionFlags', 0), cflags[self.me] if self.me < len(cflags) else 0))
        f['pen'] = pulito({'inc': V('PlayerCarMyIncidentCount') if V('PlayerCarMyIncidentCount') is not None else V('PlayerCarDriverIncidentCount'),
                           'incMax': (lambda m: int(m.group(1)) if m else None)(re.search(r'IncidentLimit:\s*(\d+)', self.yaml))})
        wet = self._v(buf, 'TrackWetness', d=None)
        prec = self._v(buf, 'Precipitation', d=None)
        aria, asf = self._v(buf, 'AirTemp', d=None), self._v(buf, 'TrackTempCrew', d=None)
        if wet is not None or prec is not None or aria is not None:
            f['wx'] = {'wet': r1(max(0, (wet or 1) - 1) / 6.0, 2) if wet else None, 'rain': r1(prec, 2) if prec is not None else None,
                       'air': r1(aria, 1), 'road': r1(asf, 1), 'dich': 1 if self._v(buf, 'WeatherDeclaredWet', d=0) else 0,
                       'wind': r1(self._v(buf, 'WindVel', d=None), 1), 'windDir': r1((self._v(buf, 'WindDir', d=0) or 0) * DEG, 0) if self._v(buf, 'WindVel', d=None) else None,
                       'hum': r1(self._v(buf, 'RelativeHumidity', d=None), 2), 'rho': r1(self._v(buf, 'AirDensity', d=None), 3)}
        if any(p for p in pr if p):
            f['tp'] = [r1(p / 100.0, 3) if p else None for p in pr]      # kPa → bar
        if any(x for x in tm if x):
            f['tm'] = [r1(x) for x in tm]; f['ti'] = [r1(x) for x in ti]; f['to'] = [r1(x) for x in to]
            f['tt'] = f['tm']
        if any(w for w in wear if w):
            f['tw'] = [r1(1 - w, 3) if w else None for w in wear]
        rpm_max = None
        m = re.search(r'DriverCarRedLine:\s*([\d.]+)', self.yaml)
        if m:
            rpm_max = int(float(m.group(1)))
        f['rpmMax'] = rpm_max
        self.sessione['maxRpm'] = rpm_max
        self.sessione['fuelCap'] = r1(cap, 1)
        left = self._v(buf, 'SessionTimeRemain', d=None)
        self.sessione['left'] = int(left * 1000) if left and 0 < left < 1e6 else None
        # tutte le auto
        pcts = self._arr(buf, 'CarIdxLapDistPct')
        posz = self._arr(buf, 'CarIdxPosition')
        laps = self._arr(buf, 'CarIdxLapCompleted') or self._arr(buf, 'CarIdxLap')
        lasts = self._arr(buf, 'CarIdxLastLapTime')
        bests = self._arr(buf, 'CarIdxBestLapTime')
        pits = self._arr(buf, 'CarIdxOnPitRoad')
        auto = []
        for i, pc in enumerate(pcts):
            if pc is None or pc < 0 or i not in self.piloti:
                continue
            p = self.piloti[i]
            if p.get('n', '').lower() == 'pace car':
                continue
            auto.append({'id': i, 'n': p.get('n'), 'num': p.get('num'), 'cls': p.get('cls') or None, 'pct': r1(pc, 5),
                         'pos': (posz[i] if i < len(posz) else 0) or None, 'lap': laps[i] if i < len(laps) else None,
                         'last': int(lasts[i] * 1000) if i < len(lasts) and lasts[i] and lasts[i] > 0 else None,
                         'best': int(bests[i] * 1000) if i < len(bests) and bests[i] and bests[i] > 0 else None,
                         'pit': bool(pits[i]) if i < len(pits) else False, 'me': i == self.me})
        self.auto = auto
        return self.comune(f)


class LettoreAMS2(Lettore):
    gioco = 'ams2'
    nome = 'Automobilista 2'

    def __init__(self):
        super().__init__()
        self.m = None

    def apri(self):
        try:
            self.m = Mappa('$pcars2$')
            return True
        except OSError:
            return False

    def chiudi(self):
        if self.m:
            self.m.chiudi()
        self.m = None

    def leggi(self):
        for _ in range(3):                        # lettura coerente: numero di sequenza pari e uguale
            d = leggi_struct(self.m, ST.AMS2)
            if d.mSequenceNumber % 2 == 0:
                break
        if d.mGameState != 2:                     # solo in pista (non pausa, menu, replay): niente dati vecchi
            return None
        i = d.mViewedParticipantIndex
        if not (0 <= i < 64):
            return None
        p = d.mParticipantInfo[i]
        self.lun_pista = d.mTrackLength if d.mTrackLength > 100 else self.lun_pista
        self.n_settori = 3
        s1, s2, s3 = d.mCurrentSector1Time, d.mCurrentSector2Time, d.mCurrentSector3Time
        f = {
            'v': r1(d.mSpeed * 3.6), 'rpm': int(d.mRpm), 'rpmMax': int(d.mMaxRPM) or None, 'gear': int(d.mGear),
            'thr': r1(d.mThrottle, 3), 'brk': r1(d.mBrake, 3), 'clu': r1(d.mClutch, 3), 'str': r1(d.mSteering, 3),
            'fuel': r1(d.mFuelLevel * d.mFuelCapacity, 2), 'fuelCap': r1(d.mFuelCapacity, 1) or None,
            'latG': r1(d.mLocalAcceleration[0] / 9.81, 2), 'lonG': r1(-d.mLocalAcceleration[2] / 9.81, 2),
            'x': r1(p.mWorldPosition[0]), 'y': r1(p.mWorldPosition[2]), 'z': r1(p.mWorldPosition[1]),
            'pct': r1(p.mCurrentLapDistance / self.lun_pista, 5) if self.lun_pista else None,
            'dist': r1(p.mCurrentLapDistance), 'lap': int(p.mLapsCompleted),
            'cur': int(d.mCurrentTime * 1000) if d.mCurrentTime > 0 else None,
            'last': int(d.mLastLapTime * 1000) if d.mLastLapTime > 0 else None,
            'best': int(d.mBestLapTime * 1000) if d.mBestLapTime > 0 else None,
            'sec': int(p.mCurrentSector) if p.mCurrentSector >= 0 else None, 'pos': int(p.mRacePosition) or None,
            'pit': d.mPitMode != 0, 'valid': not d.mLapInvalidated,
            'bb': r1((1 - d.mBrakeBias) * 100, 1) if 0 < d.mBrakeBias < 1 else None,
            'tp': [pressione_bar(x) for x in d.mAirPressure],
            'tt': [r1(x) for x in d.mTyreTemp],
            'tw': [r1(x, 3) for x in d.mTyreWear],
            'bt': [r1(x) for x in d.mBrakeTempCelsius],
            'comp': txt(d.mTyreCompound[0]),
            'dmg': danni(corpo=d.mAeroDamage, motore=d.mEngineDamage, aero=d.mAeroDamage,
                         sosp=list(d.mSuspensionDamage), freni=list(d.mBrakeDamage)),
            'wx': {'rain': r1(d.mRainDensity, 2), 'air': r1(d.mAmbientTemperature, 1), 'road': r1(d.mTrackTemperature, 1),
                   'wind': r1(d.mWindSpeed, 1) or None, 'windDir': r1(math.degrees(math.atan2(d.mWindDirectionX, d.mWindDirectionY)) % 360, 0) if d.mWindSpeed else None},
        }
        f['e'] = pulito({
            'absA': 1 if d.mAntiLockActive else 0, 'abs': livello(d.mAntiLockSetting), 'tc': livello(d.mTractionControlSetting),
            'lim': 1 if (d.mCarFlags & 0x10) else 0, 'drs': (2 if d.mDrsState & 2 else 1 if d.mDrsState & 1 else 0) if d.mDrsState else None,
            'ers': {'soc': r1(d.mBoostAmount / 100.0, 3), 'mode': livello(d.mErsDeploymentMode), 'chg': None} if d.mBoostAmount > 0 else None,
            'yaw': r1(d.mAngularVelocity[1] * DEG, 1), 'pitch': r1(d.mOrientation[1] * DEG, 2), 'roll': r1(d.mOrientation[2] * DEG, 2),
            'vG': r1(d.mLocalAcceleration[1] / 9.81, 2), 'sus': lista(d.mSuspensionTravel, 1000.0, 1), 'rh': lista(d.mRideHeight, 1000.0, 1),
            'eng': {'wT': r1(d.mWaterTempCelsius) or None, 'oT': r1(d.mOilTempCelsius) or None,
                    'oP': r1(d.mOilPressureKPa / 100.0, 2) or None, 'fP': r1(d.mFuelPressureKPa / 100.0, 2) or None,
                    'boost': r1(d.mTurboBoostPressure / 100.0, 2) or None},
            'grip': lista(d.mTyreGrip, 1.0, 3),
        })
        f['fl'] = pulito({'f': BANDIERA_AMS2.get(int(d.mHighestFlagColour), 'none'),
                          'fcy': 1 if d.mYellowFlagState > 0 else None})
        if any(d.mTyreTempCenter):
            f['tm'] = [r1(x) for x in d.mTyreTempCenter]
            f['ti'] = [r1(d.mTyreTempRight[k] if k % 2 == 0 else d.mTyreTempLeft[k]) for k in range(4)]
            f['to'] = [r1(d.mTyreTempLeft[k] if k % 2 == 0 else d.mTyreTempRight[k]) for k in range(4)]
        self.sessione = {
            'k': 's', 'g': self.gioco, 'nome': self.nome, 'track': txt(d.mTrackLocation), 'cfg': txt(d.mTrackVariation),
            'trackLen': r1(self.lun_pista, 0) or None, 'car': txt(d.mCarName), 'cls': txt(d.mCarClassName),
            'driver': txt(p.mName), 'type': {1: 'P', 2: 'TEST', 3: 'Q', 4: 'FORM', 5: 'R', 6: 'TA'}.get(d.mSessionState, ''),
            'left': int(d.mEventTimeRemaining) if d.mEventTimeRemaining > 0 else None,
            'airT': r1(d.mAmbientTemperature), 'roadT': r1(d.mTrackTemperature), 'nsec': 3,
            'maxRpm': int(d.mMaxRPM) or None, 'fuelCap': r1(d.mFuelCapacity, 1) or None,
        }
        auto = []
        for k in range(max(0, min(d.mNumParticipants, 64))):
            q = d.mParticipantInfo[k]
            if not q.mIsActive:
                continue
            auto.append({'id': k, 'n': txt(q.mName), 'pos': int(q.mRacePosition) or None, 'lap': int(q.mLapsCompleted),
                         'pct': r1(q.mCurrentLapDistance / self.lun_pista, 5) if self.lun_pista else None,
                         'x': r1(q.mWorldPosition[0]), 'y': r1(q.mWorldPosition[2]), 'z': r1(q.mWorldPosition[1]),
                         'last': int(d.mLastLapTimes[k] * 1000) if d.mLastLapTimes[k] > 0 else None,
                         'best': int(d.mFastestLapTimes[k] * 1000) if d.mFastestLapTimes[k] > 0 else None,
                         'pit': d.mPitModes[k] != 0, 'car': txt(d.mCarNames[k]), 'cls': txt(d.mCarClassNames[k]) or None, 'me': k == i})
        self.auto = auto
        return self.comune(f)


def da_kelvin(x):
    """Kelvin → °C. Sotto i 100 K il gioco non ha il dato (0 K a gomme appena montate, nel garage…)."""
    return r1(x - 273.15) if isinstance(x, (int, float)) and x > 100 else None


class LettoreRF(Lettore):
    """Le Mans Ultimate (memoria propria "LMU_Data") e rFactor 2 (plugin di The Iron Wolf)."""

    @staticmethod
    def _extra_auto(q):
        try:
            return _extra_auto_rf(q)
        except Exception:
            return {}

    def __init__(self, lmu=True):
        super().__init__()
        self.lmu = lmu
        self.gioco = 'lmu' if lmu else 'rf2'
        self.nome = 'Le Mans Ultimate' if lmu else 'rFactor 2'
        self.m = self.mt = self.msc = None
        self.rf2 = None
        self.ultimo_last = {}
        self.giri.last_sincrono = True          # mLastLapTime e mTotalLaps si aggiornano insieme (scoring)

    def apri(self):
        try:
            if self.lmu:
                self.m = Mappa('LMU_Data')
            else:
                self.rf2 = ST.rf2()
                self.mt = Mappa('$rFactor2SMMP_Telemetry$')
                self.msc = Mappa('$rFactor2SMMP_Scoring$')
            return True
        except OSError:
            self.chiudi()
            return False

    def chiudi(self):
        for m in (self.m, self.mt, self.msc):
            if m:
                m.chiudi()
        self.m = self.mt = self.msc = None

    def _dati(self):
        if self.lmu:
            d = leggi_struct(self.m, ST.LMU)
            self._ffb = d.generic.FFBTorque         # uscita del force feedback (−1…1 = −100…100%)
            info = d.scoring.scoringInfo
            veic = [d.scoring.vehScoringInfo[i] for i in range(max(0, min(info.mNumVehicles, 104)))]
            tel = None
            if d.telemetry.playerHasVehicle:
                tel = d.telemetry.telemInfo[d.telemetry.playerVehicleIdx]
                me = next((v for v in veic if v.mIsPlayer), None)
                # quando entrano o escono altre auto l'indice può puntare per un attimo a un'altra macchina:
                # posizione, benzina e «giro non valido» di un altro → giri segnati come box per errore
                if me is not None and tel.mID != me.mID:
                    tel = next((d.telemetry.telemInfo[i] for i in range(min(104, max(d.telemetry.activeVehicles, 1)))
                                if d.telemetry.telemInfo[i].mID == me.mID), None)
            return info, veic, tel
        R = self.rf2
        for _ in range(3):
            T = leggi_struct(self.mt, R.rF2Telemetry)
            if T.mVersionUpdateBegin == T.mVersionUpdateEnd:
                break
        for _ in range(3):
            S = leggi_struct(self.msc, R.rF2Scoring)
            if S.mVersionUpdateBegin == S.mVersionUpdateEnd:
                break
        info = S.mScoringInfo
        veic = [S.mVehicles[i] for i in range(max(0, min(info.mNumVehicles, 128)))]
        me = next((v for v in veic if v.mIsPlayer), None)
        tel = None
        if me is not None:
            for i in range(max(0, min(T.mNumVehicles, 128))):
                if T.mVehicles[i].mID == me.mID:
                    tel = T.mVehicles[i]
                    break
        return info, veic, tel

    def leggi(self):
        info, veic, tel = self._dati()
        me = next((v for v in veic if v.mIsPlayer), None)
        if me is None or tel is None:
            return None
        if hasattr(info, 'mInRealtime') and not info.mInRealtime:
            return None                           # nel garage / sul monitor: la macchina non sta girando
        self.lun_pista = info.mLapDist if info.mLapDist > 100 else self.lun_pista
        self.n_settori = 3
        vel = tel.mLocalVel
        v = math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2) * 3.6
        sec_map = {1: 0, 2: 1, 0: 2}
        w = tel.mWheels
        cur = (info.mCurrentET - me.mLapStartET) if info.mCurrentET > me.mLapStartET else None
        # la telemetria va a ogni passo di fisica: tempo nel giro e distanza molto più precisi dello scoring
        et = getattr(tel, 'mElapsedTime', 0) or 0
        if et > 0 and 0 <= tel.mLapStartET <= et and et - tel.mLapStartET < 3600:
            cur = et - tel.mLapStartET
        dist = me.mLapDist
        if et > 0 and 0 <= et - info.mCurrentET < 0.5 and self.lun_pista:
            dist = min(self.lun_pista, max(0.0, me.mLapDist + v / 3.6 * (et - info.mCurrentET)))
        f = {
            'v': r1(v), 'rpm': int(tel.mEngineRPM), 'rpmMax': int(tel.mEngineMaxRPM) or None, 'gear': int(tel.mGear),
            'thr': r1(tel.mUnfilteredThrottle, 3), 'brk': r1(tel.mUnfilteredBrake, 3),
            'clu': r1(tel.mUnfilteredClutch, 3), 'str': r1(tel.mUnfilteredSteering, 3),
            'fuel': r1(tel.mFuel, 2), 'fuelCap': r1(tel.mFuelCapacity, 1) or None,
            'latG': r1(tel.mLocalAccel.x / 9.81, 2), 'lonG': r1(-tel.mLocalAccel.z / 9.81, 2),
            # posizione: quella della telemetria (a ogni passo di fisica). Quella dello scoring si aggiorna
            # solo 5 volte al secondo: la macchina sembrava ferma per 3 letture su 4 e poi «saltare»
            'x': r1(tel.mPos.x if (tel.mPos.x or tel.mPos.z) else me.mPos.x), 'y': r1(tel.mPos.z if (tel.mPos.x or tel.mPos.z) else me.mPos.z),
            'z': r1(tel.mPos.y if (tel.mPos.x or tel.mPos.z) else me.mPos.y),
            'pct': r1(dist / self.lun_pista, 5) if self.lun_pista else None, 'dist': r1(dist),
            'lap': int(me.mTotalLaps), 'cur': int(cur * 1000) if cur else None,
            'last': int(me.mLastLapTime * 1000) if me.mLastLapTime > 0 else None,
            'best': int(me.mBestLapTime * 1000) if me.mBestLapTime > 0 else None,
            'sec': sec_map.get(int(me.mSector)), 'pos': int(me.mPlace) or None, 'pit': bool(me.mInPits),
            'garage': bool(getattr(me, 'mInGarageStall', False)) or None,
            'bb': r1((1 - tel.mRearBrakeBias) * 100, 1) if 0 < tel.mRearBrakeBias < 1 else None,
            'tp': [r1(w[k].mPressure / 100.0, 3) if w[k].mPressure > 5 else None for k in range(4)],
            'tm': [da_kelvin(w[k].mTemperature[1]) for k in range(4)],
            'tt': [da_kelvin(w[k].mTireCarcassTemperature) for k in range(4)],
            'tw': [r1(1 - w[k].mWear, 3) for k in range(4)],
            'bt': [da_kelvin(w[k].mBrakeTemp) for k in range(4)],      # LMU/rF2: freni in Kelvin (come le gomme)
            'comp': txt(tel.mFrontTireCompoundName),
        }
        # mTemperature: sinistra/centro/destra del battistrada visto da dietro → interno/esterno per lato
        f['ti'] = [da_kelvin(w[k].mTemperature[2 if k % 2 == 0 else 0]) for k in range(4)]
        f['to'] = [da_kelvin(w[k].mTemperature[0 if k % 2 == 0 else 2]) for k in range(4)]
        if all(x is None for x in f['tt']):
            del f['tt']                           # la carcassa non arriva: meglio niente che -273 °C
        rng = getattr(tel, 'mPhysicalSteeringWheelRange', 0) or 0
        x = {
            'pl': r1(me.mPathLateral, 2), 'te': r1(abs(me.mTrackEdge), 2) if me.mTrackEdge else None,
            'sdeg': r1(tel.mUnfilteredSteering * rng / 2.0, 1) if rng > 0 else None,
            'lim': 1 if getattr(tel, 'mSpeedLimiterActive', tel.mSpeedLimiter) else 0,
            'drs': (2 if tel.mRearFlapActivated else 1 if tel.mRearFlapLegalStatus == 2 else 0) if tel.mRearFlapLegalStatus else None,
            'yaw': r1(tel.mLocalRot.y * DEG, 1), 'vG': r1(tel.mLocalAccel.y / 9.81, 2),
            'sus': [r1(w[k].mSuspensionDeflection * 1000, 1) for k in range(4)],
            'rh': [r1(w[k].mRideHeight * 1000, 1) for k in range(4)],
            'load': [r1(w[k].mTireLoad, 0) for k in range(4)], 'cam': [r1(w[k].mCamber * DEG, 2) for k in range(4)],
            'grip': [r1(w[k].mGripFract, 3) for k in range(4)],
            'sa': [r1(math.degrees(math.atan2(w[k].mLateralPatchVel, max(1.0, abs(w[k].mLongitudinalGroundVel)))), 2) for k in range(4)],
            'sr': [r1((w[k].mLongitudinalPatchVel) / max(1.0, abs(w[k].mLongitudinalGroundVel)), 3) for k in range(4)],
            'dfF': r1(tel.mFrontDownforce, 0), 'dfR': r1(tel.mRearDownforce, 0), 'drag': r1(tel.mDrag, 0),
            'rhF': r1(tel.mFrontRideHeight * 1000, 1), 'rhR': r1(tel.mRearRideHeight * 1000, 1),
            # canali in più: forze della gomma, convergenza dal vivo, tipo di superficie (cordolo, erba…), strati della gomma
            'fx': [r1(w[k].mLongitudinalForce, 0) for k in range(4)], 'fy': [r1(w[k].mLateralForce, 0) for k in range(4)],
            'ws': [r1(w[k].mRotation, 1) for k in range(4)], 'bp': [r1(w[k].mBrakePressure, 3) for k in range(4)],
            'sF': [r1(w[k].mSuspForce, 0) for k in range(4)], 'tdef': [r1(w[k].mVerticalTireDeflection * 1000, 1) for k in range(4)],
            'toe': [r1(getattr(w[k], 'mToe', 0) * DEG, 3) for k in range(4)] if hasattr(w[0], 'mToe') else None,
            'surf': [int(w[k].mSurfaceType) for k in range(4)], 'kerb': 1 if any(int(w[k].mSurfaceType) == 5 for k in range(4)) else 0,
            'fuori': 1 if any(int(w[k].mSurfaceType) in (2, 3, 4) for k in range(4)) else 0,
            'tin': [da_kelvin(sum(w[k].mTireInnerLayerTemperature) / 3.0) for k in range(4)] if hasattr(w[0], 'mTireInnerLayerTemperature') else None,
            'topt': da_kelvin(w[0].mOptimalTemp) if getattr(w[0], 'mOptimalTemp', 0) else None,
            'stTq': r1(tel.mSteeringShaftTorque, 2), 'engTq': r1(tel.mEngineTorque, 0), 'wingH': r1(tel.mFrontWingHeight * 1000, 1) if tel.mFrontWingHeight else None,
            'angv': [r1(tel.mLocalRot.x * DEG, 1), r1(tel.mLocalRot.y * DEG, 1), r1(tel.mLocalRot.z * DEG, 1)],
            'pitch': r1(math.degrees(math.atan2(tel.mOri[2].y, math.hypot(tel.mOri[2].x, tel.mOri[2].z))), 2),
            'roll': r1(math.degrees(math.atan2(tel.mOri[0].y, math.hypot(tel.mOri[0].x, tel.mOri[0].z))), 2),
            'impact': r1(tel.mLastImpactMagnitude, 0) if tel.mLastImpactMagnitude else None, 'cluRpm': int(tel.mClutchRPM),
            'h3': [r1(tel.mFront3rdDeflection * 1000, 1), r1(tel.mRear3rdDeflection * 1000, 1)] if (tel.mFront3rdDeflection or tel.mRear3rdDeflection) else None,
            'ffb': (r1(self._ffb * 100.0 if abs(self._ffb) <= 1.5 else self._ffb, 1) if getattr(self, '_ffb', None) else None) if self.lmu else None,
            'eng': {'wT': r1(tel.mEngineWaterTemp), 'oT': r1(tel.mEngineOilTemp), 'boost': r1(tel.mTurboBoostPressure / 100000.0, 2) or None},
        }
        if self.lmu:
            x.update({'tc': livello(tel.mTC, tel.mTCMax), 'tcMax': livello(tel.mTCMax) or None,
                      'tcCut': livello(tel.mTCCut, tel.mTCCutMax), 'tcCutMax': livello(tel.mTCCutMax) or None,
                      'tcSlip': livello(tel.mTCSlip, tel.mTCSlipMax), 'tcSlipMax': livello(tel.mTCSlipMax) or None,
                      'abs': livello(tel.mABS, tel.mABSMax), 'absMax': livello(tel.mABSMax) or None,
                      'map': livello(tel.mMotorMap, tel.mMotorMapMax), 'mapMax': livello(tel.mMotorMapMax) or None,
                      'mig': livello(tel.mMigration, tel.mMigrationMax), 'migMax': livello(tel.mMigrationMax) or None,
                      'arbF': livello(tel.mFrontAntiSway, tel.mFrontAntiSwayMax), 'arbFMax': livello(tel.mFrontAntiSwayMax) or None,
                      'arbR': livello(tel.mRearAntiSway, tel.mRearAntiSwayMax), 'arbRMax': livello(tel.mRearAntiSwayMax) or None,
                      'tcA': 1 if tel.mTCActive else 0, 'absA': 1 if tel.mABSActive else 0,
                      'lc': r1(tel.mLiftAndCoastProgress / 255.0, 2) if tel.mLiftAndCoastProgress else None,
                      'gapA': r1(tel.mTimeGapCarAhead, 3) or None, 'gapB': r1(tel.mTimeGapCarBehind, 3) or None,
                      'delta': int(tel.mDeltaBest * 1000) if tel.mDeltaBest else None})
            if tel.mElectricBoostMotorState or tel.mBatteryChargeFraction > 0 or tel.mVirtualEnergy > 0:
                x['ers'] = {'soc': r1(tel.mStateOfCharge if tel.mStateOfCharge > 0 else tel.mBatteryChargeFraction, 3),
                            've': r1(tel.mVirtualEnergy, 4) if tel.mVirtualEnergy > 0 else None,
                            # mRegen è la POTENZA di recupero in W (+ in frenata, − quando spinge: confrontato con la telemetria .duckdb di LMU), non un livello
                            'rkw': r1(tel.mRegen / 1000.0, 0),
                            'kw': r1(tel.mElectricBoostMotorTorque * tel.mElectricBoostMotorRPM * 2 * math.pi / 60000.0, 0),
                            'st': int(tel.mElectricBoostMotorState), 'chg': 1 if tel.mElectricBoostMotorState == 3 else 0,
                            'temp': r1(tel.mElectricBoostMotorTemperature) or None}
            if x.get('delta') is not None:
                f['delta'] = x['delta']
        f['e'] = pulito(x)
        if self.lmu:
            f['valid'] = not bool(tel.mLapInvalidated)
        dent = list(tel.mDentSeverity)
        f['dmg'] = danni(corpo=max(dent) if dent else 0, scala=2.0, motore=(0.5 if tel.mOverheating else 0),
                         sosp=[1.0 if (w[k].mDetached or w[k].mFlat) else 0.0 for k in range(4)], grezzo=dent)
        # LMU/rF2: pioggia, bagnato medio e sulla traiettoria (min) / fuori (max), nuvole scure (annunciano la pioggia), temperature
        f['wx'] = {'rain': r1(info.mRaining, 2), 'wet': r1(getattr(info, 'mAvgPathWetness', 0), 2),
                   'wetMin': r1(getattr(info, 'mMinPathWetness', 0), 2), 'wetMax': r1(getattr(info, 'mMaxPathWetness', 0), 2),
                   'cloud': r1(getattr(info, 'mDarkCloud', 0), 2), 'air': r1(info.mAmbientTemp, 1), 'road': r1(info.mTrackTemp, 1)}
        try:
            wv = info.mWind; ws = math.hypot(wv.x, wv.z)
            if ws > 0.05:
                f['wx']['wind'] = r1(ws, 1); f['wx']['windDir'] = r1(math.degrees(math.atan2(wv.x, wv.z)) % 360, 0)
        except AttributeError:
            pass
        try:
            yf = info.mYellowFlagState
            yf = ord(yf) if isinstance(yf, bytes) else int(yf)
        except (TypeError, ValueError):
            yf = 0
        sett = [int(s) == 1 for s in list(info.mSectorFlag)[:3]]
        fl = 'none'
        if info.mGamePhase == 8 or yf == 7:
            fl = 'red'
        elif info.mGamePhase == 9 or me.mFinishStatus == 1:
            fl = 'chequered'
        elif yf in (1, 2, 3, 4, 5) or info.mGamePhase == 6:
            fl = 'sc'
        elif int(me.mFlag) == 6:
            fl = 'blue'
        elif any(sett) or me.mUnderYellow:
            fl = 'yellow'
        elif info.mGamePhase == 5:
            fl = 'green'
        f['fl'] = pulito({'f': fl, 'sett': sett if any(sett) else None, 'motivo': FCY_RF.get(yf)})
        pen = {'n': int(me.mNumPenalties) if me.mNumPenalties > 0 else None}
        if self.lmu:
            passi = getattr(tel, 'mTrackLimitsSteps', 0)
            per_pen = getattr(info, 'mTrackLimitsStepsPerPenalty', 0)
            if per_pen:
                pen['tl'] = int(passi); pen['tlMax'] = int(per_pen)
        f['pen'] = pulito(pen)
        # tempi di settore ufficiali del giro appena chiuso
        if me.mLastLapTime > 0 and me.mLastSector1 > 0 and me.mLastSector2 > me.mLastSector1:
            f['_settori_ufficiali'] = [me.mLastSector1 * 1000, (me.mLastSector2 - me.mLastSector1) * 1000,
                                       (me.mLastLapTime - me.mLastSector2) * 1000]
        stipo = int(info.mSession)
        tipo = 'TEST' if stipo == 0 else 'P' if stipo <= 4 else 'Q' if stipo <= 8 else 'WU' if stipo == 9 else 'R'
        left = info.mEndET - info.mCurrentET if info.mEndET > 0 else None
        self.sessione = {
            'k': 's', 'g': self.gioco, 'nome': self.nome, 'track': txt(info.mTrackName), 'cfg': '',
            'trackLen': r1(self.lun_pista, 0) or None, 'car': txt(me.mVehicleName),
            'cls': txt(me.mVehicleClass), 'driver': txt(me.mDriverName), 'type': tipo,
            'model': txt(getattr(tel, 'mVehicleModel', b'')) or None,
            'left': int(left * 1000) if left and left > 0 else None, 'airT': r1(info.mAmbientTemp),
            'roadT': r1(info.mTrackTemp), 'nsec': 3, 'maxRpm': f['rpmMax'], 'fuelCap': f['fuelCap'],
        }
        auto = []
        for q in veic:
            auto.append({'id': int(q.mID), 'n': txt(q.mDriverName), 'car': txt(q.mVehicleName),
                         'cls': txt(q.mVehicleClass), 'pos': int(q.mPlace) or None, 'lap': int(q.mTotalLaps),
                         'pct': r1(q.mLapDist / self.lun_pista, 5) if self.lun_pista else None,
                         'x': r1(q.mPos.x), 'y': r1(q.mPos.z), 'z': r1(q.mPos.y),
                         'last': int(q.mLastLapTime * 1000) if q.mLastLapTime > 0 else None,
                         'best': int(q.mBestLapTime * 1000) if q.mBestLapTime > 0 else None,
                         'gap': r1(q.mTimeBehindLeader, 3), 'lapsDown': int(q.mLapsBehindLeader),
                         'pit': bool(q.mInPits), 'me': bool(q.mIsPlayer), **self._extra_auto(q)})
        self.auto = auto
        return self.comune(f)


def _sett3(s1, s2, giro):
    """rF2/LMU: settori cumulativi (s1, s1+s2, giro) → tre tempi in ms"""
    try:
        if not (s1 and s1 > 0 and s2 and s2 > s1 and giro and giro > s2):
            return None
        return [int(s1 * 1000), int((s2 - s1) * 1000), int((giro - s2) * 1000)]
    except TypeError:
        return None


def _extra_auto_rf(q):
    """dati in più di ogni avversario (LMU/rF2): velocità, settori, soste, penalità, benzina (LMU)"""
    v = math.sqrt(q.mLocalVel.x ** 2 + q.mLocalVel.y ** 2 + q.mLocalVel.z ** 2) * 3.6
    out = {'v': r1(v, 0), 'ls': _sett3(q.mLastSector1, q.mLastSector2, q.mLastLapTime),
           'bl': _sett3(getattr(q, 'mBestLapSector1', 0), getattr(q, 'mBestLapSector2', 0), q.mBestLapTime),
           'np': int(q.mNumPitstops), 'pen': int(q.mNumPenalties) or None}
    if hasattr(q, 'mFuelFraction'):
        out['fuel'] = r1(q.mFuelFraction / 255.0, 2)
    if hasattr(q, 'mDRSState') and q.mDRSState:
        out['drs'] = 1
    return out


class LettoreForza(Lettore):
    """Forza Motorsport: pacchetti UDP "Data Out" (formato Car Dash)."""
    gioco = 'forza'
    nome = 'Forza Motorsport'
    FMT_SLED = '<iI' + 'f' * 27 + 'i' * 4 + 'f' * 20 + 'i' * 5        # 232 byte
    FMT_DASH = '<' + 'f' * 17 + 'H' + 'B' * 6 + 'b' * 3                  # 79 byte

    def __init__(self, porta=5300):
        super().__init__()
        self.porta = porta
        self.sock = None
        self.ultimo = None
        self.t_ultimo = 0
        self.lap_d0 = None
        self.prec_lap = None

    def apri(self):
        if self.sock:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.porta))
            s.setblocking(False)
            self.sock = s
            return True
        except OSError:
            return False

    def chiudi(self):
        pass                                   # il socket resta aperto: Forza può ripartire

    def ricevi(self):
        """Svuota la coda UDP; True se c'è un pacchetto recente."""
        if not self.sock:
            return False
        try:
            while True:
                b, _ = self.sock.recvfrom(1024)
                if len(b) in (311, 324, 331):
                    self.ultimo = b
                    self.t_ultimo = ORA()
        except (BlockingIOError, OSError):
            pass
        return self.ultimo is not None and ORA() - self.t_ultimo < 2

    def leggi(self):
        if not self.ricevi():
            return None
        b = self.ultimo
        sled = struct.unpack_from(self.FMT_SLED, b, 0)
        off = 232 + (12 if len(b) == 324 else 0)            # Forza Horizon ha 12 byte in più in mezzo
        dash = struct.unpack_from(self.FMT_DASH, b, off)
        if not sled[0]:
            return None
        rpm_max, rpm = sled[2], sled[4]
        accx, accz = sled[5], sled[7]
        px, py, pz, speed, power, torque, t1, t2, t3, t4, boost, fuel, distanza, best, last, cur, race_t = dash[:17]
        lap_n, pos, acc, brk, clu, hb, gear, steer = dash[17], dash[18], dash[19], dash[20], dash[21], dash[22], dash[23], dash[24]
        wear = None
        if len(b) == 331:
            wear = list(struct.unpack_from('<4f', b, 311))
            track_ord = struct.unpack_from('<i', b, 327)[0]
        else:
            track_ord = None
        if self.prec_lap is None or lap_n != self.prec_lap:
            if self.prec_lap is not None and self.lap_d0 is not None and distanza - self.lap_d0 > 500:
                self.lun_pista = distanza - self.lap_d0
            self.lap_d0 = distanza
            self.prec_lap = lap_n
        dist = distanza - self.lap_d0 if self.lap_d0 is not None else None
        f = {
            'v': r1(speed * 3.6), 'rpm': int(rpm), 'rpmMax': int(rpm_max) or None, 'gear': int(gear) if gear < 11 else 0,
            'thr': r1(acc / 255.0, 3), 'brk': r1(brk / 255.0, 3), 'clu': r1(clu / 255.0, 3), 'str': r1(steer / 127.0, 3),
            'fuel': None, 'fuelPct': r1(fuel * 100, 1), 'latG': r1(accx / 9.81, 2), 'lonG': r1(accz / 9.81, 2),
            'x': r1(px), 'y': r1(pz), 'z': r1(py), 'dist': r1(dist), 'pct': r1(dist / self.lun_pista, 5) if (dist is not None and self.lun_pista) else None,
            'lap': int(lap_n), 'cur': int(cur * 1000) if cur > 0 else None, 'last': int(last * 1000) if last > 0 else None,
            'best': int(best * 1000) if best > 0 else None, 'sec': None, 'pos': int(pos) or None,
            'tt': [r1((t - 32) * 5 / 9) for t in (t1, t2, t3, t4)],
        }
        if wear:
            f['tw'] = [r1(w, 3) for w in wear]
        f['e'] = pulito({
            'yaw': r1(sled[12] * DEG, 1), 'pitch': r1(sled[15] * DEG, 2), 'roll': r1(sled[16] * DEG, 2),
            'sus': [r1(v * 1000, 1) for v in sled[49:53]], 'sr': [r1(v, 3) for v in sled[21:25]],
            'eng': {'boost': r1(boost * 0.0689476, 2) if boost else None},
            'kw': r1(power / 1000.0, 0) if power else None, 'nm': r1(torque, 0) if torque else None,
        })
        self.sessione = {'k': 's', 'g': self.gioco, 'nome': self.nome,
                         'track': ('Forza #%d' % track_ord) if track_ord else 'Forza', 'cfg': '',
                         'trackLen': r1(self.lun_pista, 0) or None, 'car': 'Auto #%d' % sled[-5], 'driver': '',
                         'nsec': 3, 'maxRpm': int(rpm_max) or None}
        self.auto = [{'id': 0, 'me': True, 'x': f['x'], 'y': f['y'], 'pos': f['pos'], 'lap': f['lap'],
                      'last': f['last'], 'best': f['best'], 'pct': f['pct']}]
        return self.comune(f)


class LettoreF1(Lettore):
    """F1 25 (EA / Codemasters): dati UDP del gioco (Impostazioni → Telemetria:
    UDP attivo, IP 127.0.0.1, porta 20777, formato 2025, frequenza 20 Hz).
    Specifica ufficiale «Data Output from F1 25» (v3): pacchetti little-endian,
    impaccati, intestazione di 29 byte, 22 auto. Si tengono gli ultimi pacchetti
    di ogni tipo e si costruisce il fotogramma quando arrivano telemetria e giri.
    Le ruote nel gioco sono nell'ordine RL, RR, FL, FR: qui diventano FL, FR, RL, RR."""
    gioco = 'f1'
    nome = 'F1 25'
    HDR = '<HBBBBBQfIIBB'                                                    # 29 byte
    CAR_MOT = 'ffffff' + 'h' * 6 + 'ffffff'                                 # 60 byte
    LAP = 'IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB'                               # 57 byte
    TEL = 'HfffBbHBBH' + 'HHHH' + 'BBBB' + 'BBBB' + 'H' + 'ffff' + 'BBBB'   # 60 byte
    STA = 'BBBBBfffHHBBHBBBbfffBfffB'                                       # 55 byte
    DMG = 'ffff' + 'B' * 4 * 3 + 'B' * 18                                    # 46 byte
    PART = 'BBBBBBB32sBBHBB12s'                                             # 57 byte
    SETUP = 'BBBBffffBBBBBBBBBffffBf'                                       # 50 byte
    SESS_TESTA = 'BbbBHBbBHHBBBBBB'                                         # dopo l'intestazione
    MEX = 'f' * 32 + 'f' + 'fff' * 3 + 'f' + 'ffff' + 'ff' + 'ff' + 'ff' + 'ffff' + 'ffff'
    PISTE = {0: 'Melbourne', 2: 'Shanghai', 3: 'Sakhir', 4: 'Catalunya', 5: 'Monaco', 6: 'Montreal', 7: 'Silverstone', 9: 'Hungaroring',
             10: 'Spa', 11: 'Monza', 12: 'Singapore', 13: 'Suzuka', 14: 'Abu Dhabi', 15: 'Austin', 16: 'Interlagos', 17: 'Red Bull Ring',
             19: 'Città del Messico', 20: 'Baku', 26: 'Zandvoort', 27: 'Imola', 29: 'Jeddah', 30: 'Miami', 31: 'Las Vegas', 32: 'Losail',
             39: 'Silverstone (inversa)', 40: 'Red Bull Ring (inversa)', 41: 'Zandvoort (inversa)'}
    SQUADRE = {0: 'Mercedes', 1: 'Ferrari', 2: 'Red Bull Racing', 3: 'Williams', 4: 'Aston Martin', 5: 'Alpine', 6: 'RB', 7: 'Haas', 8: 'McLaren', 9: 'Sauber'}
    MESCOLE = {16: 'C5', 17: 'C4', 18: 'C3', 19: 'C2', 20: 'C1', 21: 'C0', 22: 'C6', 7: 'Intermedia', 8: 'Bagnato', 9: 'Asciutto', 10: 'Bagnato',
               11: 'Supersoft', 12: 'Soft', 13: 'Medium', 14: 'Hard', 15: 'Bagnato'}
    SESSIONI = {1: 'P', 2: 'P', 3: 'P', 4: 'P', 5: 'Q', 6: 'Q', 7: 'Q', 8: 'Q', 9: 'Q', 10: 'Q', 11: 'Q', 12: 'Q', 13: 'Q', 14: 'Q',
                15: 'R', 16: 'R', 17: 'R', 18: 'TT'}
    PIOGGIA = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.3, 4: 0.7, 5: 1.0}
    ORD = (2, 3, 0, 1)                         # RL RR FL FR → FL FR RL RR

    def __init__(self, porta=20777):
        super().__init__()
        self.porta = porta
        self.sock = None
        self.p = {}
        self.t_ultimo = 0
        self.migliori = {}
        self.prec_lap = {}
        self.uid = None

    def apri(self):
        if self.sock:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.porta))
            s.setblocking(False)
            self.sock = s
            return True
        except OSError:
            return False

    def chiudi(self):
        pass

    def ricevi(self):
        if not self.sock:
            return False
        try:
            while True:
                b, _ = self.sock.recvfrom(2048)
                if len(b) < 29:
                    continue
                h = struct.unpack_from(self.HDR, b, 0)
                if h[0] != 2025:
                    continue
                if self.uid is not None and h[6] != self.uid:
                    self.p = {}; self.migliori = {}; self.prec_lap = {}
                self.uid = h[6]
                self.p[h[5]] = (h, b)
                self.t_ultimo = ORA()
        except (BlockingIOError, OSError):
            pass
        return 6 in self.p and 2 in self.p and ORA() - self.t_ultimo < 2

    @staticmethod
    def _ruote(v, scala=1.0, cifre=1):
        try:
            return [r1(v[i] * scala, cifre) for i in LettoreF1.ORD]
        except (TypeError, IndexError):
            return None

    def _auto(self, pid, fmt, i, base=29):
        c = self.p.get(pid)
        if not c:
            return None
        n = struct.calcsize('<' + fmt)
        try:
            return struct.unpack_from('<' + fmt, c[1], base + i * n)
        except struct.error:
            return None

    def setup_json(self):
        """Setup della TUA auto (pacchetto 5) come JSON leggibile: il programma lo mostra e lo confronta tra i giri."""
        if 5 not in self.p or 6 not in self.p:
            return None
        me = self.p[6][0][10]
        q = self._auto(5, self.SETUP, me)
        if not q or not any(q[:4]):
            return None
        nomi = ['frontWing', 'rearWing', 'diffOnThrottle', 'diffOffThrottle', 'frontCamber', 'rearCamber', 'frontToe', 'rearToe',
                'frontSuspension', 'rearSuspension', 'frontAntiRollBar', 'rearAntiRollBar', 'frontRideHeight', 'rearRideHeight',
                'brakePressure', 'brakeBias', 'engineBraking', 'tyrePressureRL', 'tyrePressureRR', 'tyrePressureFL', 'tyrePressureFR', 'ballast', 'fuelLoad']
        d = {}
        for k, v in zip(nomi, q):
            d[k] = round(v, 2) if isinstance(v, float) else v
        return json.dumps({'f1Setup': d}, indent=1)

    def leggi(self):
        if not self.ricevi():
            return None
        h = self.p[6][0]
        me = h[10]
        if me >= 22:
            return None
        tel, lap = self._auto(6, self.TEL, me), self._auto(2, self.LAP, me)
        if not tel or not lap:
            return None
        sta, mot, dmg = self._auto(7, self.STA, me), self._auto(0, self.CAR_MOT, me), self._auto(10, self.DMG, me)
        sess = None
        if 1 in self.p:
            try:
                sess = struct.unpack_from('<' + self.SESS_TESTA, self.p[1][1], 29)
            except struct.error:
                sess = None
        aiuti, prev = None, {}
        if sess:
            try:
                bs = self.p[1][1]
                st_, br_, gb_, pa_, pr_, ea_, da_, rl_ = struct.unpack_from('<BBBBBBBB', bs, 685)
                aiuti = [x for x in ['sterzo assistito' if st_ else None, {1: 'frenata assistita (bassa)', 2: 'frenata assistita (media)', 3: 'frenata assistita (alta)'}.get(br_),
                                     'cambio automatico' if gb_ == 3 else ('marcia suggerita' if gb_ == 2 else None), 'box assistito' if pa_ else None,
                                     'ERS assistito' if ea_ else None, 'DRS assistito' if da_ else None, 'traiettoria ideale' if rl_ else None] if x] or None
                n_prev = bs[155]
                tipo = sess[5]
                for k in range(min(64, n_prev)):
                    s_tipo, off, _m, _tt, _tc, _at, _ac, pioggia = struct.unpack_from('<BBBbbbbB', bs, 156 + k * 8)
                    if s_tipo == tipo and off in (10, 30) and off not in prev:
                        prev[off] = pioggia / 100.0
            except (struct.error, IndexError):
                pass
        lun = sess[4] if sess else 0
        if lun > 500:
            self.lun_pista = float(lun)
        spd, thr, steer, brk, clu, gear, rpm, drs = tel[0], tel[1], tel[2], tel[3], tel[4], tel[5], tel[6], tel[7]
        bt, ts, ti, tp, surf = tel[10:14], tel[14:18], tel[18:22], tel[23:27], tel[27:31]
        last, cur = lap[0], lap[1]
        dist, pos, lap_n, pit, sett, inval = lap[10], lap[13], lap[14], lap[15], lap[17], lap[18]
        if last and (lap_n - 1) != self.prec_lap.get(me) and not inval:
            self.migliori[me] = min(self.migliori.get(me, 10 ** 9), last)
        self.prec_lap[me] = lap_n - 1
        f = {
            'v': r1(spd), 'rpm': int(rpm), 'gear': max(0, int(gear)),
            'thr': r1(thr, 3), 'brk': r1(brk, 3), 'clu': r1(clu / 100.0, 3), 'str': r1(max(-1, min(1, steer)), 3),
            'x': r1(mot[0]) if mot else None, 'y': r1(mot[2]) if mot else None, 'z': r1(mot[1]) if mot else None,
            'latG': r1(mot[12], 2) if mot else None, 'lonG': r1(mot[13], 2) if mot else None,
            'dist': r1(dist) if dist >= 0 else None, 'pct': r1(dist / self.lun_pista, 5) if (dist >= 0 and self.lun_pista) else None,
            'lap': int(lap_n) - 1, 'cur': int(cur) if cur > 0 else None, 'last': int(last) if last > 0 else None,
            'best': int(self.migliori[me]) if me in self.migliori and self.migliori[me] < 10 ** 9 else None,
            'sec': int(sett), 'pos': int(pos) or None, 'valid': not inval, 'pit': pit > 0,
            'tt': self._ruote(ts), 'tm': self._ruote(ti), 'tp': [pressione_bar(tp[i]) for i in self.ORD], 'bt': self._ruote(bt, 1, 0),
        }
        if sta:
            f['fuel'] = r1(sta[5] / 0.74, 2)                 # il gioco dà la massa (kg): litri con densità 0,74
            f['fuelCap'] = r1(sta[6] / 0.74, 1) or None
            f['rpmMax'] = int(sta[8]) or None
            f['comp'] = self.MESCOLE.get(sta[13], str(sta[13]))
            f['bb'] = r1(sta[3], 1) if sta[3] else None
            f['fl'] = pulito({'f': {1: 'green', 2: 'blue', 3: 'yellow'}.get(sta[16])})
        if dmg:
            f['tw'] = self._ruote(dmg[0:4], 0.01, 3)
            f['dmg'] = danni(aero=max(dmg[16], dmg[17], dmg[18], dmg[19]) / 100.0, motore=dmg[25] / 100.0)
        lpen = {'tempo': lap[19] or None, 'tl': lap[21] or None}
        f['pen'] = pulito(lpen)
        e = {'drs': 2 if drs else (1 if sta and sta[11] else 0), 'kerb': 1 if any(x == 1 for x in surf) else 0}
        if sta:
            e.update({'tc': int(sta[0]), 'tcMax': 2, 'abs': int(sta[1]), 'absMax': 1, 'map': int(sta[2]), 'mapMax': 3, 'lim': int(sta[4]),
                      'ers': pulito({'soc': r1(sta[19] / 4.0e6, 3), 'mode': int(sta[20]), 'modeMax': 3, 'kw': r1(sta[18] / 1000.0, 0)})})
        if mot:
            e.update({'pitch': r1(mot[16] * DEG, 2), 'roll': r1(mot[17] * DEG, 2), 'vG': r1(mot[14], 2)})
        if 13 in self.p:
            try:
                mx = struct.unpack_from('<' + self.MEX, self.p[13][1], 29)
                e.update({'sus': self._ruote(mx[0:4], 1, 1), 'sr': self._ruote(mx[16:20], 1, 3), 'sa': self._ruote(mx[20:24], DEG, 2),
                          'yaw': r1(mx[37] * DEG, 1), 'sdeg': r1(mx[42] * DEG * 12.0, 1), 'sdegStima': 1, 'load': self._ruote(mx[43:47], 1, 0),
                          'rh': [r1(mx[47] * 1000, 1), r1(mx[48] * 1000, 1)]})
            except struct.error:
                pass
        f['e'] = pulito(e)
        if sess:
            meteo = sess[0]
            f['wx'] = pulito({'air': sess[2], 'road': sess[1], 'rain': self.PIOGGIA.get(meteo, 0.0), 'cloud': {1: 0.4, 2: 0.8}.get(meteo, 0.0 if meteo == 0 else 1.0),
                              'rain10': prev.get(10), 'rain30': prev.get(30)})
        # nomi e squadre
        nomi, squadre = {}, {}
        if 4 in self.p:
            for i in range(22):
                q = self._auto(4, self.PART, i, 30)
                if q:
                    nomi[i] = q[7].split(b'\x00')[0].decode('utf-8', 'replace').strip()
                    squadre[i] = self.SQUADRE.get(q[3], '')
        self.sessione = {'k': 's', 'g': self.gioco, 'nome': self.nome,
                         'track': self.PISTE.get(sess[6], 'Pista %d' % sess[6]) if sess else 'F1', 'cfg': '',
                         'trackLen': r1(self.lun_pista, 0) or None, 'car': ('F1 ' + squadre.get(me, '')).strip(), 'driver': nomi.get(me, ''),
                         'type': self.SESSIONI.get(sess[5], '') if sess else '', 'nsec': 3, 'maxRpm': f.get('rpmMax'), 'cls': 'F1',
                         'left': int(sess[8]) * 1000 if (sess and sess[8]) else None, 'airT': sess[2] if sess else None, 'roadT': sess[1] if sess else None,
                         'aiuti': aiuti, 'autoInfo': pulito({'rpm': f.get('rpmMax'), 'serbatoio': f.get('fuelCap')})}
        auto = []
        for i in range(22):
            q = self._auto(2, self.LAP, i)
            if not q or q[13] == 0 or q[26] in (0, 1):
                continue
            m = self._auto(0, self.CAR_MOT, i)
            if q[0] and (q[14] - 1) != self.prec_lap.get(i):
                self.migliori[i] = min(self.migliori.get(i, 10 ** 9), q[0])
                self.prec_lap[i] = q[14] - 1
            a = {'id': i, 'n': nomi.get(i) or ('Auto %d' % (i + 1)), 'pos': int(q[13]), 'lap': int(q[14]) - 1,
                 'pct': r1(q[10] / self.lun_pista, 5) if (q[10] >= 0 and self.lun_pista) else None,
                 'x': r1(m[0]) if m else None, 'y': r1(m[2]) if m else None, 'z': r1(m[1]) if m else None,
                 'last': int(q[0]) or None, 'best': int(self.migliori[i]) if self.migliori.get(i, 10 ** 9) < 10 ** 9 else None,
                 'gap': r1((q[8] + q[9] * 60000) / 1000.0, 3) if q[13] > 1 else None, 'pit': q[15] > 0, 'np': int(q[16]),
                 'cls': 'F1', 'car': squadre.get(i, ''), 'me': i == me}
            auto.append(a)
        self.auto = auto
        return self.comune(f)


class LettoreDemo(Lettore):
    """Gioco finto per provare tutto senza simulatore: un circuito di 2,4 km con
    sei curve, la tua auto e cinque avversari. Avvio: python ponte.py --demo

    Dalla 2.0 la demo è «fisica»: la velocità nasce da un profilo di frenate e
    accelerazioni curva per curva, e la posizione è la velocità integrata. Così
    la traccia del giro è coerente (freni prima, esci dopo) e l'analisi, il
    coach e l'ingegnere del setup hanno qualcosa di vero da trovare:
      - nei giri dispari la curva 2 è guidata male: frenata 20 m prima,
        un tratto senza pedali, 9 km/h in meno a centro curva;
      - in uscita dalla curva 4 il controllo di trazione interviene spesso;
      - l'auto sottosterza (deriva anteriore > posteriore) e la campanatura
        anteriore è troppa (interno gomma molto più caldo dell'esterno);
      - pressioni posteriori a caldo sopra la finestra;
      - elettronica completa (TC, ABS, mappa, ripartizione, migrazione, barre),
        batteria ibrida che si carica in frenata e si scarica in rettilineo.
    Il tempo sul giro resta quello chiesto (--demo-giro): la pista scorre più
    veloce del vero, ma velocità, forze G e comandi sono realistici."""
    gioco = 'demo'
    nome = 'DEMO (simulazione)'
    L = 2400.0
    # curve: (apice m, raggio m, velocità minima km/h, verso +1 destra / −1 sinistra)
    CURVE = [(180, 45, 92, 1), (560, 70, 118, -1), (900, 120, 150, 1), (1300, 38, 84, -1), (1760, 90, 132, 1), (2150, 55, 104, -1)]

    def __init__(self, durata_giro=48.0):
        super().__init__()
        self.t0 = ORA()
        self.giro_s = durata_giro
        self.lun_pista = self.L
        self.n_settori = 3
        self.fuel = 60.0
        pts = []
        for i in range(720):
            a = i / 720 * 2 * math.pi
            r = 380 + 90 * math.sin(3 * a) + 40 * math.cos(5 * a)
            pts.append((r * math.cos(a), r * 0.7 * math.sin(a)))
        self.pts = pts
        self.rivali = [('Marco Rossi', 1.012, 'GT3'), ('Luca Bianchi', 0.995, 'GT3'), ('Anna Verdi', 1.025, 'GT3'),
                       ('Paolo Neri', 1.04, 'GT3'), ('Giulia Gallo', 1.006, 'GT3'),
                       ('Jean Prototipo', 0.90, 'LMP2'), ('Kai Prototipo', 0.905, 'LMP2')]
        self.prof = {False: self._profilo(False), True: self._profilo(True)}
        # tempo "vero" del giro buono: la pista scorre più veloce per stare nel tempo chiesto
        self.t_vero = sum(1.0 / (v / 3.6) for v in self.prof[False]['v'])      # passo 1 m
        self.warp = self.t_vero / durata_giro
        self.s = 0.0
        self.laps = 0
        self.t_giro = ORA()
        self.t_prec = ORA()
        self.durate = []
        self.rif = 0.0
        self.giro_gomme = 0
        self.fermo_da = None
        self.fermo_fatto = False
        self.soc = 0.62
        self.ve = 1.0
        self.acqua = 82.0

    # ── profilo di velocità (passo 1 m): limite in curva, frenata 1,35 g, accelerazione ~0,55 g ──
    def _profilo(self, male):
        n = int(self.L)
        lim = [262.0] * n
        coast = [False] * n
        for k, (ap, R, vmin, _) in enumerate(self.CURVE):
            vm = vmin - (9 if (male and k == 1) else 0)
            for d in range(-25, 26):
                lim[(ap + d) % n] = min(lim[(ap + d) % n], vm + abs(d) * 0.5)
        v = lim[:]
        g = 9.81
        for _ in range(2):
            for i in range(1, 2 * n):                                  # accelerazione in avanti
                a, b = (i - 1) % n, i % n
                va = v[a] / 3.6
                acc = max(1.5, 0.62 * g - 0.00042 * va * va)
                v[b] = min(v[b], math.sqrt(va * va + 2 * acc) * 3.6)
            for i in range(2 * n, 0, -1):                              # frenata all'indietro
                a, b = i % n, (i - 1) % n
                dec = 1.35 * g
                v[b] = min(v[b], math.sqrt((v[a] / 3.6) ** 2 + 2 * dec) * 3.6)
        if male:                                                       # curva 2: frena 20 m prima e resta senza pedali
            ap = self.CURVE[1][0]
            inizio = None
            for d in range(ap - 200, ap):
                if v[d + 1] < v[d] - 0.05:
                    inizio = d; break
            if inizio:
                for d in range(inizio - 20, inizio):
                    coast[d] = True
                vv = v[inizio - 20]
                for d in range(inizio - 20, ap):
                    vv = max(v[d], vv - 0.28)
                    v[d] = min(v[d], vv)
        return {'v': v, 'coast': coast}

    def apri(self):
        return True

    @staticmethod
    def _quota(pct):
        """quota della pista demo (m): saliscendi dolce, per la vista 3D"""
        return 6.0 * math.sin(2 * math.pi * pct) + 2.5 * math.sin(6 * math.pi * pct + 1.0)

    def _pos(self, pct):
        i = pct * len(self.pts)
        a, b = self.pts[int(i) % len(self.pts)], self.pts[(int(i) + 1) % len(self.pts)]
        k = i - int(i)
        return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k

    def _curva(self, s):
        """curva più vicina: (indice, distanza con segno dall'apice, raggio, verso)"""
        best = None
        for k, (ap, R, vmin, ver) in enumerate(self.CURVE):
            d = (s - ap + self.L / 2) % self.L - self.L / 2
            if best is None or abs(d) < abs(best[1]):
                best = (k, d, R, ver)
        return best

    def leggi(self):
        ora = ORA()
        dt = min(0.25, ora - self.t_prec)
        self.t_prec = ora
        t = ora - self.t0
        male = self.laps % 2 == 1
        P = self.prof[male]
        i = int(self.s) % int(self.L)
        v = P['v'][i]
        v_prima = P['v'][(i - 3) % int(self.L)]
        v_dopo = P['v'][(i + 3) % int(self.L)]
        # sosta ai box alla fine del 4° giro: corsia a 60 km/h, 1,5 s fermi, 30 L e gomme nuove
        in_box = self.laps == 3 and self.s > self.L - 260
        fermo = False
        if in_box:
            v = 60.0
            if self.s > self.L - 120 and not self.fermo_fatto:
                if self.fermo_da is None:
                    self.fermo_da = ora
                if ora - self.fermo_da < 1.5:
                    fermo = True; v = 0.0
                else:
                    self.fermo_fatto = True
        if fermo and not self.rif:
            self.rif = 30.0; self.giro_gomme = 4
        self.s += (v / 3.6) * dt * self.warp
        if self.s >= self.L:
            self.s -= self.L
            self.durate.append(ora - self.t_giro)
            self.t_giro = ora
            self.laps += 1
        s = self.s
        pct = s / self.L
        k, dap, R, ver = self._curva(s)
        in_curva = abs(dap) < 45
        acc_long = (v_dopo - v_prima) / 3.6 * (v / 3.6) / 6.0 / 9.81 if v > 5 else 0.0     # g
        frena = acc_long < -0.25 and not P['coast'][i]
        brk = min(1.0, max(0.0, -acc_long / 1.35)) if frena else 0.0
        if brk and in_curva and dap > -8:
            brk *= max(0.0, 1 + dap / 8.0)           # rilascio progressivo verso l'apice (trail braking)
        thr = 0.0 if (frena or P['coast'][i]) else (1.0 if acc_long > 0.02 or v > 255 else 0.35)
        if in_curva and dap > 0 and not frena:
            thr = min(1.0, 0.3 + dap / 45.0)
        lat = ((v / 3.6) ** 2 / R / 9.81) * max(0.0, 1 - abs(dap) / 45.0) * ver if in_curva else 0.0
        sdeg = ver * max(0.0, 1 - abs(dap) / 45.0) * (2600.0 / R) * (1.18 if in_curva else 1) if in_curva else math.sin(s / 37.0) * 1.5
        yaw = (v / 3.6) / R * DEG * ver * max(0.0, 1 - abs(dap) / 45.0) if in_curva else 0.0
        tcA = 1 if (k == 3 and 0 < dap < 60 and thr > 0.55 and (int(ora * 20) % 3 != 0)) else 0
        # sconnessioni ogni 400 m: l'auto oscilla — davanti ben smorzata, dietro RIMBALZA (smorzamento basso)
        if not hasattr(self, 'buca'):
            self.buca = {'t': -9.0, 'ult': -1}
        nb = sum(1 for bb in (300, 680, 1000, 1400, 1850, 2250) if self.s >= bb) + self.laps * 10   # sconnessioni nei rettilinei
        if nb != self.buca['ult']:
            self.buca = {'t': ora, 'ult': nb}
        tb = ora - self.buca['t']
        osc_f = 9.0 * math.exp(-0.45 * 2 * math.pi * 2.8 * tb) * math.sin(2 * math.pi * 2.8 * tb) if tb < 3 else 0.0
        osc_r = 9.0 * math.exp(-0.12 * 2 * math.pi * 2.2 * tb) * math.sin(2 * math.pi * 2.2 * tb) if tb < 5 else 0.0
        rum = math.sin(ora * 37.0) * 0.6
        absA = 1 if (brk > 0.85 and (k in (0, 3))) else 0
        # batteria: si carica in frenata, si scarica sopra i 180 km/h con il gas
        if brk > 0.2:
            self.soc = min(0.95, self.soc + 0.0022 * brk)
        elif thr > 0.95 and v > 180:
            self.soc = max(0.08, self.soc - 0.0016)
        self.ve = max(0.0, self.ve - 0.021 * (v / 3.6) * dt * self.warp / self.L)       # ~2,1% a giro
        self.acqua = min(96.0, self.acqua + 0.002)
        if not hasattr(self, 't_fuel'):
            self.t_fuel = 0.0
        self.t_fuel += dt / self.giro_s * 2.4
        self.fuel = max(0.0, 60.0 - self.t_fuel + self.rif)
        usura = 0.02 * (self.laps + pct - self.giro_gomme) if self.laps + pct >= self.giro_gomme else 0.0
        cur = int((ora - self.t_giro) * 1000)
        prec = self.durate[-1] if self.durate else None
        migl = min(self.durate) if self.durate else None
        x, y = self._pos(pct)
        # traiettoria: fuori in ingresso, dentro all'apice, fuori in uscita (pista larga 10 m).
        # Nei giri «guidati male» la curva 3 è presa da centro pista: ingresso stretto, apice largo.
        ax, ay = self._pos((pct - 0.002) % 1); bx, by = self._pos((pct + 0.002) % 1)
        tx, ty = bx - ax, by - ay; nt = math.hypot(tx, ty) or 1.0; tx, ty = tx / nt, ty / nt
        p0 = self._pos((pct - 0.012) % 1); p1 = self._pos((pct + 0.012) % 1)
        kap = (x - p0[0]) * (p1[1] - y) - (y - p0[1]) * (p1[0] - x)
        verso_in = 1.0 if kap > 0 else -1.0                   # interno curva = sinistra (+) o destra (−) della direzione di marcia
        fase = max(-1.0, min(1.0, dap / 60.0))
        u = 4.0 * math.cos(fase * math.pi) if abs(dap) < 80 else 0.0      # + verso l'interno
        if male and k == 2 and -60 < dap < 15:
            u = 0.5 if dap < -12 else 2.0
        lato = u * verso_in                                   # + = sinistra
        x, y = x - ty * lato, y + tx * lato
        carico = abs(lat)
        sa_f = 5.2 * carico / 1.6 if in_curva else 0.3      # sottosterzo: davanti deriva di più
        sa_r = 3.1 * carico / 1.6 if in_curva else 0.2
        sl = 1 if ver > 0 else -1
        f = {'v': r1(v), 'rpm': int(min(8400, 4200 + (v % 55) * 75)), 'rpmMax': 8500, 'gear': max(1, min(6, int(v / 45) + 1)),
             'thr': r1(thr, 3), 'brk': r1(brk, 3), 'clu': 0, 'str': r1(max(-1, min(1, sdeg / 270.0)), 3),
             'fuel': r1(self.fuel, 2), 'fuelCap': 120, 'latG': r1(lat, 2), 'lonG': r1(acc_long, 2),
             'x': r1(x), 'y': r1(y), 'z': r1(self._quota(pct), 2), 'pct': r1(pct, 5), 'dist': r1(s, 1), 'lap': self.laps, 'cur': cur,
             'last': int(prec * 1000) if prec else None, 'best': int(migl * 1000) if migl else None,
             'sec': min(2, int(pct * 3)), 'pos': 3, 'valid': True, 'bb': 56.0,
             'tp': [1.86, 1.87, 1.98, 1.99], 'tt': [88 + carico * 4, 89 + carico * 4, 84, 85],
             'tm': [86, 87, 85, 86], 'ti': [99, 100, 90, 91], 'to': [77, 78, 82, 83],
             'tw': [round(usura, 3), round(usura * 1.05, 3), round(usura * 0.75, 3), round(usura * 0.8, 3)],
             'bt': [520 + brk * 180, 525 + brk * 180, 380 + brk * 90, 385 + brk * 90],
             'comp': 'DHF' if self.giro_gomme == 0 else 'DHG', 'pit': in_box,
             'tset': 1 if self.giro_gomme == 0 else 2,
             'dmg': danni(corpo=(0.12 if self.laps + pct > 2.5 else 0.0), sosp=[0, 0.05 if self.laps + pct > 2.5 else 0, 0, 0]),
             'wx': {'rain': (0.35 if self.laps >= 5 else 0.0), 'wet': round(min(0.6, max(0.0, (self.laps + pct - 5) * 0.2)), 2),
                    # previsione come in ACC: tra 10 e 30 minuti; nuvole che si addensano prima della pioggia; asfalto che si raffredda
                    'rain10': 0.35 if self.laps + pct >= 4.0 else 0.0, 'rain30': 0.35 if self.laps + pct >= 3.0 else 0.0,
                    'cloud': round(min(1.0, max(0.0, (self.laps + pct - 2) * 0.3)), 2),
                    'air': 22.0, 'road': round(31.0 - min(8.0, max(0.0, (self.laps + pct - 5) * 3.0)), 1),
                    'wind': 3.2, 'windDir': 220, 'hum': 0.55, 'rho': 1.18}}
        # bandiere: blu quando un avversario più veloce arriva (giro 2), gialla nel settore 2 al giro 3,
        # avvertimenti limiti pista (1 al giro 1, 2 al giro 3) e un drive-through al giro 6
        fl = 'green'
        sett = None
        if self.laps == 2 and 0.3 < pct < 0.45:
            fl = 'blue'
        if self.laps == 3 and 0.34 < pct < 0.66:
            fl = 'yellow'; sett = [False, True, False]
        f['fl'] = pulito({'f': fl, 'sett': sett})
        f['pen'] = pulito({'tl': (1 if self.laps >= 1 else 0) + (1 if self.laps >= 3 else 0), 'tlMax': 4,
                           'tipo': 'Drive-through (taglio)' if self.laps == 6 else None, 'n': 1 if self.laps >= 6 else None})
        f['e'] = pulito({
            'sdeg': r1(sdeg, 1), 'tc': 3, 'tcMax': 11, 'tcCut': 2, 'tcCutMax': 11, 'abs': 2, 'absMax': 11, 'map': 1, 'mapMax': 4,
            'mig': 2, 'migMax': 5, 'arbF': 4, 'arbFMax': 8, 'arbR': 3, 'arbRMax': 8,
            'tcA': tcA, 'absA': absA, 'lim': 1 if in_box else 0,
            'yaw': r1(yaw, 1), 'pitch': r1(-acc_long * 0.6, 2), 'roll': r1(lat * 0.9, 2), 'vG': r1(1 + 0.05 * math.sin(s), 2),
            'sus': [r1(28 + brk * 14 + max(0, lat) * 6 + osc_f + rum, 1), r1(28 + brk * 14 + max(0, -lat) * 6 + osc_f + rum, 1),
                    r1(34 + thr * 5 + max(0, lat) * 6 + osc_r + rum, 1), r1(34 + thr * 5 + max(0, -lat) * 6 + osc_r + rum, 1)],
            # in frenata dopo il rettilineo l'anteriore tocca quasi terra
            'rh': [r1(max(0.5, 26 - brk * 16 - (v / 262.0) ** 2 * 10 - osc_f * 0.5), 1), r1(68 + brk * 6 - (v / 262.0) ** 2 * 12 - osc_r * 0.6, 1)],
            'sa': [r1(sa_f * sl, 2), r1(sa_f * sl, 2), r1(sa_r * sl, 2), r1(sa_r * sl, 2)],
            # TC: taglia con il posteriore che slitta appena il 5% (asciutto) → è l'elettronica a limitare; sul bagnato slitta davvero (17%)
            # C1: in frenata forte l'anteriore sinistra si blocca (-22%)
            'sr': [r1(-brk * (0.24 if (k == 0 and brk > 0.8) else 0.09), 3), r1(-brk * 0.09, 3),
                   r1(-brk * 0.07 + ((0.17 if self.laps >= 5 else 0.05) if tcA else thr * 0.03), 3), r1(-brk * 0.07 + ((0.17 if self.laps >= 5 else 0.05) if tcA else thr * 0.03), 3)],
            'load': [r1(3200 + brk * 1500 + osc_f * 60, 0), r1(3200 + brk * 1500 + osc_f * 60, 0), r1(3600 - brk * 900 + osc_r * 160, 0), r1(3600 - brk * 900 + osc_r * 160, 0)],
            'cam': [-3.4, -3.4, -2.6, -2.6],
            'ers': {'soc': r1(self.soc, 3), 've': r1(self.ve, 4), 'mode': 2, 'modeMax': 4, 'regen': 7,
                    'kw': r1(160 if (thr > 0.95 and v > 180 and self.soc > 0.1) else (-90 * brk), 0), 'chg': 1 if brk > 0.2 else 0},
            'eng': {'wT': r1(self.acqua, 1), 'oT': r1(self.acqua + 16, 1), 'oP': 4.6, 'boost': r1(1.2 + thr * 0.6, 2)},
            'dfF': r1(2.1 * (v / 3.6) ** 2, 0), 'dfR': r1(2.6 * (v / 3.6) ** 2, 0), 'drag': r1(0.55 * (v / 3.6) ** 2, 0),
            'mfd': {'fuel': 30.0, 'set': 2, 'p': [1.72, 1.72, 1.70, 1.70]},
            'pl': r1(lato, 2), 'te': 5.0,
            'fx': [r1(-brk * 4000 + thr * 1500, 0)] * 2 + [r1(-brk * 2500 + thr * 3000, 0)] * 2, 'fy': [r1(lat * 2500, 0)] * 4,
            'bp': [r1(brk * 0.95, 3)] * 2 + [r1(brk * 0.8, 3)] * 2, 'stTq': r1(sdeg / 90.0 * (1 + abs(lat)), 2),
            'grip': [r1(min(1.0, abs(lat) / 1.6 + brk * 0.6), 3)] * 2 + [r1(min(1.0, abs(lat) / 1.8 + thr * 0.3), 3)] * 2,
            'kerb': 1 if 0.70 < (pct % 1) < 0.72 else 0, 'tin': [92, 93, 88, 89], 'topt': 90.0,
            'ws': [r1(v / 3.6 / 0.34, 1)] * 4, 'engTq': r1(thr * 650, 0),
            'ffb': r1(max(-100.0, min(100.0, sdeg * 0.9 * (1 + abs(lat)))), 1),
        })
        # carico sulle ruote coerente con la corsa: davanti il tampone tocca a 40 mm, dietro a 43 mm
        su_ = f['e'].get('sus')
        if su_:
            f['e']['load'] = [r1(1200 + 70 * su_[k] + 320 * max(0.0, su_[k] - 40.0), 0) for k in (0, 1)] + \
                             [r1(900 + 85 * su_[k] + 380 * max(0.0, su_[k] - 43.0), 0) for k in (2, 3)]
        self.sessione = {'k': 's', 'g': 'demo', 'nome': self.nome, 'track': 'Circuito Demo', 'cfg': '', 'trackLen': int(self.L),
                         'car': 'GT3 Demo', 'cls': 'GT3', 'driver': 'Tu', 'type': 'R', 'left': int(max(0, 1800 - t) * 1000),
                         'airT': 22.0, 'roadT': 31.0, 'nsec': 3, 'maxRpm': 8500, 'fuelCap': 120, 'lapsTot': 45,
                         'aiuti': ['frizione automatica'], 'autoInfo': {'kw': 405, 'nm': 520, 'rpm': 8500, 'massa': 1300, 'serbatoio': 120}}
        io_prog = self.laps + pct
        auto = [{'id': 0, 'n': 'Tu', 'me': True, 'cls': 'GT3', 'x': f['x'], 'y': f['y'], 'pct': f['pct'], 'lap': self.laps, 'pos': 3,
                 'last': f['last'], 'best': f['best'], 'pit': in_box}]
        for k2, (nome, fatt, cls) in enumerate(self.rivali):
            tt = t / fatt
            pc = (tt % self.giro_s) / self.giro_s
            xx, yy = self._pos(pc)
            auto.append({'id': k2 + 1, 'n': nome, 'num': str(10 + k2), 'x': r1(xx), 'y': r1(yy), 'z': r1(self._quota(pc), 2), 'pct': r1(pc, 5),
                         'lap': int(tt // self.giro_s), 'last': int(self.giro_s * fatt * 1000), 'best': int(self.giro_s * fatt * 1000),
                         'me': False, 'cls': cls, 'pit': False, 'v': r1(150 + 60 * math.sin(pc * 2 * math.pi * 3) * 0.9 / fatt, 0),
                         'ls': [int(self.giro_s * fatt * 1000 * q_) for q_ in (0.31, 0.36, 0.33)], 'np': 0})
        ordine = sorted(auto, key=lambda a: -(a['lap'] + a['pct']))
        for n, a in enumerate(ordine):
            a['pos'] = n + 1
        f['pos'] = next(a['pos'] for a in auto if a['me'])
        self.auto = auto
        return self.comune(f)

    SETUP = {"carName": "demo_gt3", "basicSetup": {
        "tyres": {"tyreCompound": 0, "tyrePressure": [55, 55, 60, 60]},
        "alignment": {"camber": [4, 4, 6, 6], "toe": [38, 38, 44, 44], "staticCamber": [-3.4, -3.4, -2.6, -2.6],
                      "toeOutLinear": [0, 0, 0, 0], "casterLF": 10, "casterRF": 10, "steerRatio": 3},
        "electronics": {"tC1": 3, "tC2": 2, "abs": 2, "eCUMap": 1, "fuelMix": 0, "telemetryLaps": 0},
        "strategy": {"fuel": 60, "nPitStops": 1, "tyreSet": 0, "frontBrakePadCompound": 1, "rearBrakePadCompound": 1}},
        "advancedSetup": {
            "mechanicalBalance": {"aRBFront": 4, "aRBRear": 3, "wheelRate": [3, 3, 4, 4], "bumpStopRateUp": [4, 4, 4, 4],
                                  "bumpStopRateDn": [4, 4, 4, 4], "bumpStopWindow": [20, 20, 25, 25], "brakeTorque": 20, "brakeBias": 36},
            "dampers": {"bumpSlow": [10, 10, 8, 8], "bumpFast": [6, 6, 5, 5], "reboundSlow": [12, 12, 10, 10], "reboundFast": [7, 7, 6, 6]},
            "aeroBalance": {"rideHeight": [5, 5, 12, 12], "rodLength": [0, 0, 0, 0], "splitter": 0, "rearWing": 6, "brakeDuct": [3, 3]},
            "drivetrain": {"preload": 12}},
        "trackBopType": 1}


# ════════════════════════════════════════════════════════════════════════════
#  ACC: CLASSIFICA COMPLETA (nomi, giri, distacchi) dal "broadcasting" UDP.
#  Facoltativa: la memoria condivisa di ACC dà solo le posizioni sulla mappa.
# ════════════════════════════════════════════════════════════════════════════
def cartella_documenti():
    if IS_WIN:
        try:
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            if buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def acc_broadcasting_json():
    return os.path.join(cartella_documenti(), 'Assetto Corsa Competizione', 'Config', 'broadcasting.json')


def acc_config():
    p = acc_broadcasting_json()
    try:
        raw = open(p, 'rb').read()
        t = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') or b'\0' in raw[:10] else raw.decode('utf-8')
        return json.loads(t)
    except Exception:
        return None


def acc_configura():
    p = acc_broadcasting_json()
    cfg = acc_config() or {}
    if os.path.exists(p):
        try:
            import shutil
            shutil.copy(p, p + '.backup_rep')
        except Exception:
            pass
    cfg['updListenerPort'] = 9000
    cfg.setdefault('connectionPassword', 'asd')
    cfg.setdefault('commandPassword', '')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(json.dumps(cfg, indent=2).encode('utf-16'))
    return p


def classe_acc(modello=None, nome=''):
    """Categoria di un'auto ACC dal numero di modello (broadcasting) o dal nome del modello."""
    n = (nome or '').lower()
    if modello is not None:
        if 50 <= modello <= 61:
            return 'GT4'
        if 80 <= modello <= 86:
            return 'GT2'
        if modello in (9, 28):
            return 'CUP'
        if modello in (18, 29):
            return 'ST'
        if modello == 26:
            return 'CHL'
        if modello == 27:
            return 'TCX'
        return 'GT3'
    if 'gt4' in n:
        return 'GT4'
    if 'gt2' in n or '935' in n:
        return 'GT2'
    if 'cup' in n:
        return 'CUP'
    if 'challenge' in n:
        return 'CHL'
    if 'st_evo' in n or '_st' in n:
        return 'ST'
    if 'm2_cs' in n:
        return 'TCX'
    return 'GT3'


class ACCBroadcast:
    def __init__(self, porta, password):
        self.addr = ('127.0.0.1', porta)
        self.password = password
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setblocking(False)
        self.conn_id = None
        self.auto = {}            # carIndex → dati
        self.entry = {}
        self.pista_m = 0
        self.t_reg = 0
        self.t_entry = 0

    @staticmethod
    def _s(t):
        b = t.encode('utf-8')
        return struct.pack('<H', len(b)) + b

    def registra(self):
        msg = bytes([1, 4]) + self._s('Race Engineer Pro') + self._s(self.password) + struct.pack('<i', 250) + self._s('')
        try:
            self.s.sendto(msg, self.addr)
        except OSError:
            pass
        self.t_reg = ORA()

    def chiudi(self):
        try:
            if self.conn_id is not None:
                self.s.sendto(bytes([9]) + struct.pack('<i', self.conn_id), self.addr)
            self.s.close()
        except OSError:
            pass

    def passo(self):
        if self.conn_id is None and ORA() - self.t_reg > 3:
            self.registra()
        if self.conn_id is not None and ORA() - self.t_entry > 10:
            try:
                self.s.sendto(bytes([10]) + struct.pack('<i', self.conn_id), self.addr)
                self.s.sendto(bytes([11]) + struct.pack('<i', self.conn_id), self.addr)
            except OSError:
                pass
            self.t_entry = ORA()
        for _ in range(200):
            try:
                b, _ = self.s.recvfrom(65535)
            except (BlockingIOError, OSError):
                break
            try:
                self._msg(b)
            except Exception:
                pass

    def _msg(self, b):
        p = [1]
        def u8():
            v = b[p[0]]; p[0] += 1; return v
        def u16():
            v = struct.unpack_from('<H', b, p[0])[0]; p[0] += 2; return v
        def i32():
            v = struct.unpack_from('<i', b, p[0])[0]; p[0] += 4; return v
        def f32():
            v = struct.unpack_from('<f', b, p[0])[0]; p[0] += 4; return v
        def s():
            n = u16(); v = b[p[0]:p[0] + n].decode('utf-8', 'ignore'); p[0] += n; return v
        def lap():
            ms = i32(); u16(); u16(); n = u8(); spl = [i32() for _ in range(n)]
            inv = u8(); u8(); u8(); u8()
            spl = [None if (x == 2147483647 or x <= 0) else x for x in spl]
            return (None if ms == 2147483647 else ms), inv, spl
        t = b[0]
        if t == 1:                                    # esito registrazione
            cid = i32(); ok = u8()
            if ok:
                self.conn_id = cid
                self.t_entry = 0
                log('ACC: classifica completa collegata.')
        elif t == 3:                                  # aggiornamento di un'auto
            idx = u16(); u16(); u8(); u8()
            x = f32(); y = f32(); f32(); u8(); kmh = u16(); pos = u16(); u16(); u16(); spl = f32(); laps = u16(); delta = i32()
            best, _, bsp = lap(); last, linv, lsp = lap(); cur, _, _ = lap()
            a = self.auto.setdefault(idx, {})
            a.update({'pos': pos, 'lap': laps, 'pct': round(spl, 5), 'best': best, 'last': last, 'v': kmh,
                      # settori del giro migliore e dell'ultimo (per il confronto con gli altri)
                      'bl': bsp if any(bsp) else None, 'ls': lsp if any(lsp) else None, 'inv': 1 if linv else 0})
            a.update(self.entry.get(idx, {}))
        elif t == 6:                                  # dati di un'iscritto
            idx = u16(); modello = u8(); team = s(); num_ = i32(); u8(); cur_d = u8(); u16(); nd = u8()
            piloti = []
            for _ in range(nd):
                nome = s(); cogn = s(); s(); u8(); u16()
                piloti.append((nome + ' ' + cogn).strip())
            self.entry[idx] = {'n': piloti[cur_d] if cur_d < len(piloti) else (piloti[0] if piloti else ''), 'num': str(num_), 'team': team,
                               'cls': classe_acc(modello)}
        elif t == 5:                                  # dati pista
            i32(); s(); i32(); self.pista_m = i32()


# ════════════════════════════════════════════════════════════════════════════
#  SETUP DEI GIOCHI (solo lettura dei file che il gioco salva)
# ════════════════════════════════════════════════════════════════════════════
CARTELLE_EXTRA = []        # --cartella-setup "D:\\...\\UserData\\player\\Settings"


def librerie_steam():
    """Tutte le librerie di Steam (anche su altri dischi), da libraryfolders.vdf."""
    base = [os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Steam'),
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Steam')]
    try:
        import winreg
        for radice, chiave, nome in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                     (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
            try:
                with winreg.OpenKey(radice, chiave) as k:
                    base.insert(0, winreg.QueryValueEx(k, nome)[0].replace('/', '\\'))
            except OSError:
                pass
    except ImportError:
        pass
    libs = list(base)
    for b in base:
        vdf = os.path.join(b, 'steamapps', 'libraryfolders.vdf')
        try:
            for m in re.finditer(r'"path"\s*"([^"]+)"', open(vdf, encoding='utf-8', errors='replace').read()):
                libs.append(m.group(1).replace('\\\\', '\\'))
        except OSError:
            pass
    for d in 'CDEFGH':
        libs += [d + ':\\SteamLibrary', d + ':\\Steam', d + ':\\Program Files (x86)\\Steam', d + ':\\Games\\Steam']
    return libs


def cartelle_setup(gioco, lettore=None):
    doc = cartella_documenti()
    if gioco == 'acc':
        return [os.path.join(doc, 'Assetto Corsa Competizione', 'Setups')], ('.json',)
    if gioco == 'ac':
        return [os.path.join(doc, 'Assetto Corsa', 'setups')], ('.ini',)
    if gioco in ('lmu', 'rf2'):
        cand = list(CARTELLE_EXTRA)
        if gioco == 'lmu' and lettore is not None and getattr(lettore, 'm', None) is not None:
            try:
                d = leggi_struct(lettore.m, ST.LMU)
                for i in range(5):
                    q = txt(d.paths.p[i]).rstrip('\\/')
                    if not q:
                        continue
                    # il gioco dà le sue cartelle: UserData, player, ... → si risale fino a UserData
                    parti = re.split(r'[\\/]', q)
                    for k in range(len(parti), 0, -1):
                        if parti[k - 1].lower() == 'userdata':
                            cand.append(os.path.join(os.sep.join(parti[:k]) if not IS_WIN else '\\'.join(parti[:k]), 'player', 'Settings'))
                            break
                    cand.append(os.path.join(q, 'player', 'Settings'))
                    cand.append(os.path.join(q, 'Settings'))
            except Exception:
                pass
        nome = 'Le Mans Ultimate' if gioco == 'lmu' else 'rFactor 2'
        for lib in librerie_steam():
            cand.append(os.path.join(lib, 'steamapps', 'common', nome, 'UserData', 'player', 'Settings'))
        visti, out = set(), []
        for c in cand:
            k = os.path.normcase(os.path.abspath(c))
            if k not in visti:
                visti.add(k); out.append(c)
        return out, ('.svm',)
    return [], ()


def elenco_setup(gioco, lettore=None):
    radici, est = cartelle_setup(gioco, lettore)
    out = []
    for r in radici:
        if not os.path.isdir(r):
            continue
        for dirpath, _, files in os.walk(r):
            for fn in files:
                if fn.lower().endswith(est):
                    p = os.path.join(dirpath, fn)
                    rel = os.path.relpath(p, r)
                    parti = rel.split(os.sep)
                    try:
                        mt = os.path.getmtime(p)
                    except OSError:
                        mt = 0
                    if est == ('.svm',):
                        # Le Mans Ultimate / rFactor 2: Settings\<pista>\[...]\file.svm, l'auto è scritta DENTRO il file
                        auto = ''
                        try:
                            testa = open(p, 'rb').read(6000).decode('utf-8', 'replace')
                            m = re.search(r'VehicleClassSetting\s*=\s*"?([^"\r\n/]*)', testa)
                            auto = m.group(1).strip() if m else ''
                        except OSError:
                            pass
                        if not auto and len(parti) > 2:
                            auto = parti[1]
                        out.append({'id': len(out), 'nome': fn, 'percorso': rel, 'auto': auto, 'pista': parti[0] if len(parti) > 1 else '',
                                    'mt': int(mt * 1000), '_abs': p})
                        continue
                    out.append({'id': len(out), 'nome': fn, 'percorso': rel, 'auto': parti[0] if len(parti) > 2 else '',
                                'pista': parti[1] if len(parti) > 2 else (parti[0] if len(parti) > 1 else ''),
                                'mt': int(mt * 1000), '_abs': p})
    out.sort(key=lambda x: -x['mt'])
    for i, o in enumerate(out):
        o['id'] = i
    return out[:300]


def slug(s):
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


def leggi_testo(p, limite=400000):
    raw = open(p, 'rb').read()[:limite]
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def iracing_setup(yaml):
    """Il setup in uso sta nella sessione di iRacing (sezione CarSetup), aggiornato
    a ogni modifica fatta nel garage: lo si prende da lì, niente file .sto."""
    m = re.search(r'^CarSetup:\s*\n((?:[ \t]+.*\n?)+)', yaml or '', re.M)
    return ('CarSetup:\n' + m.group(1)) if m else None


def parole(s):
    return set(w for w in slug(s).split('_') if len(w) >= 3 and not w.isdigit())


# stessi circuiti, nomi diversi: quello del gioco («Circuit de la Sarthe») e quello della cartella («Le Mans»)
ALIAS_PISTE = {
    'lemans': ('sarthe', 'mans', 'lemans', 'le_mans'), 'imola': ('imola', 'enzo', 'dino'), 'portimao': ('portimao', 'algarve'),
    'cota': ('cota', 'americas', 'austin'), 'qatar': ('qatar', 'lusail', 'losail'), 'interlagos': ('interlagos', 'carlos', 'pace', 'paulo'),
    'spa': ('spa', 'francorchamps'), 'monza': ('monza',), 'sebring': ('sebring',), 'fuji': ('fuji',), 'bahrain': ('bahrain', 'sakhir'),
    'silverstone': ('silverstone',), 'paulricard': ('ricard', 'castellet', 'paulricard'), 'nurburgring': ('nurburgring', 'nordschleife'),
    'barcelona': ('barcelona', 'catalunya', 'montmelo'), 'daytona': ('daytona', 'daytonarc'), 'lagunaseca': ('laguna', 'lagunaseca', 'weathertech'),
    'longbeach': ('longbeach', 'long_beach', 'beach'), 'roadatlanta': ('atlanta', 'roadatlanta', 'michelin'), 'watkins': ('watkins', 'glen'),
    'vallelunga': ('vallelunga',), 'mugello': ('mugello',), 'zandvoort': ('zandvoort',), 'hockenheim': ('hockenheim',), 'redbull': ('spielberg', 'redbull'),
}


GENERICHE_PISTE = {'circuit', 'circuito', 'the', 'road', 'national', 'international', 'raceway', 'speedway', 'autodromo', 'park', 'grand', 'prix',
                   'track', 'motor', 'motorsport', 'ring', 'de', 'la', 'del', 'des', 'wec', 'endurance'}


def canone(s):
    """parole del nome + il nome «canonico» del circuito, per confrontare nomi diversi"""
    p = parole(s)
    sl = slug(s)
    out = set(p)
    for k, voci in ALIAS_PISTE.items():
        if any(v in p or (len(v) >= 5 and v in sl) for v in voci):
            out.add('#' + k)
    return out


def valore_svm(testo, *nomi):
    for n in nomi:
        m = re.search(r'^\s*' + n + r'\s*=\s*(-?\d+)', testo, re.M | re.I)
        if m:
            return int(m.group(1))
    return None


def scegli_svm(lista, sessione, f):
    """Le Mans Ultimate / rFactor 2: i setup stanno in Settings/<pista>/*.svm,
    tutte le auto insieme. Si tengono quelli della pista, poi quelli della TUA
    auto (riga VehicleClassSetting del file), poi quello che ha barre, TC, ABS e
    mappa uguali a quelli che hai in macchina adesso; a parità il più recente."""
    tr = canone(sessione.get('track')) | canone(sessione.get('cfg'))
    trs = slug(sessione.get('track'))
    def stessa(s):
        pi = slug(s.get('pista'))
        if not pi:
            return False
        if pi == trs or (len(pi) >= 4 and (pi in trs or trs in pi)):
            return True
        cb = canone(s.get('pista'))
        ka, kb = set(x for x in tr if x[0] == '#'), set(x for x in cb if x[0] == '#')
        if ka and kb:
            return bool(ka & kb)                     # circuito riconosciuto da entrambe le parti: decide il nome canonico
        return bool((tr - GENERICHE_PISTE) & (cb - GENERICHE_PISTE))
    pista = [s for s in lista if stessa(s)]
    if not pista:
        nomi = sorted(set(s.get('pista') for s in lista if s.get('pista')))
        return None, 'nessuna cartella dei setup corrisponde alla pista «%s» (cartelle trovate: %s)' % (sessione.get('track'), ', '.join(nomi[:25]) or 'nessuna')
    generiche = {'lmgt3', 'gt3', 'gte', 'hypercar', 'lmh', 'lmdh', 'lmp2', 'lmp3', 'gtp', 'car', 'evo', 'team', 'racing', 'motorsport'}
    car = (parole(sessione.get('car')) | parole(sessione.get('model'))) - generiche     # conta il modello, non la categoria
    for s in pista:
        try:
            s['_t'] = leggi_testo(s['_abs'], 60000)
        except OSError:
            s['_t'] = ''
        m = re.search(r'VehicleClassSetting\s*=\s*"?([^"\r\n/]*)', s['_t'])
        s['_car'] = m.group(1).strip() if m else (s.get('auto') or '')
        s['_c'] = len(car & (parole(s['_car']) - generiche)) if s['_car'] else 0
    top = max(s['_c'] for s in pista)
    if top > 0:
        cand = [s for s in pista if s['_c'] == top]
        motivo = 'il più recente per questa auto e pista'
    else:
        # nessun file nomina il tuo modello: si scartano solo quelli che nominano CHIARAMENTE un altro modello
        cand = [s for s in pista if not (parole(s['_car']) - generiche)]
        motivo = 'il più recente per questa pista (il file non dice il modello dell\'auto)'
        if not cand:
            # i file nominano auto che non riconosco: meglio mostrare il più recente della pista, dicendolo
            cand = pista
            motivo = ('il più recente per questa pista — ATTENZIONE: non riconosco l\'auto («%s» nel file, «%s» dal gioco): se non è il tuo, sceglilo dall\'elenco'
                      % (pista[0]['_car'] if pista else '', sessione.get('model') or sessione.get('car')))
    e = (f or {}).get('e') or {}
    if len(cand) > 1 and e:
        prove = (('arbF', ('FrontAntiSwaySetting',)), ('arbR', ('RearAntiSwaySetting',)),
                 ('tc', ('TractionControlMapSetting', 'TCSetting', 'TractionControlSetting')),
                 ('abs', ('AntilockBrakeSystemMapSetting', 'ABSSetting', 'AntilockBrakesSetting')),
                 ('map', ('EngineMixtureSetting', 'MotorMapSetting', 'EngineMapSetting')))
        def uguali(s):
            n = 0
            for k, nomi in prove:
                v = valore_svm(s['_t'], *nomi)
                if e.get(k) is not None and v is not None and v == e[k]:
                    n += 1
            return n
        for s in cand:
            s['_u'] = uguali(s)
        mx = max(s['_u'] for s in cand)
        if mx > 0:
            cand = [s for s in cand if s['_u'] == mx]
            motivo += ', con barre/elettronica uguali a quelle in macchina (%d valori)' % mx
    cand.sort(key=lambda s: -s['mt'])
    return cand[0], motivo


def scegli_setup(gioco, lettore, sessione, f):
    """Il setup che stai usando, tra quelli salvati: stessa auto e stessa pista;
    per ACC vince quello i cui valori di elettronica coincidono con quelli che il
    gioco mostra in questo momento; a parità, il più recente."""
    lista = elenco_setup(gioco, lettore)
    if not lista:
        return None, 'nessun setup salvato nelle cartelle del gioco'
    car, tr = slug(sessione.get('car')), slug(sessione.get('track'))
    def pesa(s):
        p = 0
        a, pi = slug(s.get('auto')), slug(s.get('pista'))
        if a and car and (a == car or a in car or car in a):
            p += 4
        if pi and tr and (pi == tr or pi in tr or tr in pi or pi.split('_')[0] == tr.split('_')[0]):
            p += 2
        return p
    for s in lista:
        s['_p'] = pesa(s)
    if gioco in ('lmu', 'rf2'):
        return scegli_svm(lista, sessione, f)
    migliore = max(s['_p'] for s in lista)
    if gioco in ('acc', 'ac') and migliore < 4:
        return None, 'nessun setup salvato per questa auto'
    cand = [s for s in lista if s['_p'] == migliore][:25]
    motivo = 'il più recente per questa auto e pista' if migliore >= 6 else ('il più recente per questa auto' if migliore >= 4 else 'il più recente per questa pista')
    e = (f or {}).get('e') or {}
    if gioco == 'acc' and len(cand) > 1 and e:
        def uguali(s):
            try:
                j = json.loads(leggi_testo(s['_abs']))
                el = (j.get('basicSetup') or {}).get('electronics') or {}
                n = 0
                if e.get('tc') is not None and el.get('tC1') == e['tc']:
                    n += 1
                if e.get('abs') is not None and el.get('abs') == e['abs']:
                    n += 1
                if e.get('map') is not None and el.get('eCUMap') in (e['map'], e['map'] - 1):
                    n += 1
                return n
            except Exception:
                return 0
        for s in cand:
            s['_u'] = uguali(s)
        top = max(s['_u'] for s in cand)
        if top > 0:
            cand = [s for s in cand if s['_u'] == top]
            motivo = 'TC, ABS e mappa uguali a quelli che hai in macchina adesso' if top == 3 else motivo + ', con l\'elettronica che coincide'
    cand.sort(key=lambda s: -s['mt'])
    return cand[0], motivo


# ════════════════════════════════════════════════════════════════════════════
#  SERVER: pagina per i telefoni (HTTP) + dati live (WebSocket), stessa porta
# ════════════════════════════════════════════════════════════════════════════
GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


class Client:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.lock = threading.Lock()
        self.vivo = True

    def invia(self, testo):
        dati = testo.encode('utf-8')
        n = len(dati)
        if n < 126:
            h = struct.pack('!BB', 0x81, n)
        elif n < 65536:
            h = struct.pack('!BBH', 0x81, 126, n)
        else:
            h = struct.pack('!BBQ', 0x81, 127, n)
        try:
            with self.lock:
                self.sock.sendall(h + dati)
            return True
        except OSError:
            self.vivo = False
            return False


class Server:
    def __init__(self, porta, solo_pc, ponte):
        self.porta = porta
        self.solo_pc = solo_pc
        self.ponte = ponte
        self.client = []
        self.lock = threading.Lock()
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(('127.0.0.1' if solo_pc else '0.0.0.0', porta))
        self.s.listen(16)
        threading.Thread(target=self._accetta, daemon=True).start()

    def _accetta(self):
        while True:
            try:
                c, addr = self.s.accept()
            except OSError:
                return
            threading.Thread(target=self._gestisci, args=(c, addr), daemon=True).start()

    def _gestisci(self, c, addr):
        try:
            c.settimeout(10)
            req = b''
            while b'\r\n\r\n' not in req and len(req) < 16384:
                pezzo = c.recv(4096)
                if not pezzo:
                    c.close(); return
                req += pezzo
            testa = req.split(b'\r\n\r\n', 1)[0].decode('latin-1')
            righe = testa.split('\r\n')
            percorso = righe[0].split(' ')[1] if len(righe[0].split(' ')) > 1 else '/'
            hdr = {}
            for r in righe[1:]:
                if ':' in r:
                    k, v = r.split(':', 1)
                    hdr[k.strip().lower()] = v.strip()
            if 'websocket' in hdr.get('upgrade', '').lower():
                chiave = hdr.get('sec-websocket-key', '')
                acc = base64.b64encode(hashlib.sha1((chiave + GUID).encode()).digest()).decode()
                c.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                           'Sec-WebSocket-Accept: %s\r\n\r\n' % acc).encode())
                c.settimeout(None)
                cl = Client(c, addr)
                with self.lock:
                    self.client.append(cl)
                log('Collegato:', addr[0], '(%d in tutto)' % len(self.client))
                self.ponte.benvenuto(cl)
                self._leggi_ws(cl)
                return
            self._http(c, percorso.split('?')[0])
        except Exception:
            pass
        try:
            c.close()
        except OSError:
            pass

    def _http(self, c, percorso):
        if percorso in ('/', '/index.html', '/mobile'):
            p = os.path.join(DIR, 'mobile.html')
            corpo = open(p, 'rb').read() if os.path.exists(p) else b'<h1>REP Sim Bridge</h1><p>mobile.html mancante</p>'
            tipo = 'text/html; charset=utf-8'
        elif percorso == '/stato':
            corpo = json.dumps(self.ponte.stato(), ensure_ascii=False).encode('utf-8')
            tipo = 'application/json; charset=utf-8'
        else:
            c.sendall(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            return
        c.sendall(('HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\n'
                   'Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n' % (tipo, len(corpo))).encode() + corpo)

    def _leggi_ws(self, cl):
        s = cl.sock
        buf = b''
        try:
            while cl.vivo:
                pezzo = s.recv(65536)
                if not pezzo:
                    break
                buf += pezzo
                while len(buf) >= 2:
                    b0, b1 = buf[0], buf[1]
                    op = b0 & 0x0f
                    n = b1 & 0x7f
                    p = 2
                    if n == 126:
                        if len(buf) < 4: break
                        n = struct.unpack('!H', buf[2:4])[0]; p = 4
                    elif n == 127:
                        if len(buf) < 10: break
                        n = struct.unpack('!Q', buf[2:10])[0]; p = 10
                    mask = None
                    if b1 & 0x80:
                        if len(buf) < p + 4: break
                        mask = buf[p:p + 4]; p += 4
                    if len(buf) < p + n:
                        break
                    dati = bytearray(buf[p:p + n])
                    buf = buf[p + n:]
                    if mask:
                        for i in range(len(dati)):
                            dati[i] ^= mask[i % 4]
                    if op == 8:
                        cl.vivo = False
                        break
                    if op == 9:
                        with cl.lock:
                            s.sendall(bytes([0x8A, len(dati)]) + bytes(dati))
                        continue
                    if op == 1:
                        try:
                            self.ponte.comando(cl, json.loads(dati.decode('utf-8')))
                        except Exception as e:
                            cl.invia(json.dumps({'k': 'err', 'msg': str(e)[:200]}))
        except OSError:
            pass
        cl.vivo = False
        with self.lock:
            if cl in self.client:
                self.client.remove(cl)
        try:
            s.close()
        except OSError:
            pass
        log('Scollegato:', cl.addr[0])

    def trasmetti(self, obj):
        if not self.client:
            return
        t = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        with self.lock:
            lista = list(self.client)
        for cl in lista:
            if not cl.invia(t):
                with self.lock:
                    if cl in self.client:
                        self.client.remove(cl)


def indirizzi_lan():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith('127.'))


# ════════════════════════════════════════════════════════════════════════════
#  PONTE: cerca il gioco, legge, trasmette
# ════════════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════════════
#  CONTROLLO DEI DATI — prima di mandare un valore al programma si controlla
#  che sia plausibile. Un canale fuori scala (struttura del gioco cambiata,
#  unità diverse, campo non usato da quell'auto) NON arriva al programma:
#  viene segnalato in 'sospetti' con il motivo, e il programma lo mostra nel
#  pannello 🩺 Controllo dati. Così un numero sbagliato non diventa un
#  consiglio sbagliato.
# ════════════════════════════════════════════════════════════════════════════
LIMITI = {                  # canale: (minimo, massimo, descrizione)
    'v': (0, 450, 'velocità'), 'rpm': (0, 25000, 'giri motore'), 'gear': (-1, 12, 'marcia'),
    'thr': (-0.02, 1.05, 'gas'), 'brk': (-0.02, 1.05, 'freno'), 'clu': (-0.02, 1.05, 'frizione'),
    'fuel': (0, 400, 'benzina'), 'latG': (-8, 8, 'G laterale'), 'lonG': (-8, 8, 'G longitudinale'),
    # superficie del battistrada: in un pattinamento o in un testacoda arriva anche a 250–300 °C per qualche istante
    'tp': (0.3, 4.0, 'pressioni gomme (bar)'), 'tt': (-30, 260, 'temperature gomme'), 'tm': (-30, 350, 'temperature gomme (centro)'),
    'ti': (-30, 350, 'temperature gomme (interno)'), 'to': (-30, 350, 'temperature gomme (esterno)'),
    'bt': (-30, 1300, 'temperature freni'), 'tw': (-0.01, 1.01, 'usura gomme'), 'bb': (20, 85, 'ripartizione freno'),
}
LIMITI_E = {
    'sdeg': (-1500, 1500, 'angolo volante'), 'yaw': (-500, 500, 'imbardata'), 'vG': (-6, 8, 'G verticale'),
    'sus': (-400, 400, 'corsa sospensioni (mm)'), 'rh': (-60, 600, 'altezza da terra (mm)'), 'load': (-500, 40000, 'carico ruote (N)'),
    'sr': (-5, 5, 'slittamento ruote'), 'sa': (-60, 60, 'angolo di deriva'), 'cam': (-15, 15, 'campanatura'),
}
# accelerazioni: oltre i limiti sono URTI (muro, contatto, cordolo alto, ritorno ai box), non dati letti male
IMPULSIVI = {'latG', 'lonG', 'e.vG', 'e.yaw'}
ASSENTI_T = ('tm', 'tt', 'ti', 'to', 'bt')
SOGLIA_SISTEMATICO = 0.01       # oltre l'1% delle letture fuori scala = dato letto male; sotto = casi rari, esclusi e basta


class Tamponi:
    """Quando la sospensione arriva sui tamponi (bumpstop), dal vivo.
    Nessun gioco lo manda nella memoria condivisa (ACC lo scrive solo nei file MoTeC). Si ricava così:
      • TARATO: se il programma ha letto un file .ld di ACC della stessa auto, conosce la corsa esatta a cui
        il tampone tocca (nel .ld il passaggio è netto: es. 28,2 mm davanti, 45 mm dietro) e la manda qui;
      • STIMATO: la forza sulla ruota (LMU: forza della molla; ACC/AC: carico sulla gomma) cresce in modo
        lineare con la corsa finché non tocca il tampone, poi cresce molto più in fretta. Si cerca quel
        «gomito» con una retta spezzata sui valori medi per millimetro di corsa.
    Valido per l'assetto in uso: cambiando altezza o corsa dei tamponi la soglia cambia (si ricalcola)."""
    MIN_PUNTI = 800

    def __init__(self):
        self.reset(None)
        self.tarate = {}                       # auto → [soglia mm ×4] dal file .ld

    def reset(self, auto):
        self.auto = auto
        self.camp = [[] for _ in range(4)]
        self.soglie = [None] * 4
        self.prove = [None] * 4
        self.t_calc = ORA(); self.prec = None; self.t_prec = None

    @staticmethod
    def chiave(auto):
        return re.sub(r'[^a-z0-9]', '', str(auto or '').lower())

    def tara(self, auto, soglie):
        if auto and soglie and len(soglie) == 4:
            self.tarate[self.chiave(auto)] = [float(x) if x is not None else None for x in soglie]

    @staticmethod
    def gomito(punti):
        """punti = [(corsa mm, forza N)]: soglia in mm o None"""
        if len(punti) < Tamponi.MIN_PUNTI:
            return None
        cs = sorted(p[0] for p in punti)
        lo, hi = cs[int(len(cs) * 0.02)], cs[int(len(cs) * 0.995) - 1]
        if hi - lo < 8:
            return None
        bins = {}
        for c, fz in punti:
            if lo <= c <= hi:
                bins.setdefault(int(math.floor(c)), []).append(fz)
        xs, ys, ws = [], [], []
        for b in sorted(bins):
            v = sorted(bins[b])
            if len(v) >= 5:
                xs.append(b + 0.5); ys.append(v[len(v) // 2]); ws.append(math.sqrt(len(v)))
        if len(xs) < 10:
            return None

        def mq(cols):                           # minimi quadrati pesati, con il sistema normale (2–3 incognite)
            n = len(cols)
            A = [[sum(ws[i] * cols[a][i] * cols[b][i] for i in range(len(xs))) for b in range(n)] for a in range(n)]
            y = [sum(ws[i] * cols[a][i] * ys[i] for i in range(len(xs))) for a in range(n)]
            for k in range(n):                  # Gauss
                p = max(range(k, n), key=lambda r_: abs(A[r_][k]))
                if abs(A[p][k]) < 1e-9:
                    return None, None
                A[k], A[p] = A[p], A[k]; y[k], y[p] = y[p], y[k]
                for r_ in range(k + 1, n):
                    f_ = A[r_][k] / A[k][k]
                    A[r_] = [A[r_][j] - f_ * A[k][j] for j in range(n)]; y[r_] -= f_ * y[k]
            c = [0.0] * n
            for k in reversed(range(n)):
                c[k] = (y[k] - sum(A[k][j] * c[j] for j in range(k + 1, n))) / A[k][k]
            sse = sum(ws[i] * (ys[i] - sum(c[a] * cols[a][i] for a in range(n))) ** 2 for i in range(len(xs)))
            return c, sse
        uno = [1.0] * len(xs)
        _, sse1 = mq([uno, xs])
        if sse1 is None:
            return None
        meglio = None
        for j in range(3, len(xs) - 3):
            x0 = xs[j]
            # il gomito deve essere «visto»: dati subito prima e subito dopo (se in mezzo c'è un buco, si aspetta)
            vicini = set(round(b_ + 0.5 - x0) for b_ in bins if len(bins[b_]) >= 2)
            if not {-1, 1, 2} <= vicini:
                continue
            # e lì la pendenza deve cambiare davvero (dopo almeno 1,5 volte quella di prima), non solo «in media»
            def loc(a_, b_):
                pp = [(b2 + 0.5, sorted(bins[b2])[len(bins[b2]) // 2]) for b2 in bins if len(bins[b2]) >= 2 and a_ <= b2 + 0.5 - x0 <= b_]
                if len(pp) < 2:
                    return None
                mx_ = sum(p[0] for p in pp) / len(pp); my_ = sum(p[1] for p in pp) / len(pp)
                dd = sum((p[0] - mx_) ** 2 for p in pp)
                return sum((p[0] - mx_) * (p[1] - my_) for p in pp) / dd if dd else None
            sp, sd_ = loc(-3.1, 0.1), loc(-0.1, 3.1)
            if sp is None or sd_ is None or sp <= 0 or sd_ < 1.5 * sp:
                continue
            c, sse = mq([uno, xs, [max(0.0, x - x0) for x in xs]])
            if c is None:
                continue
            if c[1] > 0 and c[2] > 1.0 * c[1] and (meglio is None or sse < meglio[0]):   # il tampone è almeno il doppio più rigido
                meglio = (sse, x0, c)
        if not meglio or meglio[0] > sse1 * 0.6:
            return None
        return round(meglio[1], 1)

    def passa(self, f, auto):
        x = f.get('e')
        if not isinstance(x, dict):
            return f
        sus = x.get('sus')
        if not sus or len(sus) != 4 or any(v is None for v in sus):
            return f
        if auto != self.auto:
            self.reset(auto)
        forza = x.get('sF') if x.get('sF') and any(x.get('sF')) else x.get('load')
        ora = ORA()
        v = f.get('v') or 0
        if forza and len(forza) == 4 and v > 50 and self.prec is not None and 0 < ora - self.t_prec < 0.3:
            dt = ora - self.t_prec
            for k in range(4):
                if forza[k] is None or self.prec[k] is None:
                    continue
                if abs(sus[k] - self.prec[k]) / dt < 40:          # sospensione quasi ferma: niente forza dell'ammortizzatore
                    cp = self.camp[k]; cp.append((sus[k], forza[k]))
                    if len(cp) > 8000:
                        del cp[:2000]
        self.prec = list(sus); self.t_prec = ora
        if ora - self.t_calc > 4:
            self.t_calc = ora
            for k in range(4):
                s_ = self.gomito(self.camp[k])
                # si accetta solo se due calcoli di fila (4 s di distanza, più dati) danno lo stesso valore
                if s_ is not None and self.prove[k] is not None and abs(s_ - self.prove[k]) <= 1.5:
                    self.soglie[k] = round((s_ + self.prove[k]) / 2.0, 1)
                self.prove[k] = s_
        tar = self.tarate.get(self.chiave(auto))
        sog = tar if tar else self.soglie
        if any(s_ is not None for s_ in sog):
            x['bump'] = [(1 if sus[k] >= sog[k] else 0) if sog[k] is not None else None for k in range(4)]
            x['bumpS'] = [r1(s_, 1) for s_ in sog]
            x['bumpFonte'] = 'file' if tar else 'stima'
        return f


class Verifica:
    def __init__(self):
        self.stat = {}          # canale → [min, max, somma, n, fuori, urti, assenti, esempio]
        self.sospetti = {}      # canale → motivo
        self.kelvin = {}        # canale → True se il gioco lo manda in Kelvin
        self.fermo = []         # letture a macchina ferma (per capire le unità)
        self.prec = None
        self.incroci = {'vpos': [], 'glat': []}
        self.t_inviato = 0
        self.pos = None         # ultima posizione CAMBIATA: (x, y, ts, somma velocità, n)

    def _conta(self, k, v, lim):
        s = self.stat.setdefault(k, [None, None, 0.0, 0, 0, 0, 0, None])
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            if x is None or not isinstance(x, (int, float)):
                continue
            s[3] += 1
            if not (lim[0] <= x <= lim[1]):
                if k in IMPULSIVI:
                    s[5] += 1
                else:
                    s[4] += 1
                    s[7] = ', '.join(str(y) for y in vals)
                continue
            if s[0] is None or x < s[0]:          # minimo e massimo solo dei valori buoni
                s[0] = x
            if s[1] is None or x > s[1]:
                s[1] = x
            s[2] += x

    def _fuori(self, v, lim):
        vals = v if isinstance(v, list) else [v]
        vals = [x for x in vals if isinstance(x, (int, float))]
        return bool(vals) and any(not (lim[0] <= x <= lim[1]) for x in vals)

    def _unita(self, f):
        """Freni e gomme in Kelvin? A macchina ferma devono stare vicino alla
        temperatura dell'aria: se stanno a 270–340 sono Kelvin."""
        # solo prima di partire la prima volta: dopo un pit i freni sono davvero a 300 °C
        if (f.get('v') or 0) > 20:
            self.mosso = True
        if (f.get('v') or 0) < 3 and not getattr(self, 'mosso', False):
            self.fermo.append({'bt': f.get('bt'), 'tm': f.get('tm') or f.get('tt')})
            self.fermo = self.fermo[-60:]
        if len(self.fermo) >= 20:
            for k in ('bt', 'tm'):
                if k in self.kelvin:
                    continue
                vv = [x for r in self.fermo for x in (r.get(k) or []) if isinstance(x, (int, float))]
                if len(vv) >= 20:
                    med = sorted(vv)[len(vv) // 2]
                    self.kelvin[k] = 265 < med < 345
                    if self.kelvin[k]:
                        log('Controllo dati: %s arrivano in Kelvin, li converto in °C' % ('freni' if k == 'bt' else 'gomme'))

    def _assenti(self, k, n):
        s = self.stat.setdefault(k, [None, None, 0.0, 0, 0, 0, 0, None])
        s[6] += n

    def passa(self, f):
        self._unita(f)
        if self.kelvin.get('bt') and f.get('bt'):
            f['bt'] = [r1(x - 273.15) if isinstance(x, (int, float)) else x for x in f['bt']]
        if self.kelvin.get('tm'):
            for k in ('tm', 'tt', 'ti', 'to'):
                if f.get(k):
                    f[k] = [r1(x - 273.15) if isinstance(x, (int, float)) else x for x in f[k]]
        sosp = {}
        e = f.get('e') or {}
        # dati assenti: 0 K (-273 °C) e 0 bar vogliono dire «il gioco non lo sta mandando» (pit, cambio gomme, garage)
        for k in ASSENTI_T:
            if isinstance(f.get(k), list):
                n0 = sum(1 for x in f[k] if isinstance(x, (int, float)) and x <= -250)
                if n0:
                    self._assenti(k, n0)
                    f[k] = [None if (isinstance(x, (int, float)) and x <= -250) else x for x in f[k]]
        if isinstance(f.get('tp'), list):
            n0 = sum(1 for x in f['tp'] if isinstance(x, (int, float)) and x <= 0.05)
            if n0:
                self._assenti('tp', n0)
                f['tp'] = [None if (isinstance(x, (int, float)) and x <= 0.05) else x for x in f['tp']]
        # sotto i 30 km/h slittamento e deriva non vogliono dire nulla (divisione per una velocità quasi zero)
        if (f.get('v') or 0) < 30:
            for k in ('sr', 'sa'):
                if k in e:
                    del e[k]
        def pulisci(d, k, lim, nome):
            v = d[k]
            self._conta(nome, v, lim)
            if not self._fuori(v, lim):
                return
            if nome in IMPULSIVI:
                f['urto'] = 1                      # questo istante non entra nelle analisi della dinamica
            if isinstance(v, list):
                nuovo = [x if (not isinstance(x, (int, float)) or lim[0] <= x <= lim[1]) else None for x in v]
                if nome not in IMPULSIVI:
                    sosp[nome] = '%s fuori scala su %d valori su %d (%s)' % (lim[2], sum(1 for x in v if isinstance(x, (int, float)) and not (lim[0] <= x <= lim[1])), len(v), ', '.join(str(x) for x in v))
                if all(x is None for x in nuovo):
                    del d[k]
                else:
                    d[k] = nuovo
            else:
                if nome not in IMPULSIVI:
                    sosp[nome] = '%s fuori scala (%s)' % (lim[2], v)
                del d[k]
        for k, lim in LIMITI.items():
            if k in f and f[k] is not None:
                pulisci(f, k, lim, k)
        for k, lim in LIMITI_E.items():
            if k in e and e[k] is not None:
                pulisci(e, k, lim, 'e.' + k)
        # controlli incrociati: la velocità dichiarata e quella misurata dagli spostamenti.
        # Si misura tra una posizione NUOVA e la precedente (alcuni giochi aggiornano la posizione
        # meno spesso della velocità) e con la velocità media nello stesso intervallo.
        if f.get('x') is not None and f.get('ts'):
            q = self.pos
            if q is None:
                self.pos = [f['x'], f['y'], f['ts'], f.get('v') or 0, 1]
            elif (f['x'], f['y']) == (q[0], q[1]):
                q[3] += f.get('v') or 0; q[4] += 1
            else:
                dt = (f['ts'] - q[2]) / 1000.0
                dist = math.hypot(f['x'] - q[0], f['y'] - q[1])
                vmed = (q[3] + (f.get('v') or 0)) / (q[4] + 1)
                if 0.02 < dt < 1.0 and vmed > 60 and dist < vmed / 3.6 * dt * 3 + 5:      # niente salti (ritorno ai box, reset)
                    self.incroci['vpos'].append(dist / dt * 3.6 / vmed)
                    self.incroci['vpos'] = self.incroci['vpos'][-200:]
                self.pos = [f['x'], f['y'], f['ts'], f.get('v') or 0, 1]
        # G laterale e imbardata: in curva devono andare d'accordo (ay ≈ v · r)
        if e.get('yaw') is not None and f.get('latG') is not None and (f.get('v') or 0) > 60 and abs(f['latG']) > 0.6:
            atteso = (f['v'] / 3.6) * math.radians(abs(e['yaw'])) / 9.81
            if atteso > 0.2:
                self.incroci['glat'].append(abs(f['latG']) / atteso)
                self.incroci['glat'] = self.incroci['glat'][-200:]
        self.prec = {'x': f.get('x'), 'y': f.get('y'), 'ts': f.get('ts')}
        for k, v in sosp.items():
            self.sospetti[k] = v
        if sosp:
            f['sospetti'] = sosp
        return f

    def rapporto(self):
        out = {'k': 'diag', 'canali': {}, 'sospetti': {}, 'rari': {}, 'kelvin': [k for k, v in self.kelvin.items() if v], 'incroci': {}}
        for k, s in self.stat.items():
            if s[3] or s[6]:
                buoni = s[3] - s[4] - s[5]
                quota = s[4] / s[3] if s[3] else 0
                out['canali'][k] = {'min': r1(s[0], 3), 'max': r1(s[1], 3), 'media': r1(s[2] / buoni, 3) if buoni > 0 else None, 'n': s[3],
                                    'fuori': s[4], 'urti': s[5], 'assenti': s[6], 'sistematico': quota > SOGLIA_SISTEMATICO}
                # fuori scala tante volte = dato letto male (da segnalare); poche volte = istanti particolari, esclusi e basta
                if s[4] and k in self.sospetti:
                    (out['sospetti'] if quota > SOGLIA_SISTEMATICO else out['rari'])[k] = self.sospetti[k] + ' — %d letture su %d (%.2f%%)' % (s[4], s[3], quota * 100)
        for k, v in self.incroci.items():
            if len(v) >= 30:
                med = sorted(v)[len(v) // 2]
                out['incroci'][k] = {'rapporto': r1(med, 2), 'ok': 0.75 < med < 1.33}
        return out


# ════════════════════════════════════════════════════════════════════════════
#  ARCHIVIO DEI GIRI SU DISCO (ponte 2.1): ogni giro, con la sua traccia, viene
#  scritto in Documenti\RaceEngineerPro\giri_sim anche se il programma è chiuso.
#  Quando il programma si collega, chiede i giri che non ha ancora e li archivia
#  (a pagine di 25 giri). Un file per giorno, gioco e pista (una riga JSON per
#  giro); i setup usati sono scritti una volta sola per file.
# ════════════════════════════════════════════════════════════════════════════
def aiuti_ac(st):
    """Aiuti attivi in AC / ACC (memoria statica): nomi brevi, per la tabella delle condizioni."""
    out = []
    try:
        if st.aidStability > 0: out.append('stabilità %d%%' % round(st.aidStability * 100))
        if st.aidAutoClutch: out.append('frizione automatica')
        if st.aidAutoBlip: out.append('doppietta automatica')
        if st.aidAllowTyreBlankets: out.append('termocoperte')
        if 0 < st.aidTireRate != 1: out.append('usura gomme ×%g' % round(st.aidTireRate, 2))
        if 0 < st.aidFuelRate != 1: out.append('consumo ×%g' % round(st.aidFuelRate, 2))
        if 0 <= st.aidMechanicalDamage < 1: out.append('danni %d%%' % round(st.aidMechanicalDamage * 100))
    except (AttributeError, TypeError):
        pass
    return out or None


def foto_giro(f, sessione):
    """Gomme, elettronica e condizioni alla fine del giro (servono al confronto di più giri)."""
    f = f or {}
    e = f.get('e') or {}
    wx = f.get('wx') or {}
    def q(v, n=1):
        try:
            return [None if x is None else round(float(x), n) for x in list(v)[:4]] if v else None
        except (TypeError, ValueError):
            return None
    return pulito({'ti': q(f.get('ti')), 'tm': q(f.get('tm') or f.get('tt')), 'to': q(f.get('to')), 'tp': q(f.get('tp'), 3),
                   'tw': q(f.get('tw'), 3), 'bt': q(f.get('bt'), 0), 'core': q(f.get('tt')) if f.get('tm') else None, 'inner': q(e.get('tin')), 'grip': q(e.get('grip'), 3),
                   'auto': (sessione or {}).get('autoInfo'),
                   'topt': e.get('topt'), 'comp': f.get('comp'), 'tc': e.get('tc'), 'abs': e.get('abs'), 'map': e.get('map'), 'bb': f.get('bb'),
                   'air': wx.get('air'), 'road': wx.get('road'), 'wet': max(wx.get('wet') or 0, wx.get('rain') or 0) or None,
                   'wind': wx.get('wind'), 'windDir': wx.get('windDir'), 'hum': wx.get('hum'), 'rho': wx.get('rho'), 'gripPista': wx.get('grip'),
                   'aiuti': sessione.get('aiuti') if sessione else None, 'pilota': (sessione or {}).get('driver'), 'sess': (sessione or {}).get('type')})


class Archivio:
    def __init__(self, cartella):
        self.cartella = cartella
        self.indice = []                 # [ts, file, n]
        self.setup_scritti = {}          # file -> set(firme)
        self.ok = False
        try:
            os.makedirs(cartella, exist_ok=True)
            pi = os.path.join(cartella, 'indice.json')
            if os.path.isfile(pi):
                self.indice = json.load(open(pi, encoding='utf-8'))
            self.ok = True
        except (OSError, ValueError):
            self.indice = []

    def info(self):
        return {'k': 'arch', 'n': len(self.indice), 'ultimo': max([x[0] for x in self.indice] or [0]), 'cartella': self.cartella}

    def salva(self, ev, sessione, f, setup):
        if not self.ok:
            return
        try:
            nome = '%s_%s_%s.jsonl' % (time.strftime('%Y-%m-%d'), slug(ev.get('g')) or 'gioco', slug(ev.get('track')) or 'pista')
            pf = os.path.join(self.cartella, nome)
            righe = []
            firma = None
            if setup and setup.get('testo'):
                firma = hashlib.md5(setup['testo'].encode('utf-8', 'replace')).hexdigest()[:16]
                fatte = self.setup_scritti.setdefault(nome, set())
                if firma not in fatte:
                    righe.append({'k': 'setupArch', 'firma': firma, 'nome': setup.get('nome'), 'testo': setup['testo']})
                    fatte.add(firma)
            r = dict(ev)
            r['sess'] = pulito({'g': ev.get('g'), 'track': ev.get('track'), 'car': ev.get('car'), 'driver': sessione.get('driver'),
                                'cls': sessione.get('cls'), 'trackLen': sessione.get('trackLen'), 'type': sessione.get('type')})
            r['gm'] = foto_giro(f, sessione)
            if firma:
                r['setupFirma'] = firma; r['setupNome'] = setup.get('nome')
            righe.append(r)
            with open(pf, 'a', encoding='utf-8') as fh:
                for x in righe:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')
            self.indice.append([ev.get('ts') or ms_ora(), nome, ev.get('n')])
            json.dump(self.indice, open(os.path.join(self.cartella, 'indice.json'), 'w', encoding='utf-8'))
        except OSError as e:
            log('Archivio giri non scritto:', e)

    def dopo(self, ts, quanti=25):
        """I giri archiviati dopo ts (in ordine), più i setup che servono a leggerli."""
        voci = sorted([x for x in self.indice if x[0] > ts], key=lambda x: x[0])
        resto = max(0, len(voci) - quanti)
        voci = voci[:quanti]
        per_file = {}
        for v in voci:
            per_file.setdefault(v[1], set()).add(v[0])
        out = []
        for nome, tss in per_file.items():
            setups = {}
            try:
                for ln in open(os.path.join(self.cartella, nome), encoding='utf-8'):
                    try:
                        o = json.loads(ln)
                    except ValueError:
                        continue
                    if o.get('k') == 'setupArch':
                        setups[o['firma']] = o
                    elif o.get('ts') in tss:
                        if o.get('setupFirma') in setups:
                            o['setupTesto'] = setups[o['setupFirma']]['testo']
                        out.append(o)
            except OSError:
                continue
        out.sort(key=lambda o: o.get('ts') or 0)
        return out, resto


class Ponte:
    HZ = 20

    def __init__(self, porta=8977, solo_pc=False, forza_porta=5300, registra=None, demo=False, f1_porta=20777, archivio=None):
        self.porta = porta
        self.archivio = Archivio(archivio) if archivio else None
        self.demo = demo
        self.forza = LettoreForza(forza_porta)
        self.f1 = LettoreF1(f1_porta)
        self.candidati = [LettoreEVO, LettoreAC, LettoreIRacing, lambda: LettoreRF(True), lambda: LettoreRF(False), LettoreAMS2]
        self.attivo = None
        self.ult_ricerca = 0
        self.server = Server(porta, solo_pc, self) if porta else None
        self.ult_f = None
        self.giri_emessi = []
        self.setup_cache = []
        self.registra = open(registra, 'a', encoding='utf-8') if registra else None
        self.t_reg = 0
        self.inviati = 0
        self.solo_pc = solo_pc
        self.verifica = Verifica()
        self.tamponi = Tamponi()
        self.diagnosi = None
        self.ultimo_diag = None
        self.setup_auto = None          # ultimo setup inviato da solo
        self.t_setup = 0
        self.firma_setup = None

    def nuova_sessione(self, a, f):
        """Altro gioco, pista, auto o tipo di sessione (o sessione ricominciata):
        tutto quello che il ponte ricorda della sessione di prima si butta, e il
        programma riceve 'nuova' per fare lo stesso. Niente dati fantasma."""
        s = a.sessione or {}
        chiave = (a.gioco, s.get('track'), s.get('car'), s.get('type'))
        prima = getattr(self, 'chiave_sess', None)
        lap = f.get('lap')
        ricomincia = prima == chiave and lap is not None and getattr(self, 'lap_prec', None) is not None and lap < self.lap_prec and lap <= 1
        self.lap_prec = lap
        if prima is None or not s.get('track'):
            if s.get('track'):
                self.chiave_sess = chiave
            return
        if chiave == prima and not ricomincia:
            return
        self.chiave_sess = chiave
        motivo = 'sessione ricominciata' if ricomincia else 'nuova sessione: ' + ' · '.join(str(x) for x in chiave if x)
        self.giri_emessi = []
        self.verifica = Verifica()
        self.tamponi.reset(None)          # assetto forse cambiato: la stima riparte (la taratura da file resta)
        self.firma_setup = None
        self.setup_auto = None
        self.ultimo_diag = None
        self.t_setup = 0
        if not ricomincia:
            a.giri.reset()
        self.trasmetti({'k': 'nuova', 'motivo': motivo, 'ts': ms_ora()})
        self.trasmetti(a.sessione)
        log('Dati azzerati:', motivo)

    def setup_automatico(self, forza=False):
        a = self.attivo
        if not a or not a.sessione or (ORA() - self.t_setup < 4 and not forza):
            return
        self.t_setup = ORA()
        msg = None
        try:
            if a.gioco == 'demo':
                testo = json.dumps(LettoreDemo.SETUP, indent=1)
                msg = {'nome': 'demo_gara.json', 'percorso': 'Circuito Demo/demo_gara.json', 'motivo': 'setup della demo', 'testo': testo, 'mt': 0}
            elif a.gioco == 'f1':
                testo = a.setup_json()
                if testo:
                    msg = {'nome': 'Setup in uso (F1 25)', 'percorso': '', 'motivo': 'letto dal gioco: è quello montato adesso', 'testo': testo, 'mt': 0}
            elif a.gioco == 'iracing':
                testo = iracing_setup(getattr(a, 'yaml', ''))
                if testo:
                    msg = {'nome': 'Setup in uso (garage iRacing)', 'percorso': '', 'motivo': 'letto dal gioco: è quello montato adesso', 'testo': testo, 'mt': 0}
            elif a.gioco in ('acc', 'ac', 'lmu', 'rf2') and getattr(self, 'setup_manuale', None) and self.setup_manuale[:2] == (a.sessione.get('car'), a.sessione.get('track')) and os.path.isfile(self.setup_manuale[2]):
                sm = self.setup_manuale
                msg = {'nome': sm[3], 'percorso': sm[4], 'motivo': 'scelto da te dall\'elenco', 'testo': leggi_testo(sm[2]), 'mt': int(os.path.getmtime(sm[2]) * 1000)}
            elif a.gioco in ('acc', 'ac', 'lmu', 'rf2'):
                s, motivo = scegli_setup(a.gioco, a, a.sessione, self.ult_f)
                if s:
                    msg = {'nome': s['nome'], 'percorso': s['percorso'], 'motivo': motivo, 'testo': leggi_testo(s['_abs']), 'mt': s['mt']}
                else:
                    radici, _ = cartelle_setup(a.gioco, a)
                    nessuno = {'k': 'setupAuto', 'nessuno': True, 'gioco': a.gioco, 'motivo': motivo,
                               'cartelle': [{'p': r, 'c': os.path.isdir(r)} for r in radici][:12], 'pista': a.sessione.get('track'), 'auto': a.sessione.get('car')}
                    firma = 'nessuno|' + motivo + '|' + str(a.sessione.get('track'))
                    if firma != self.firma_setup or forza:
                        self.firma_setup = firma
                        self.setup_auto = nessuno
                        self.trasmetti(nessuno)
                        log('Setup: %s' % motivo)
                    return
        except Exception as e:
            log('Setup automatico non letto:', e)
            return
        if not msg:
            return
        firma = hashlib.md5((msg['percorso'] + '|' + msg['testo']).encode('utf-8', 'replace')).hexdigest()
        if firma == self.firma_setup and not forza:
            return
        cambiato = self.firma_setup is not None
        self.firma_setup = firma
        msg.update({'k': 'setupAuto', 'gioco': a.gioco, 'auto': a.sessione.get('car'), 'pista': a.sessione.get('track'),
                    'cambiato': cambiato, 'ts': ms_ora()})
        self.setup_auto = msg
        self.trasmetti(msg)
        log('Setup %s: %s (%s)' % ('cambiato' if cambiato else 'in uso', msg['nome'], msg['motivo']))

    def stato(self):
        a = self.attivo
        return {'k': 'hello', 'bridge': VERSIONE, 'gioco': a.gioco if a else None, 'nome': a.nome if a else None,
                'sessione': a.sessione if a else None, 'ip': indirizzi_lan(), 'porta': self.porta,
                'solo_pc': self.solo_pc, 'giri': len(self.giri_emessi)}

    def benvenuto(self, cl):
        cl.invia(json.dumps(self.stato(), ensure_ascii=False))
        if self.attivo and self.attivo.sessione:
            cl.invia(json.dumps(self.attivo.sessione, ensure_ascii=False))
        if self.setup_auto:
            cl.invia(json.dumps(self.setup_auto, ensure_ascii=False))
        if self.ultimo_diag:
            cl.invia(json.dumps(self.ultimo_diag, ensure_ascii=False))
        if self.archivio and self.archivio.ok:
            cl.invia(json.dumps(self.archivio.info(), ensure_ascii=False))
        # gli ultimi giri (senza traccia) per chi si collega a sessione iniziata
        for g in self.giri_emessi[-60:]:
            h = dict(g); h.pop('traccia', None); h['storico'] = True
            cl.invia(json.dumps(h, ensure_ascii=False))

    def comando(self, cl, m):
        c = m.get('cmd')
        if c == 'ping':
            cl.invia(json.dumps({'k': 'pong', 't': m.get('t')}))
        elif c == 'setups':
            g = self.attivo.gioco if self.attivo else m.get('gioco')
            self.setup_cache = elenco_setup(g, self.attivo)
            cl.invia(json.dumps({'k': 'setups', 'gioco': g,
                                 'lista': [{k: v for k, v in s.items() if not k.startswith('_')} for s in self.setup_cache]},
                                ensure_ascii=False))
        elif c == 'setup':
            i = int(m.get('id', -1))
            if not (0 <= i < len(self.setup_cache)):
                raise ValueError('setup non trovato: richiedi di nuovo l\'elenco')
            s = self.setup_cache[i]
            # scelto a mano: da ora è «il setup in uso» per questa auto e pista (e lo si segue se cambia)
            if self.attivo and self.attivo.sessione:
                self.setup_manuale = (self.attivo.sessione.get('car'), self.attivo.sessione.get('track'), s['_abs'], s['nome'], s['percorso'])
            raw = open(s['_abs'], 'rb').read()[:400000]
            try:
                testo = raw.decode('utf-8')
            except UnicodeDecodeError:
                testo = raw.decode('latin-1')
            cl.invia(json.dumps({'k': 'setup', 'id': i, 'nome': s['nome'], 'auto': s['auto'], 'pista': s['pista'],
                                 'gioco': self.attivo.gioco if self.attivo else '', 'testo': testo}, ensure_ascii=False))
        elif c == 'msg':
            # chiamata dell'ingegnere (programma) → la ripetono tutti i telefoni collegati
            self.trasmetti({'k': 'msg', 'testo': str(m.get('testo', ''))[:300], 'cat': m.get('cat'), 'prio': int(m.get('prio') or 1), 'ts': ms_ora()})
        elif c == 'setupAuto':
            self.firma_setup = None
            self.setup_automatico(forza=True)
            if not self.setup_auto:
                cl.invia(json.dumps({'k': 'setupAuto', 'nessuno': True, 'gioco': self.attivo.gioco if self.attivo else None}))
        elif c == 'tamponi':
            # dal programma: soglie esatte lette da un file .ld di ACC per questa auto
            self.tamponi.tara(m.get('auto'), m.get('soglie'))
            cl.invia(json.dumps({'k': 'tamponi', 'ok': True, 'auto': m.get('auto')}))
        elif c == 'archivio':
            if not self.archivio:
                cl.invia(json.dumps({'k': 'archFine', 'resto': 0, 'n': 0}))
                return
            giri, resto = self.archivio.dopo(int(m.get('dopo') or 0), int(m.get('quanti') or 25))
            for g in giri:
                g['k'] = 'lapArch'
                cl.invia(json.dumps(g, ensure_ascii=False))
            cl.invia(json.dumps({'k': 'archFine', 'resto': resto, 'n': len(giri), 'ultimo': giri[-1].get('ts') if giri else None}))
        elif c == 'giro':
            n = m.get('n')
            for g in reversed(self.giri_emessi):
                if g['n'] == n:
                    cl.invia(json.dumps(g, ensure_ascii=False)); break

    def cerca(self):
        if self.demo:
            return LettoreDemo(self.demo if isinstance(self.demo, float) else 48.0)
        if self.forza.apri() and self.forza.ricevi():
            return self.forza
        if self.f1.apri() and self.f1.ricevi():
            return self.f1
        aperti = []
        for C in self.candidati:
            lt = C()
            if not lt.apri():
                continue
            try:
                if lt.leggi() is not None:            # gioco aperto e in pista: si prende subito
                    for x in aperti:
                        x.chiudi()
                    return lt
            except Exception:
                pass
            aperti.append(lt)
        # nessuno in pista: si tiene il primo trovato (menu, box) e lo si ricontrolla
        for x in aperti[1:]:
            x.chiudi()
        return aperti[0] if aperti else None

    def passo(self):
        if self.attivo is None:
            if ORA() - self.ult_ricerca < 2:
                return
            self.ult_ricerca = ORA()
            self.attivo = self.cerca()
            if self.attivo:
                self.verifica = Verifica()
                log('Gioco trovato:', self.attivo.nome)
                if self.attivo.gioco == 'acc':
                    cfg = acc_config()
                    if cfg and cfg.get('updListenerPort'):
                        self.attivo.bcast = ACCBroadcast(int(cfg['updListenerPort']), cfg.get('connectionPassword', ''))
                    else:
                        log('ACC: per nomi e distacchi degli avversari avvia il ponte una volta con --configura-acc')
                self.trasmetti(self.stato())
            return
        a = self.attivo
        try:
            if getattr(a, 'bcast', None):
                a.bcast.passo()
            f = a.leggi()
        except Exception as e:
            log('Lettura interrotta (%s): riprovo a cercare il gioco.' % e)
            f = None
            try:
                a.chiudi()
            except Exception:
                pass
            self.attivo = None
            self.trasmetti({'k': 'hello', 'bridge': VERSIONE, 'gioco': None})
            return
        if isinstance(a, (LettoreForza, LettoreF1)) and f is None and ORA() - a.t_ultimo > 5:
            self.attivo = None
            self.trasmetti({'k': 'hello', 'bridge': VERSIONE, 'gioco': None})
            return
        if f is None:
            if not getattr(self, 'fermo', False) and ORA() - getattr(self, 't_ultimo_dato', 0) > 2:
                self.fermo = True
                self.trasmetti({'k': 'fermo', 'motivo': 'non sei in pista (menu, garage, pausa o replay)', 'ts': ms_ora()})
            # fermo da un po' (menu o gioco chiuso): si torna a cercare, magari c'è un altro gioco
            if ORA() - getattr(self, 't_ultimo_dato', 0) > 15 and ORA() - self.ult_ricerca > 15:
                self.ult_ricerca = ORA()
                nuovo = self.cerca()
                if nuovo is not None and (nuovo.gioco != a.gioco):
                    try:
                        a.chiudi()
                    except Exception:
                        pass
                    self.attivo = nuovo
                    log('Gioco trovato:', nuovo.nome)
                    self.trasmetti(self.stato())
                elif nuovo is not None and nuovo is not a:
                    nuovo.chiudi()
            return
        # fotogramma fermo (gioco in pausa o nel menu ma la memoria resta piena): non si manda
        firma = (f.get('cur'), f.get('lap'), f.get('x'), f.get('y'), f.get('v'), f.get('rpm'))
        if firma == getattr(self, 'firma_f', None):
            if ORA() - getattr(self, 't_firma', ORA()) > 2.5:
                if not getattr(self, 'fermo', False):
                    self.fermo = True
                    self.trasmetti({'k': 'fermo', 'motivo': 'il gioco non manda dati nuovi (pausa, menu o garage)', 'ts': ms_ora()})
                    log('Dati fermi: gioco in pausa o nel menu')
                return
        else:
            self.firma_f = firma; self.t_firma = ORA()
            if getattr(self, 'fermo', False):
                self.fermo = False
                self.trasmetti({'k': 'vivo', 'ts': ms_ora()})
        self.t_ultimo_dato = ORA()
        self.nuova_sessione(a, f)
        f = self.verifica.passa(f)
        try:
            f = self.tamponi.passa(f, (a.sessione or {}).get('car'))
        except Exception as e_:
            log('tamponi:', e_)
        if ORA() - self.verifica.t_inviato > 5:
            self.verifica.t_inviato = ORA()
            self.ultimo_diag = self.verifica.rapporto()
            self.trasmetti(self.ultimo_diag)
            if self.diagnosi:
                try:
                    with open(self.diagnosi, 'w', encoding='utf-8') as fh:
                        json.dump({'gioco': a.gioco, 'sessione': a.sessione, 'controllo': self.ultimo_diag, 'ultimo_fotogramma': f}, fh, ensure_ascii=False, indent=1)
                except OSError:
                    pass
        ev = a.giri.aggiorna(f, a.lun_pista, a.n_settori)
        f.pop('_settori_ufficiali', None)
        self.ult_f = f
        self.trasmetti(f)
        self.inviati += 1
        if self.inviati % 10 == 1:
            self.trasmetti(a.sessione)
            self.trasmetti({'k': 'c', 'cars': a.auto})
        self.setup_automatico()
        if ev:
            ev['track'] = a.sessione.get('track'); ev['car'] = a.sessione.get('car'); ev['g'] = a.gioco
            self.giri_emessi.append(ev)
            if len(self.giri_emessi) > 200:
                self.giri_emessi.pop(0)
            if self.archivio:
                self.archivio.salva(ev, a.sessione or {}, f, self.setup_auto if (self.setup_auto and not self.setup_auto.get('nessuno')) else None)
            ev['gm'] = foto_giro(f, a.sessione or {})
            self.trasmetti(ev)
            log('Giro %s: %s%s%s' % (ev['n'], fmt_ms(ev['ms']), '' if ev['valid'] else '  (non valido)', ('  [box: %s]' % ev['perche']) if ev.get('perche') else ''))
        if self.registra and ORA() - self.t_reg > 1:
            self.t_reg = ORA()
            self.registra.write(json.dumps({'f': f, 's': a.sessione}, ensure_ascii=False) + '\n')
            self.registra.flush()

    def trasmetti(self, o):
        if self.server:
            self.server.trasmetti(o)

    def gira(self):
        periodo = 1.0 / self.HZ
        while True:
            t0 = ORA()
            try:
                self.passo()
            except Exception as e:
                log('Errore:', e)
                time.sleep(1)
            dt = periodo - (ORA() - t0)
            if dt > 0:
                time.sleep(dt)


def fmt_ms(ms):
    if not ms:
        return '—'
    return '%d:%06.3f' % (ms // 60000, (ms % 60000) / 1000.0)


def main():
    a = sys.argv[1:]
    def opz(nome, d=None):
        if nome in a:
            i = a.index(nome)
            return a[i + 1] if i + 1 < len(a) else d
        return d
    if '--configura-acc' in a:
        p = acc_configura()
        print('ACC configurato per mandare la classifica completa (porta 9000).')
        print('File:', p, '(la versione precedente è salvata accanto, .backup_rep)')
        print('Riavvia ACC se era aperto.')
        return
    diag_file = None
    if '--diagnosi' in a:
        diag_file = opz('--diagnosi', 'diagnosi_dati.json')
        if not diag_file or diag_file.startswith('--'):
            diag_file = 'diagnosi_dati.json'
    if opz('--cartella-setup'):
        CARTELLE_EXTRA.append(opz('--cartella-setup'))
    porta = int(opz('--porta', 8977))
    solo_pc = '--solo-pc' in a
    try:
        ponte = Ponte(porta, solo_pc, int(opz('--forza-porta', 5300)), opz('--registra'),
                      demo=(float(opz('--demo-giro', 48)) if '--demo' in a else False), f1_porta=int(opz('--f1-porta', 20777)),
                      archivio=None if '--senza-archivio' in a else (opz('--cartella-giri') or os.path.join(cartella_documenti(), 'RaceEngineerPro', 'giri_sim', 'demo' if '--demo' in a else '')))
    except OSError as e:
        print('Non riesco ad aprire la porta %d: %s' % (porta, e))
        print('Forse il ponte è già acceso in un\'altra finestra.')
        input('Premi Invio per chiudere…')
        return
    ponte.diagnosi = diag_file
    if diag_file:
        print('Controllo dati: il rapporto si aggiorna ogni 5 s in', os.path.abspath(diag_file))
    print('═' * 66)
    print('  REP SIM BRIDGE %s — ponte tra simulatori e Race Engineer Pro' % VERSIONE)
    print('═' * 66)
    print('  Programma sul PC:  linguetta 🎮 SIM in alto → COLLEGA (127.0.0.1:%d)' % porta)
    if not solo_pc:
        for ip in indirizzi_lan() or ['(nessuna rete trovata)']:
            print('  Telefono/tablet:   http://%s:%d   (stessa rete Wi-Fi)' % (ip, porta))
        print('  Se Windows chiede il permesso di rete: consenti su "Reti private".')
    print('  Forza Motorsport:  Data Out → IP 127.0.0.1, porta %s, formato Car Dash' % opz('--forza-porta', 5300))
    print('  F1 25:             Impostazioni → Telemetria → UDP attivo, IP 127.0.0.1, porta %s, formato 2025' % opz('--f1-porta', 20777))
    if ponte.archivio and ponte.archivio.ok:
        print('  Archivio giri:     %s (%d giri)' % (ponte.archivio.cartella, len(ponte.archivio.indice)))
    print('  Aspetto il gioco… (chiudi questa finestra per spegnere il ponte)')
    print('─' * 66)
    ponte.gira()


if __name__ == '__main__':
    main()
