# Race Engineer Pro — Qualità, compatibilità e limiti noti
### Documento tecnico per la versione commerciale · v20_14 (PC) + v4.6 (trasmettitore telefono)

---

## 1. Stato della verifica

**Test automatici**: 12 suite, 148 verifiche, tutte verdi.

| Suite | Verifiche | Cosa copre |
|---|---|---|
| QA sweep pagine | 2 | tutte le **55 pagine** del software si aprono senza errori |
| Guardiano qualità | 7 | cattura errori, backup, ripristino, export log |
| Telemetria Lap Pro | 15 | riconoscimento circuito, traguardo, settori, teorico, predittivo |
| Analisi Pro | 10 | canali/settore, istogrammi, math channel, video sync |
| Test performance | 10 | 0-100, 0-200, 400 m, frenata 100-0, curve, mappa colorata |
| Pit board / moviola | 11 | messaggi al pilota, replay, ghost, report |
| Scanner e magazzino | 13 | QR/barcode, scheda pezzo, carico magazzino |
| Record e CSV | 8 | record personale per pista, export |
| Overlay video box | 7 | velocità, gas/freno, giro, delta sul tile |
| Pulsanti e navigazione | 3 | 343 handler verificati, id duplicati, link di pagina |
| QA completo PC+telefono | 12 | riferimenti DOM, esportazioni, motore fisico, moduli |
| Pacchetto distribuzione | 20 | manifest, service worker, icone, avvio box e telefono dal pacchetto |

**Difetti trovati e corretti in questa sessione di QA**

| # | Difetto | Impatto | Stato |
|---|---|---|---|
| 1 | Contesto canvas non verificato in 13 punti | Pagina in errore se il browser revoca il contesto grafico (memoria scarsa) | ✅ corretto |
| 2 | Id `autosave-indicator` duplicato (elemento statico + creato a runtime) | Due indicatori di salvataggio, `getElementById` puntava sempre al primo | ✅ corretto |
| 3 | **Grafico previsione rally mai visualizzato**: mancava il contenitore nella pagina, la funzione usciva sempre | Funzione di fatto assente per l'utente | ✅ corretto (aggiunto pannello con grafico e schede vettura) |
| 4 | Guardia prestazioni del grafico giri su id inesistente (`lap-chart`) | Ricostruzione del grafico anche a pagina non visibile: spreco di CPU | ✅ corretto (ora `lapchart-plotly`) |

**Verifiche di copertura**
- 55 pagine aperte una per una: nessuna eccezione, nessun errore JavaScript.
- 343 handler di pulsanti/campi: tutti puntano a funzioni esistenti.
- 756 riferimenti DOM nel codice: nessuno non protetto (18 riferimenti a elementi legacy o dinamici, tutti con guardia — nessun impatto).
- Trasmettitore telefono: avvio pulito, nessun id duplicato, tutti i pulsanti validi.

---

## 2. Protezione dei dati (novità v20_14)

- **Backup automatico** di tutti i dati locali ogni 30 minuti in un archivio interno del browser; ne restano gli ultimi 6, ripristinabili con un click dal pannello 🛡.
- **Monitor memoria**: avviso quando i dati locali superano ~4,2 MB o quando la memoria concessa dal browser supera l'80% — **prima** che si possa perdere qualcosa.
- **Backup manuale completo** (già presente): esporta tutto in un file JSON.
- Il primo backup automatico parte 1 minuto dopo l'apertura.

**Raccomandazione operativa**: a fine giornata, ⬇ BACKUP COMPLETO su chiavetta o cloud. I backup automatici proteggono dagli incidenti, non sostituiscono l'archiviazione esterna.

---

## 3. Raccolta errori (novità v20_14)

Ogni errore del software viene catturato e registrato (ultimi 50 conservati tra le sessioni). Quando accade qualcosa compare il badge **🐞** in basso a destra: cliccandolo si apre il pannello con l'elenco, orario e origine, e il pulsante **⬇ ESPORTA LOG** produce un file di testo con anche il browser usato.

Per l'assistenza clienti: chiedere sempre quel file — contiene cosa è successo, dove e quando.

Sul **telefono** gli errori vengono trasmessi al box e compaiono nel pannello 📟 "Stato telefoni": in macchina nessuno può leggere lo schermo, così l'ingegnere vede comunque il problema.

---

## 4. Matrice browser

| Funzione | Chrome / Edge | Firefox | Safari (Mac) | Safari (iPhone) |
|---|---|---|---|---|
| Interfaccia, calcoli, setup, analisi | ✅ | ✅ | ✅ | ✅ |
| Salvataggio dati e backup | ✅ | ✅ | ✅ | ✅ |
| Telemetria live (dati) | ✅ | ✅ | ✅ | ✅ |
| Video live dalla vettura | ✅ | ✅ | ✅ | ✅ (limiti iOS §5) |
| Registrazione video sul telefono | ✅ | ✅ | ✅ | ✅ |
| Scanner codici (QR + barre) | ✅ nativo | ⚠️ solo QR | ⚠️ solo QR | ✅ nativo (iOS 17+) |
| Notifiche di sistema | ✅ | ✅ | ✅ | ⚠️ solo se installata sulla Home |
| Dettatura note vocali | ✅ | ❌ | ✅ | ✅ |
| Schermo sempre acceso | ✅ | ⚠️ parziale | ✅ | ✅ (iOS 16.4+) |
| Copia negli appunti | ✅ | ✅ | ✅ | ✅ |

**Browser consigliato per il PC del box: Chrome o Edge aggiornati.** Sono quelli su cui tutte le funzioni sono al 100%.

Dove una funzione manca, il software **degrada senza rompersi**: lo scanner passa al lettore software, le notifiche diventano avvisi interni, la dettatura si disattiva con messaggio.

---

## 5. Limiti noti — dichiarati, non nascosti

Questi non sono difetti del software ma vincoli delle piattaforme. Un prodotto serio li scrive.

1. **iPhone, schermo spento = trasmissione ferma.** iOS congela le pagine web quando lo schermo si spegne: camera e trasmissione si fermano. Nessuna applicazione web può aggirarlo. Soluzione integrata: 🔒 BLOCCA SCHERMO dentro l'app (schermo acceso e nero, tocchi disattivati) + rilevamento automatico della sospensione con ripristino al risveglio.
2. **Una sola camera per volta sul telefono**: video live e scanner codici non possono funzionare insieme (limite iOS). Il software lo segnala e impedisce il conflitto.
3. **Browser integrato**: molti siti (Google, cronometraggi ufficiali) vietano di essere mostrati dentro un'altra pagina. Non è aggirabile lato software: il programma se ne accorge e offre l'apertura in finestra esterna.
4. **Video live su reti mobili difficili**: quando la rete non permette il flusso continuo, il sistema passa automaticamente ai **fotogrammi** (un'immagine ogni 2 s sul canale dati) e torna al video fluido appena possibile.
5. **Memoria del browser**: i dati stanno nel browser del PC. Cancellare i dati del sito o usare la navigazione anonima li elimina. Il monitor avvisa, i backup automatici proteggono, ma l'esportazione a fine giornata resta la regola.
6. **Modello di dinamica del veicolo**: la fisica è corretta (trasferimenti di carico, ellisse d'attrito, sensibilità al carico, aerodinamica), ma i **suggerimenti di setup restano indicazioni di direzione e ordine di grandezza**, da calibrare con i dati misurati della vettura (funzioni FIT µ e FIT CdA). Il software include la validazione automatica GPS↔IMU per verificare la coerenza dei sensori curva per curva.

---

## 6. Da completare prima della vendita

- [ ] **Validazione in pista** di tutte le funzioni telemetriche (mai eseguita dopo gli ultimi aggiornamenti) ← **unico blocco rimasto**
- [ ] Prova manuale su Firefox e Safari con l'elenco funzioni alla mano
- [x] Manuale utente per il cliente finale → `MANUALE_UTENTE.md`
- [x] Licenza d'uso e condizioni → `LICENZA.md`
- [x] Confezione: versione installabile (PWA), canale aggiornamenti, procedura assistenza → cartella `dist/` + `LEGGIMI_INSTALLAZIONE.md`

---

## 7. Come rieseguire i test

I test stanno nella cartella `tests/`. Con Node.js installato e la libreria jsdom:

```
npm install jsdom
node tests/test_qa_full.js      # QA completo PC + telefono
node tests/test_guard.js        # 55 pagine + guardiano qualità
node tests/test_buttons.js      # pulsanti, id, navigazione
node tests/test_lappro.js       # cronometraggio e settori
node tests/test_pro.js          # analisi professionale
node tests/test_perf.js         # test performance e curve
node tests/test_scan.js         # scanner e magazzino
node tests/test_pitrpl.js       # pit board, moviola, report
node tests/test_pb.js           # record per pista, CSV
node tests/test_ovl.js          # overlay video al box
node tests/test_v38.js          # trasmissione video
node tests/test_dist.js         # pacchetto di distribuzione
```

**Regola per gli aggiornamenti futuri: nessuna versione si pubblica se una sola suite è rossa.**

---

*Documento generato per la revisione qualità della v20_14. Da aggiornare a ogni versione.*
