# Race Engineer Pro — Manuale utente
### Software di ingegneria di pista per squadre corse · versione 20.14

---

## Cos'è

Race Engineer Pro trasforma un PC e uno o più telefoni in un banco da ingegnere di pista completo: cronometraggio con settori, telemetria live dalle vetture, video e audio dall'abitacolo, analisi dei giri, suggerimenti di assetto basati sulla dinamica del veicolo, magazzino gomme e ricambi, gestione del weekend di gara.

Non serve installare nulla: il programma è un unico file che si apre nel browser. I telefoni usano una pagina web da aggiungere alla schermata Home.

---

## Primo avvio (10 minuti)

1. **Apri il file** `race_engineer_pro_v20_14.html` con doppio clic. Si consiglia **Chrome o Edge**.
2. **Crea la tua vettura**: menu ⚙ → Parametri vettura. Inserisci almeno massa, passo, carreggiate, trazione. Sono i dati su cui si basano tutti i calcoli.
3. **Imposta il weekend**: pagina Programma → circuito, sessioni, orari.
4. **Fai un backup**: menu → ⬇ BACKUP COMPLETO. Prendi l'abitudine: è un file che ripristina tutto.

---

## I telefoni (trasmettitore)

Su ogni telefono che va in macchina:

1. Apri l'indirizzo del trasmettitore in **Safari** (iPhone) o **Chrome** (Android).
2. Tocca Condividi → **Aggiungi alla schermata Home**: da lì si apre come un'app.
3. Imposta il **NOME AUTO** (es. "CLIO 5"): è il nome che vedrai al box.
4. Sul PC: pagina Telemetria → **📡 ATTIVA RICEZIONE** → compare il **CODICE SQUADRA** di 6 caratteri.
5. Sul telefono: scrivi il codice → **CONNETTI** → **START**.

Tutti i telefoni della squadra usano lo **stesso codice**.

**Regola d'oro in macchina**: monta il telefono rigido al parabrezza, collega il caricabatterie e usa il pulsante **🔒 BLOCCA SCHERMO** dentro l'app — **mai il tasto laterale**, perché a schermo spento il sistema operativo congela la trasmissione.

---

## Le funzioni principali

### Cronometraggio e telemetria
Il telefono riconosce da solo il circuito, impara il traguardo al primo passaggio lanciato e lo ricorda per le volte successive. Da lì misura tempo sul giro, settori S1-S2-S3, giro teorico e **delta predittivo** (quanto sei avanti o indietro rispetto al tuo giro migliore, aggiornato in tempo reale). Il pilota lo vede grande sullo schermo bloccato; tu al box vedi tabella giri, mappa, velocità, accelerazioni.

### Video e audio dalla vettura
Premi 🎥 sul telefono una volta a inizio giornata (serve il consenso alla camera). Al box compare il riquadro con velocità, barre gas/freno stimate, tempo giro e delta in sovraimpressione. Se la rete non regge il video fluido, il sistema passa automaticamente a **fotogrammi** e torna al video appena può. Il telefono registra sempre anche in locale a piena qualità.

### Pit board digitale
Dal box invii messaggi al pilota (BOX, PUSH, GIALLA, RIENTRA o testo libero): compaiono giganti sullo schermo del telefono, con vibrazione.

### Telecomando
Dal PC accendi/spegni acquisizione dati, video e microfono di ogni vettura, senza toccare il telefono.

### Analisi
- **Analisi giro**: confronto tra due giri con il grafico di dove si guadagna e si perde.
- **Curve**: velocità minima in ogni curva, giro migliore contro ultimo giro.
- **Analisi Pro**: statistiche per settore, istogrammi, canali calcolati con formule tue, video sincronizzato con i dati.
- **Moviola e ghost**: rivedi la sessione sulla mappa; il "fantasma" del giro migliore corre insieme alla vettura vera.

### Assetto
Compili la scheda assetto e il software calcola trasferimenti di carico, rigidezze, rollio, bilanciamento e ti dice in che direzione muoverti per correggere sotto/sovrasterzo in ingresso, percorrenza e uscita. **I suggerimenti indicano direzione e ordine di grandezza**: vanno tarati sui dati misurati della tua vettura con le funzioni FIT µ e FIT CdA.

### Magazzino
Gomme e ricambi con scorte minime e storico. Dal telefono puoi scansionare il codice di un pezzo, compilare nome, categoria e quantità, e il pezzo entra da solo nel magazzino del PC.

### Report
A fine giornata, un click genera il report stampabile (o PDF) con giri, settori, migliori tempi, test di performance e allarmi.

---

## I dati: dove stanno e come proteggerli

I dati sono salvati **nel browser del PC**, non su un server: nessuno li vede, ma sono legati a quel browser.

Il software protegge con: salvataggio automatico continuo, **backup automatico ogni 30 minuti** (ripristinabile dal pannello 🛡 in basso a destra) e avviso quando la memoria si avvicina al limite.

**Regola**: a fine giornata fai sempre ⬇ BACKUP COMPLETO su chiavetta o cloud. Attenzione: cancellare i dati di navigazione del browser o usare la modalità anonima cancella tutto.

---

## Se qualcosa non va

1. In basso a destra compare il badge **🐞** se il software ha incontrato un errore. Cliccalo, poi **⬇ ESPORTA LOG**: quel file dice esattamente cosa è successo.
2. Se un telefono smette di trasmettere, guarda il pannello **📟 Stato telefoni** sul PC: riporta lo stato della camera e degli errori di ogni vettura.
3. Connessione caduta: non serve fare nulla, il sistema riaggancia da solo entro ~30 secondi mantenendo lo stesso codice squadra.
4. Video nero o assente: chiudi le altre app che usano la camera sul telefono e ripremi 🎥.

---

## Scorciatoie utili

- **Ctrl+K** — cerca e apri qualunque pagina o funzione
- **H** — aiuto contestuale della pagina in cui sei
- **🩺 ESEGUI VERIFICA** (Guida & novità) — controllo automatico dello stato del programma

---

## Limiti da conoscere

- Su iPhone, a schermo spento la trasmissione si ferma (limite del sistema operativo): usare il blocco schermo interno all'app.
- Video live e scanner codici non funzionano insieme: il telefono ha una camera sola.
- Alcuni siti esterni non si aprono dentro il browser integrato (lo vietano): si aprono in finestra separata.
- Con rete mobile debole il video passa a fotogrammi: è il comportamento previsto, non un guasto.

---

*Per l'elenco completo delle verifiche e della compatibilità browser: vedi QUALITA_E_COMPATIBILITA.md*
