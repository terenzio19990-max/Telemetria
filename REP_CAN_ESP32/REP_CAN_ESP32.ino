/* ═══════════════════════════════════════════════════════════════════════════
   REP-CAN — modulo CAN → Bluetooth LE per Race Engineer Pro (firmware 1.0)

   Hardware: una scheda ESP32 (ESP32 classico, S3 o C3: hanno tutti il
   controllore CAN «TWAI») + un trasmettitore CAN a 3,3 V (SN65HVD230 o
   simile). Vedi LEGGIMI.md per i collegamenti.

   Cosa fa
   • parte SEMPRE in SOLO ASCOLTO: non trasmette niente sulla rete
     dell'auto, nemmeno le conferme (ACK). Legge i frame e li manda al
     telefono in Bluetooth LE;
   • limita i frame per ogni ID (il Bluetooth non regge 2000 frame/s);
   • a richiesta del telefono (comando «O…») interroga la centralina con le
     domande OBD standard (modo 01) dalla presa diagnostica. SOLO in quel
     caso trasmette sulla rete: non usarlo sulla rete CAN di una centralina
     motorsport.

   Protocollo Bluetooth (servizio a7c40001-5e3a-4f6b-9b1c-2f0c0dbe0001)
   • notifiche (…0002): pacchetti di frame, ognuno
       0xAA | id (4 byte little endian, bit 31 = id esteso) | dlc | dati
   • scrittura (…0003): comandi di testo terminati da \n
       B500        velocità rete in kbit/s (125, 250, 500, 1000)
       L           solo ascolto (predefinito)
       O0C0D11...  OBD su CAN: elenco dei PID da chiedere a giro
       F316,329    accetta solo questi ID (esadecimale); «F» vuoto = tutti
       R25         frame al secondo massimi per ogni ID

   Librerie: solo quelle incluse nel pacchetto «esp32» di Arduino (Espressif).
   ═══════════════════════════════════════════════════════════════════════════ */
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "driver/twai.h"

/* ── collegamenti: cambiali se usi altri piedini ── */
#define PIN_CAN_TX   5      // ESP32 → CTX / TXD del trasmettitore
#define PIN_CAN_RX   4      // ESP32 ← CRX / RXD del trasmettitore
#define PIN_LED      2      // LED della scheda (-1 se non c'è)
#define NOME_BLE     "REP-CAN"

#define SVC_UUID  "a7c40001-5e3a-4f6b-9b1c-2f0c0dbe0001"
#define RX_UUID   "a7c40002-5e3a-4f6b-9b1c-2f0c0dbe0001"   // notifiche verso il telefono
#define TX_UUID   "a7c40003-5e3a-4f6b-9b1c-2f0c0dbe0001"   // comandi dal telefono

static BLECharacteristic *chNotifica = nullptr;
static volatile bool collegato = false;

/* ── stato ── */
static uint32_t kbit = 500;
static bool modoObd = false;
static uint8_t pidObd[16]; static uint8_t nPid = 0, iPid = 0;
static uint32_t filtro[32]; static uint8_t nFiltro = 0;
static uint16_t maxHz = 25;
static volatile bool daRiavviare = true;
static String comandoInArrivo;

/* limitatore: ultimo invio per ID (tabella piccola, sostituzione circolare) */
struct Ultimo { uint32_t id; uint32_t ms; };
static Ultimo ultimi[160]; static uint8_t nUltimi = 0, giroUltimi = 0;

/* pacchetto Bluetooth in preparazione (iPhone: MTU ≥ 185 → 160 byte stanno sicuri) */
#define PACCHETTO 160
static uint8_t pacchetto[PACCHETTO]; static uint16_t lPacchetto = 0; static uint32_t msPacchetto = 0;

/* ── CAN ── */
static void avviaCan(){
  twai_stop(); twai_driver_uninstall();
  twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)PIN_CAN_TX, (gpio_num_t)PIN_CAN_RX,
                                                       modoObd ? TWAI_MODE_NORMAL : TWAI_MODE_LISTEN_ONLY);
  g.rx_queue_len = 64; g.tx_queue_len = 8;
  twai_timing_config_t t;
  switch(kbit){
    case 125:  t = TWAI_TIMING_CONFIG_125KBITS(); break;
    case 250:  t = TWAI_TIMING_CONFIG_250KBITS(); break;
    case 1000: t = TWAI_TIMING_CONFIG_1MBITS();   break;
    default:   t = TWAI_TIMING_CONFIG_500KBITS(); kbit = 500; break;
  }
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if(twai_driver_install(&g, &t, &f) == ESP_OK) twai_start();
  nUltimi = 0;
}
static bool accettato(uint32_t id){
  if(modoObd) return id >= 0x7E8 && id <= 0x7EF;
  if(nFiltro == 0) return true;
  for(uint8_t i = 0; i < nFiltro; i++) if(filtro[i] == id) return true;
  return false;
}
static bool nonTroppoSpesso(uint32_t id){
  uint32_t ora = millis(), passo = 1000 / (maxHz ? maxHz : 1);
  for(uint8_t i = 0; i < nUltimi; i++){
    if(ultimi[i].id == id){
      if(ora - ultimi[i].ms < passo) return false;
      ultimi[i].ms = ora; return true;
    }
  }
  if(nUltimi < 160){ ultimi[nUltimi].id = id; ultimi[nUltimi].ms = ora; nUltimi++; }
  else { ultimi[giroUltimi].id = id; ultimi[giroUltimi].ms = ora; giroUltimi = (giroUltimi + 1) % 160; }
  return true;
}
static void svuota(){
  if(lPacchetto && collegato && chNotifica){
    chNotifica->setValue(pacchetto, lPacchetto);
    chNotifica->notify();
  }
  lPacchetto = 0; msPacchetto = millis();
}
static void accoda(const twai_message_t &m){
  uint8_t dlc = m.data_length_code > 8 ? 8 : m.data_length_code;
  if(lPacchetto + 6 + dlc > PACCHETTO) svuota();
  uint32_t id = m.identifier | (m.extd ? 0x80000000UL : 0);
  pacchetto[lPacchetto++] = 0xAA;
  pacchetto[lPacchetto++] = id & 0xFF; pacchetto[lPacchetto++] = (id >> 8) & 0xFF;
  pacchetto[lPacchetto++] = (id >> 16) & 0xFF; pacchetto[lPacchetto++] = (id >> 24) & 0xFF;
  pacchetto[lPacchetto++] = dlc;
  for(uint8_t i = 0; i < dlc; i++) pacchetto[lPacchetto++] = m.data[i];
}
static void domandaObd(){
  if(!modoObd || nPid == 0) return;
  twai_message_t q = {};
  q.identifier = 0x7DF; q.data_length_code = 8;
  q.data[0] = 0x02; q.data[1] = 0x01; q.data[2] = pidObd[iPid];
  for(uint8_t i = 3; i < 8; i++) q.data[i] = 0x00;
  twai_transmit(&q, pdMS_TO_TICKS(5));
  iPid = (iPid + 1) % nPid;
}

/* ── comandi dal telefono ── */
static uint8_t esa(char c){ return (c >= '0' && c <= '9') ? c - '0' : ((c | 0x20) >= 'a' && (c | 0x20) <= 'f') ? (c | 0x20) - 'a' + 10 : 0xFF; }
static void eseguiComando(String c){
  c.trim(); if(!c.length()) return;
  char t = toupper(c[0]); String a = c.substring(1);
  if(t == 'B'){ uint32_t k = a.toInt(); if(k == 125 || k == 250 || k == 500 || k == 1000){ kbit = k; daRiavviare = true; } }
  else if(t == 'L'){ if(modoObd){ modoObd = false; daRiavviare = true; } }
  else if(t == 'O'){
    nPid = 0; iPid = 0;
    for(int i = 0; i + 1 < (int)a.length() && nPid < 16; i += 2){
      uint8_t h = esa(a[i]), l = esa(a[i+1]);
      if(h != 0xFF && l != 0xFF) pidObd[nPid++] = (h << 4) | l;
    }
    bool vuole = nPid > 0;
    if(vuole != modoObd){ modoObd = vuole; daRiavviare = true; }
  }
  else if(t == 'F'){
    nFiltro = 0; int da = 0;
    while(da < (int)a.length() && nFiltro < 32){
      int v = a.indexOf(',', da); if(v < 0) v = a.length();
      String x = a.substring(da, v); x.trim();
      if(x.length()) filtro[nFiltro++] = strtoul(x.c_str(), nullptr, 16);
      da = v + 1;
    }
  }
  else if(t == 'R'){ int h = a.toInt(); if(h >= 1 && h <= 200) maxHz = h; }
}
class Comandi : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *ch) override {
    String v = String(ch->getValue().c_str());
    for(size_t i = 0; i < v.length(); i++){
      char ch1 = v[i];
      if(ch1 == '\n' || ch1 == '\r'){ eseguiComando(comandoInArrivo); comandoInArrivo = ""; }
      else if(comandoInArrivo.length() < 200) comandoInArrivo += ch1;
    }
  }
};
class Server : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override { collegato = true; }
  void onDisconnect(BLEServer *s) override {
    collegato = false;
    /* telefono andato via: si torna in solo ascolto e si riaccende la visibilità */
    if(modoObd){ modoObd = false; nPid = 0; daRiavviare = true; }
    delay(200); BLEDevice::startAdvertising();
  }
};

void setup(){
  if(PIN_LED >= 0) pinMode(PIN_LED, OUTPUT);
  BLEDevice::init(NOME_BLE);
  BLEDevice::setMTU(247);
  BLEServer *srv = BLEDevice::createServer();
  srv->setCallbacks(new Server());
  BLEService *svc = srv->createService(SVC_UUID);
  chNotifica = svc->createCharacteristic(RX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  chNotifica->addDescriptor(new BLE2902());
  BLECharacteristic *chCmd = svc->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  chCmd->setCallbacks(new Comandi());
  svc->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SVC_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

void loop(){
  static uint32_t msDomanda = 0, msLed = 0;
  if(daRiavviare){ daRiavviare = false; avviaCan(); }

  twai_message_t m;
  int letti = 0;
  while(letti < 40 && twai_receive(&m, 0) == ESP_OK){
    letti++;
    if(m.rtr) continue;
    if(!accettato(m.identifier)) continue;
    if(!modoObd && !nonTroppoSpesso(m.identifier)) continue;
    if(collegato) accoda(m);
  }
  /* un pacchetto parte quando è pieno o ogni 40 ms */
  if(lPacchetto && millis() - msPacchetto > 40) svuota();

  /* OBD: una domanda ogni 15 ms (circa 65 valori al secondo) */
  if(modoObd && collegato && millis() - msDomanda > 15){ msDomanda = millis(); domandaObd(); }

  /* rete in errore (cavo staccato, velocità sbagliata): si riparte */
  twai_status_info_t s;
  if(twai_get_status_info(&s) == ESP_OK){
    if(s.state == TWAI_STATE_BUS_OFF) twai_initiate_recovery();
    else if(s.state == TWAI_STATE_STOPPED) twai_start();
  }

  /* LED: fisso = telefono collegato, lampeggio = in attesa */
  if(PIN_LED >= 0 && millis() - msLed > 400){ msLed = millis(); digitalWrite(PIN_LED, collegato ? HIGH : !digitalRead(PIN_LED)); }
  if(!letti) delay(1);
}
