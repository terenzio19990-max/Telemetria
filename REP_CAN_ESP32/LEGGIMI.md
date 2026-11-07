# REP-CAN — dati della centralina via rete CAN

Il modulo REP-CAN legge la rete CAN della vettura e manda i dati al telefono in Bluetooth. Il telefono li inoltra al box, insieme al GPS.

- **Centraline motorsport** (Magneti Marelli, MoTeC, Life, Bosch Motorsport…): il modulo resta in **solo ascolto** e legge i segnali che la centralina pubblica sulla rete.
- **Auto di serie o rimappate** (dal 2008 quasi tutte hanno l'OBD su CAN): in **OBD veloce** il modulo interroga la centralina dalla presa diagnostica. Fa circa 65 letture al secondo, contro le 10–20 di un adattatore ELM327.

Per le auto di serie basta anche un adattatore OBD Bluetooth LE già pronto (Vgate iCar Pro BLE, OBDLink CX…): il modulo REP-CAN non è obbligatorio.

## Cosa comprare (circa 15–20 €)

| Pezzo | Esempio |
| --- | --- |
| Scheda ESP32 | ESP32 DevKit V1, ESP32-S3 o ESP32-C3 |
| Trasmettitore CAN 3,3 V | modulo SN65HVD230 («CJMCU-230») |
| Alimentazione | riduttore 12 V → 5 V USB per auto (anche quello della presa accendisigari) |
| Collegamento | spina OBD-II maschio con cavetti, oppure connettore della centralina |

## Collegamenti

```
ESP32           SN65HVD230
3V3   ───────►  3V3
GND   ───────►  GND
GPIO5 ───────►  CTX (TXD)
GPIO4 ◄───────  CRX (RXD)
                CANH ───► CAN-H della vettura (presa OBD: piedino 6)
                CANL ───► CAN-L della vettura (presa OBD: piedino 14)
GND della scheda collegato anche alla massa della vettura (presa OBD: piedino 4 o 5)
```

- Alimenta l'ESP32 dal riduttore USB, non direttamente dai 12 V.
- **Non** aggiungere la resistenza da 120 Ω se il modulo si attacca a una rete che ne ha già due, come quasi sempre in auto. Molti moduli SN65HVD230 ne hanno una saldata (R2 da 120 Ω): se è un problema, si toglie.
- Piedini diversi da GPIO5 e GPIO4: cambia `PIN_CAN_TX` e `PIN_CAN_RX` in cima al file.

## Caricare il firmware

1. Installa **Arduino IDE** (gratuito).
2. Vai in *File → Preferenze → URL aggiuntive* e aggiungi `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
3. In *Strumenti → Scheda → Gestore schede* installa **esp32 di Espressif**.
4. Apri `REP_CAN_ESP32.ino`, scegli la tua scheda (es. *ESP32 Dev Module*) e la porta USB, poi premi **Carica**.

Non servono altre librerie. Acceso, il LED della scheda lampeggia (in attesa) e diventa fisso quando il telefono si collega.

## Usarlo

1. **Box** → 📍 GPS logger → riquadro **🔌 Centralina** → ⚙ *Allarmi e rete CAN*:
   - scegli il **modo**: *Solo ascolto* per le centraline motorsport, *OBD veloce* per le auto di serie;
   - scegli la **velocità di rete**: di solito 500 kbit/s, 1000 su molte centraline motorsport;
   - scrivi i **segnali** da leggere (vedi sotto) e premi **SALVA E INVIA AI TELEFONI**.
2. **Telefono** → **🔌 CENTRALINA** → scegli «REP-CAN» dall'elenco. Su iPhone usa l'app gratuita **Bluefy**.
3. I valori compaiono sul telefono e nel riquadro del box.

## Segnali CAN

Una riga per segnale: `nome; id; bit di partenza; lunghezza; LE o BE; U o S; fattore; offset; unità`

- **id**: identificatore del messaggio, es. `0x316`.
- **bit di partenza** e **lunghezza** in bit, come nel file DBC.
- **LE** = Intel (little endian), **BE** = Motorola (big endian).
- **U** = senza segno, **S** = con segno.
- **valore = grezzo × fattore + offset**.

Esempio (valori inventati: quelli veri dipendono dalla tua centralina):

```
rpm;   0x316; 16; 16; LE; U; 0.25;  0;   giri
clt;   0x329;  8;  8; LE; U; 0.75; -48;  °C
thr;   0x329; 40;  8; LE; U; 0.392; 0;   %
```

I nomi `rpm`, `spd`, `thr`, `clt`, `oil`, `iat`, `volt`, `boost` vengono mostrati con l'etichetta giusta e attivano gli allarmi del box. Gli altri nomi compaiono così come sono.

**Dove si trovano i dati?** Nel file **DBC** o nel manuale della centralina: le centraline motorsport hanno quasi sempre un «CAN stream» configurabile e documentato. Senza documentazione, usa **🔍 SCOPERTA CAN** sul telefono. Mostra tutti gli ID che passano ed evidenzia i byte che cambiano: muovi il pedale, gira il volante, accendi le luci e guarda cosa si accende.

## Sicurezza

- In **solo ascolto** il modulo non trasmette niente, nemmeno le conferme di ricezione: non può disturbare la centralina.
- L'**OBD veloce** trasmette domande standard di sola lettura (modo 01). Usalo **solo dalla presa diagnostica** di auto di serie o rimappate, mai sulla rete di una centralina motorsport.
- Se il telefono si scollega, il modulo torna da solo in solo ascolto.
- Fissa bene i collegamenti: un cavo CAN che si stacca o va in corto può spegnere strumenti o centralina.
- Prova sempre a vettura ferma prima di usarlo in pista.
