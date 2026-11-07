# REP Estensione 1.1 — Rally-Maps e Live timing

Una sola estensione per due cose: importare le prove da rally-maps.com dal solo link e leggere qualsiasi pagina di **live timing** per Race Engineer Pro.

## Live timing (novità 1.1)

I siti di live timing (Al Kamel, Apex, TSL, Speedhive, FICR…) ricevono i tempi dal loro server e li disegnano nella pagina: un programma esterno non può leggerli direttamente. L'estensione apre la pagina in una scheda in secondo piano e, ogni pochi secondi, legge la tabella dei tempi così come la vedi tu.

1. Nel programma: 📡 Live timing → incolla l'indirizzo della pagina del live timing → **CONNETTI**.
2. Per i siti più comuni il permesso c'è già. Per un sito nuovo si apre una pagina dell'estensione: premi **Consenti** (vale solo per quel sito), poi di nuovo CONNETTI.
3. Se il sito chiede i cookie, accettali nella scheda del live timing (una volta).
4. Con «Auto-import giri» i giri nuovi delle tue vetture vanno nei Tempi giro, quelli degli altri negli Avversari.

Se avevi la versione 1.0: sostituisci i file nella stessa cartella e premi ↻ (Ricarica) sulla scheda dell'estensione in chrome://extensions.

## Rally-Maps — importare un rally incollando solo il link

Con questa estensione, nella Mappa 3D di Race Engineer Pro basta incollare il link del rally su rally-maps.com e premere **⚡ IMPORTA DAL LINK**.

L'estensione apre la pagina del rally in una scheda in secondo piano, legge le prove speciali, chiude la scheda e le passa al programma. Il programma poi fa tutto da solo:
- un percorso per ogni prova, con le altitudini (serve internet), per la Mappa 3D;
- la lunghezza di ogni prova;
- il collegamento alle Pressioni e al Meteo per PS;
- il programma delle PS e il piano carburante, se è vuoto;
- il meteo del rally e le previsioni prova per prova.

Funziona con **Chrome** ed **Edge** sul PC. È gratuita e non serve nessun account.

## Installazione (una volta sola, circa 1 minuto)

1. Scompatta lo zip in una cartella che non sposterai più, per esempio `Documenti\REP_RallyMaps_estensione`.
2. Apri `chrome://extensions` in Chrome, o `edge://extensions` in Edge.
3. Attiva **Modalità sviluppatore**, in alto a destra in Chrome o a sinistra in Edge.
4. Premi **Carica estensione non pacchettizzata** e scegli la cartella del punto 1.
5. **Importante:** sulla scheda dell'estensione premi **Dettagli** e attiva **Consenti l'accesso agli URL dei file**. Serve perché il programma si apre come file dal PC.
6. Ricarica la pagina del programma. Nella Mappa 3D compare il pulsante verde **⚡ IMPORTA DAL LINK**.

## Uso

1. Su rally-maps.com apri la pagina del rally e copia il link, per esempio `https://www.rally-maps.com/Rallye-Sanremo-2026`.
2. Nel programma vai su Rally → ⛰ MAPPA 3D → riquadro «Prove speciali da Rally-Maps».
3. Incolla il link e premi **⚡ IMPORTA DAL LINK**.

**La prima volta** rally-maps può chiedere il consenso ai cookie. Se dopo una dozzina di secondi le prove non arrivano, l'estensione porta in primo piano la scheda di rally-maps: accetta i cookie lì e il resto continua da solo. Le volte successive non serve più.

## Cosa fa e cosa non fa

- Ha il permesso di leggere rally-maps.com e i siti di live timing più usati; per altri siti lo chiede a te, sito per sito.
- Sulle altre pagine non fa niente: risponde solo alla pagina di Race Engineer Pro.
- Non manda dati a nessun server: legge la pagina che apre il tuo browser e passa le prove al programma sul tuo PC.
- Se rally-maps cambia il modo in cui mostra le prove, l'estensione va aggiornata. Nel frattempo funzionano sempre il segnalibro e i file GPX/KML.
- Le prove restano di rally-maps e degli organizzatori: usale per il lavoro della tua squadra.

## Aggiornare

Sostituisci i file nella stessa cartella e premi ↻ sulla scheda dell'estensione in `chrome://extensions`.
