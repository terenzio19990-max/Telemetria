# CHECKLIST COLLAUDO IN PISTA — Race Engineer Pro v20
### Software PC: `race_engineer_pro_v20_18.html` · Telefoni: trasmettitore **v5.0** (controlla la scritta in alto a destra)
### Novità v20_18/v5.0: 🔧 LIBRETTO VITA COMPONENTI — i km di prove, giri e trasferimenti si scaricano su vettura e componenti, con soglie tue e allarmi a fine vita · PS auto-riconosciuta · controllo orario · km gomme · meteo pioggia

## LA SERA PRIMA (a casa, 30 min)
- [ ] PC: apri la v20 → 📖 Guida & novità → 🩺 ESEGUI VERIFICA: tutte spunte verdi
- [ ] ⚙ Parametri vettura aggiornati (massa reale, trazione, rapporti se li hai); scheda assetto associata
- [ ] ⬇ BACKUP COMPLETO su chiavetta/cloud
- [ ] Importa il tracciato in ⛰ Mappa 3D (link Google Maps) → USA COME PROFILO
- [ ] Telefoni: apri l'app 📡, verifica **v5.0**, imposta il NOME AUTO, batteria carica + caricatore in macchina
- [ ] iPhone: Impostazioni → Schermo → **Blocco automatico: Mai** (per i giorni di gara)
- [ ] Prova generale sul divano: ricezione → codice → CONNETTI → START → punti che salgono → STOP → percorso salvato

## AL BOX, PRIMA DEL PRIMO RUN
- [ ] ATTIVA RICEZIONE → un codice per tutta la squadra, scrivilo in grande
- [ ] Ogni telefono: nome auto → codice → CONNETTI → montaggio RIGIDO al parabrezza → START → 🔒 BLOCCA SCHERMO (quello DENTRO l'app)
- [ ] ⚠️ REGOLA D'ORO: MAI il tasto laterale! Schermo spento = iOS congela camera e trasmissione (limite di sistema). Solo 🔒 in-app: schermo acceso, tocchi bloccati, luminosità al minimo
- [ ] ⚠ ALLARMI URTO: **ON** (verifica che non sia rimasto giallo/OFF da un trasferimento)
- [ ] 🎥 VIDEO: premilo UNA VOLTA A MANO a inizio giornata su ogni telefono → UN solo consenso (camera+mic insieme). Da lì in poi ON/OFF anche dal telecomando del box, senza più tocchi. Se il mic dà problemi il software lo sacrifica da solo per salvare il video
- [ ] Al box: se il tile diventa "📷 FOTOGRAMMI" è normale con rete debole — il video fluido torna da solo appena la rete lo permette
- [ ] Setup di partenza compilato e **SALVA SETUP** (baseline per i delta)

## DURANTE I RUN — cosa osservare e annotare per me
- [ ] **Calibrazione g**: dopo la prima frenata decisa, G LAT diventa numerica sul telefono e sul box? Quanti secondi/metri servono?
- [ ] **Segno g laterale**: curva a destra e a sinistra hanno il verso giusto? (se invertito: fix da una riga, dimmelo)
- [ ] **ay max plausibile**? (Clio su slick: attesi ~1.3–1.6 g; se leggi 0.8 o 2.5 c'è un problema di montaggio o calibrazione)
- [ ] **Connessione**: diretta o "via relay"? Cade mai? Dopo quanto riaggancia?
- [ ] **Frequenza punti**: "ULTIMO DATO" resta verde (≤2 s) in tutto il giro o ci sono buchi in zone precise della pista?
- [ ] **Velocità fusa**: il tachimetro live è fluido e coerente con quello di bordo?
- [ ] **Batteria/termico telefono**: quanto dura? va in protezione termica al sole?

## TRA I RUN
- [ ] Il percorso LIVE si è salvato da solo (toast) → aprilo in ⛰ Mappa 3D per verifica traccia
- [ ] 🌡 Temperature gomme I/M/O appena rientra + tempi giro CON settori
- [ ] **ay max misurata** → 📊 CALIBR. → FIT µ gomme (è il dato che calibra il modello!)
- [ ] Vmax reale → FIT CdA
- [ ] Dopo 2+ run: 📉 **Analisi giro** run1 vs run2 → il delta indica gli stessi punti che sente il pilota?
- [ ] Una modifica di setup alla volta; il pannello dice direzione e ordine di grandezza attesi → poi confronta col cronometro

## FINE GIORNATA — il debriefing che mi serve
- [ ] Δt previsti dal modello vs reali: ordine giusto? sempre ottimisti/pessimisti?
- [ ] Verdetti di fase (ingresso/percorrenza/uscita) vs sensazioni pilota: concordano?
- [ ] Frenate individuate dalle g in Analisi: sono quelle vere della pista?
- [ ] Falsi allarmi urto: quanti, su cosa (cordoli? buche?) → per tarare la soglia
- [ ] Qualsiasi stranezza: pagina, orario, cosa stavi facendo

## FILE
- **PC: usa solo `race_engineer_pro_v20_18.html`** (le versioni precedenti si possono cancellare; `rep_base_v19.html` NON cancellarlo: serve per i futuri aggiornamenti)
- Telefoni: trasmettitore v5.0 da GitHub (aggiungi alla Home; controlla la versione dopo l'upload)
