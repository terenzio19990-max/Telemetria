# REP Sim Bridge 2.1 — ponte tra simulatori e Race Engineer Pro

Legge i dati dei giochi di guida e li manda a Race Engineer Pro (linguetta **🎮 SIM** in alto, accanto a PISTA e RALLY) e ai telefoni/tablet della stessa rete Wi-Fi.
**Legge soltanto**: non modifica niente nel gioco e non invia dati su Internet.

## Novità della 2.1
- **F1 25**: nuovo gioco supportato (dati UDP ufficiali, formato 2025): telemetria, gomme, ERS, DRS, meteo, tutte le auto in pista e il setup in uso.
- **Quota delle auto** (altezza in metri) per la mappa 3D del programma: pista con salite e discese, auto in 3D.
- **Giri salvati anche a programma chiuso**: ogni giro (traccia, gomme, condizioni, setup) viene scritto in `Documenti\RaceEngineerPro\giri_sim`; quando apri il programma e colleghi il ponte, i giri che mancano arrivano da soli. `--cartella-giri DIR` per un'altra cartella, `--senza-archivio` per non scrivere su disco.
- **Più dati per le tabelle dei giri**: vento, umidità, densità dell'aria, aiuti attivi (AC, ACC, F1 25), scheda auto (AC/ACC), previsione pioggia di F1 25.

## Novità della 2.0
- **Telemetria completa**: angolo del volante in gradi, TC / taglio TC / ABS / mappa / ripartizione / migrazione / barre regolabili, interventi di TC e ABS, ibrido (batteria, deploy, recupero, energia virtuale), temperature motore, imbardata, sospensioni, altezze da terra, derive e slittamento delle gomme, carico aerodinamico, distacchi da chi ti precede e ti segue. Quello che il gioco non dà, manca.
- **Setup trovato da solo**: il ponte cerca il setup della tua auto e pista (ACC, Assetto Corsa, Le Mans Ultimate, rFactor 2; iRacing lo legge direttamente dal gioco) e lo manda al programma; se lo modifichi nel garage lo rimanda.
- **Chiamate dell'ingegnere anche sul telefono** (box, regolazioni, coach).
- **Controllo dei dati**: ogni valore letto dal gioco viene controllato; se qualcosa non torna con quello che vedi nel gioco avvia `python ponte.py --diagnosi` (o aggiungi `--diagnosi` in AVVIA_PONTE) e manda il file `diagnosi_dati.json` che compare in questa cartella.
- **Le Mans Ultimate / rFactor 2**: temperature dei freni corrette (il gioco le manda in Kelvin).

## Una volta sola
1. Installa **Python 3** da https://www.python.org/downloads/ — durante l'installazione spunta **"Add python.exe to PATH"**.
2. Copia questa cartella sul PC dove giri al simulatore (per esempio sul Desktop).

## Ogni volta
1. Doppio clic su **AVVIA_PONTE.bat** (lascia la finestra aperta mentre giri).
2. In Race Engineer Pro premi la linguetta **🎮 SIM** in alto (accanto a PISTA e RALLY) e poi **COLLEGA**
   (indirizzo `127.0.0.1:8977` se il programma è sullo stesso PC; se è su un altro PC usa l'indirizzo che il ponte scrive nella sua finestra).
3. Telefono o tablet: apri nel browser l'indirizzo `http://…:8977` scritto nella finestra del ponte (stessa Wi-Fi). La prima volta Windows chiede il permesso di rete per Python: consenti sulle **reti private**.

## Giochi
| Gioco | Cosa impostare |
|---|---|
| Assetto Corsa, Assetto Corsa EVO, iRacing, Le Mans Ultimate | niente |
| Assetto Corsa Competizione | niente; per **nomi e distacchi di tutti** avvia una volta **CONFIGURA_ACC.bat** e riavvia ACC |
| Automobilista 2 | Opzioni → Sistema → Memoria condivisa: **Project CARS 2** |
| rFactor 2 | attiva il plugin **rFactor2SharedMemoryMapPlugin64** (Opzioni → Plugin) |
| Forza Motorsport | Impostazioni → HUD e gioco → Data Out: **ON**, IP **127.0.0.1**, porta **5300**, formato **Car Dash** |
| F1 25 | Impostazioni → Telemetria: UDP **attivo**, IP **127.0.0.1**, porta **20777**, formato UDP **2025**, frequenza **20 Hz**, «La tua telemetria» **pubblica** |

## Tamponi (bumpstop) e force feedback dal vivo
Il ponte legge dal vivo tutti i canali che i giochi mettono anche nei loro file di telemetria (MoTeC di ACC,
.duckdb di LMU): non serve convertire niente. In più:
- **Tamponi**: nessun gioco dice dal vivo quando la sospensione tocca i tamponi; il ponte lo ricava dalla forza
  sulla ruota contro la corsa (serve qualche giro). In ACC puoi renderlo esatto aprendo una volta nel programma
  un file **.ld** di quella auto (Telemetria → «Tara i tamponi»).
- **Force feedback** (LMU): quanto è al 100% (volante al limite).

## File
- **PROVA_DEMO.bat** — nessun gioco: simula una sessione con 6 auto, per provare programma e telefono.
- **SOLO_QUESTO_PC.bat** — come AVVIA_PONTE ma senza accesso dai telefoni.
- **AVVIA_PONTE.bat** accetta opzioni: `--porta 8977`, `--forza-porta 5300`, `--f1-porta 20777`, `--cartella-giri DIR`, `--senza-archivio`, `--registra dati.txt` (salva i dati grezzi: mandali se qualcosa non torna).

## Se qualcosa non va
- *"Non riesco ad aprire la porta"*: il ponte è già aperto in un'altra finestra.
- Il programma dice *ponte non raggiungibile*: controlla che la finestra del ponte sia aperta e l'indirizzo giusto.
- Il gioco non viene trovato: entra in pista (nei menu alcuni giochi non pubblicano i dati).

---
*English:* install Python 3 (tick "Add to PATH"), run **AVVIA_PONTE.bat**, then in Race Engineer Pro click the **🎮 SIM** tab at the top (next to TRACK and RALLY) and press **CONNECT**. Phones on the same Wi-Fi open the `http://…:8977` address shown in the bridge window. **PROVA_DEMO.bat** simulates a session without any game.
