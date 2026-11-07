# Race Engineer Pro — Installazione e aggiornamenti
### Pacchetto di distribuzione · box v20.14 · trasmettitore v5.2

---

## Cosa c'è in questo pacchetto

```
box/          → il software per il PC del box (installabile come app)
telefono/     → il trasmettitore per i telefoni delle vetture
documenti/    → manuale utente, licenza, documento qualità, checklist pista
```

Le due parti si pubblicano **separatamente**: sono due app distinte che si parlano tra loro.

---

## Modo rapido: uso immediato senza pubblicare

Se vuoi solo provare il software sul PC: apri `box/index.html` con doppio clic (Chrome o Edge).
Funziona tutto tranne l'installazione come app e il funzionamento offline, che richiedono la pubblicazione su HTTPS.

**I telefoni invece richiedono la pubblicazione**: devono raggiungere il trasmettitore da un indirizzo web (la camera e il GPS non funzionano aprendo un file locale).

---

## Pubblicazione (una volta sola, ~10 minuti)

### Opzione A — Netlify Drop (gratuita, la più semplice)

Da fare **due volte**, una per cartella:

1. Vai su `https://app.netlify.com/drop`
2. Trascina la cartella `box` → ottieni un indirizzo tipo `https://nome-scelto.netlify.app`
3. Ripeti trascinando la cartella `telefono` → secondo indirizzo
4. Annota i due indirizzi: il primo è per il PC, il secondo per i telefoni

### Opzione B — GitHub Pages (gratuita)

1. Crea un repository, carica il contenuto di `box` nella radice e quello di `telefono` in una sottocartella `tx/`
2. Settings → Pages → Source: branch `main`
3. Indirizzi: `https://UTENTE.github.io/REPO/` (box) e `https://UTENTE.github.io/REPO/tx/` (telefono)

### Opzione C — Server proprio

Serve HTTPS (obbligatorio per camera, GPS e installazione). Copia le due cartelle in due percorsi distinti del sito.

---

## Installazione lato utente

### PC del box
Apri l'indirizzo del box in **Chrome o Edge** → nella barra degli indirizzi compare l'icona di installazione → **Installa**.
L'app si apre in finestra propria, ha una sua icona e funziona anche senza internet (i dati sono già in locale; servono connessione solo telemetria e mappe).

### Telefoni delle vetture
1. Apri l'indirizzo del trasmettitore in **Safari** (iPhone) o **Chrome** (Android)
2. Condividi → **Aggiungi alla schermata Home**
3. Aprilo da lì: parte a tutto schermo come un'app

Poi imposta il NOME AUTO e usa il codice squadra che compare sul PC.

---

## Aggiornamenti

Quando esce una versione nuova:

1. **Ripubblica** la cartella aggiornata (ritrascina su Netlify Drop, o ricarica i file sul server)
2. Sui dispositivi: **apri l'app e ricarica una volta** (trascina verso il basso sul telefono, o Ctrl+R sul PC)

L'aggiornamento è automatico: il pacchetto è configurato per prendere **sempre prima dalla rete** la pagina dell'app, quindi la versione nuova arriva alla prima apertura con connessione. La versione in cache serve solo quando manca la linea.

**Verifica sempre il numero di versione** in alto a destra dopo un aggiornamento: box `v20.14`, trasmettitore `v4.6`. Se vedi ancora il numero vecchio, ricarica di nuovo.

**I dati non si perdono mai con un aggiornamento**: restano nel browser, separati dal programma. Comunque, prima di ogni aggiornamento importante conviene fare ⬇ BACKUP COMPLETO.

---

## Verifica dopo l'installazione (5 minuti)

- [ ] Il box si apre e mostra il numero di versione corretto
- [ ] Menu → 📖 Guida & novità → **🩺 ESEGUI VERIFICA**: tutte le spunte verdi
- [ ] Il pannello 🛡 in basso a destra risponde (nessun errore 🐞 all'avvio)
- [ ] Telemetria → 📡 ATTIVA RICEZIONE → compare il codice squadra
- [ ] Su un telefono: nome auto + codice → CONNETTI → START → i punti salgono sul PC
- [ ] 🎥 sul telefono → il video compare al box con velocità e barre gas/freno
- [ ] Modalità aereo sul telefono per 30 secondi, poi riattiva: dati e video tornano da soli

Se tutti i punti passano, l'installazione è a posto.

---

## Assistenza

In caso di problemi, dal PC: pannello **🛡** (in basso a destra) → **⬇ ESPORTA LOG**.
Allega quel file alla segnalazione: contiene gli errori riscontrati, l'orario e la configurazione in uso — è ciò che permette di diagnosticare senza tentativi.

Per i problemi lato vettura, riporta anche cosa scrive il pannello **📟 Stato telefoni** sul PC.

---

*Documenti di riferimento nella cartella `documenti/`: manuale utente, licenza d'uso, documento qualità e compatibilità, checklist di pista.*
