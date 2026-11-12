/**
 * LEX TX — WiFi uplink + ESP-NOW illuminator + BLE device list.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_now.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <vector>
#include <algorithm>
#include <string.h>

Preferences prefs;
WiFiUDP udp;

String wifiSsid = "LEX-HOTSPOT";
String wifiPass = "change-me-lab-only";
String collectorIp = "192.168.4.2";
uint16_t collectorPort = 5005;
String nodeId = "tx1";

struct BleDev {
  String addr;
  String name;
  int rssi;
};

BLEScan* pScan = nullptr;
std::vector<BleDev> lastDevices;
uint32_t lastBleMs = 0;
uint32_t lastStatusMs = 0;
uint32_t calibrateUntilMs = 0;
uint32_t nearUntilMs = 0;
float nearStrength = 0.0f;
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint8_t beaconPayload[6] = {'L', 'E', 'X', 'T', 'X', 0};

// TX identity = cyan (not status-green)
static const uint8_t ID_R = 0;
static const uint8_t ID_G = 210;
static const uint8_t ID_B = 255;

void loadConfig() {
  prefs.begin("lex", true);
  wifiSsid = prefs.getString("ssid", wifiSsid);
  wifiPass = prefs.getString("pass", wifiPass);
  collectorIp = prefs.getString("collector", collectorIp);
  collectorPort = prefs.getUShort("port", collectorPort);
  nodeId = prefs.getString("node", nodeId);
  prefs.end();
}

void handleSerialProvision(uint32_t waitMs = 8000) {
  uint32_t start = millis();
  String line;
  while (millis() - start < waitMs) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n') {
        JsonDocument doc;
        if (deserializeJson(doc, line) == DeserializationError::Ok && doc["cmd"] == "provision") {
          prefs.begin("lex", false);
          if (!doc["ssid"].isNull()) prefs.putString("ssid", (const char*)doc["ssid"]);
          if (!doc["pass"].isNull()) prefs.putString("pass", (const char*)doc["pass"]);
          if (!doc["collector"].isNull()) prefs.putString("collector", (const char*)doc["collector"]);
          if (!doc["port"].isNull()) prefs.putUShort("port", (uint16_t)doc["port"]);
          if (!doc["node"].isNull()) prefs.putString("node", (const char*)doc["node"]);
          prefs.end();
          loadConfig();
          Serial.println("{\"ok\":true,\"provisioned\":true}");
          return;
        }
        line = "";
      } else if (c != '\r') {
        line += c;
      }
    }
    delay(10);
  }
}

void setLed(uint8_t r, uint8_t g, uint8_t b) {
  // DevKitC-1 v1.0=GPIO48, v1.1=GPIO38. These boards need RGB wire order.
  rgbLedWriteOrdered(48, LED_COLOR_ORDER_RGB, r, g, b);
  rgbLedWriteOrdered(38, LED_COLOR_ORDER_RGB, r, g, b);
}

void ledIdentity(uint8_t brightness = 255) {
  setLed(
      (uint8_t)((ID_R * brightness) / 255),
      (uint8_t)((ID_G * brightness) / 255),
      (uint8_t)((ID_B * brightness) / 255));
}

String serialCmdLine;

void applyCommand(JsonDocument& doc) {
  const char* cmd = doc["cmd"] | "";
  if (strcmp(cmd, "calibrate") == 0) {
    float sec = doc["seconds"] | 20.0f;
    calibrateUntilMs = millis() + (uint32_t)(sec * 1000.0f);
    Serial.printf("[TX] calibrate %.1fs\n", sec);
  } else if (strcmp(cmd, "near") == 0) {
    const char* side = doc["side"] | "none";
    nearStrength = doc["strength"] | 0.0f;
    // TX lights up when activity is near TX (or mid)
    if (strcmp(side, "tx") == 0 || strcmp(side, "mid") == 0) {
      nearUntilMs = millis() + 400;
    } else {
      nearUntilMs = 0;
    }
  }
}

void pollCommands() {
  int n = udp.parsePacket();
  while (n > 0) {
    char buf[192];
    int len = udp.read(buf, sizeof(buf) - 1);
    if (len > 0) {
      buf[len] = 0;
      JsonDocument doc;
      if (deserializeJson(doc, buf) == DeserializationError::Ok) {
        applyCommand(doc);
      }
    }
    n = udp.parsePacket();
  }

  // USB serial fallback (school WiFi often blocks PC → ESP UDP)
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      JsonDocument doc;
      if (deserializeJson(doc, serialCmdLine) == DeserializationError::Ok) {
        applyCommand(doc);
      }
      serialCmdLine = "";
    } else if (c != '\r' && serialCmdLine.length() < 180) {
      serialCmdLine += c;
    }
  }
}

void updateStatusLed() {
  if (WiFi.status() != WL_CONNECTED) {
    setLed(180, 0, 0);
    return;
  }
  if (millis() < calibrateUntilMs) {
    // Blink cyan during calibration
    bool on = ((millis() / 250) % 2) == 0;
    if (on) ledIdentity(255);
    else setLed(0, 0, 0);
    return;
  }
  if (millis() < nearUntilMs && nearStrength > 0.2f) {
    // Pulse brighter when someone is near THIS board
    uint8_t b = 140 + (uint8_t)(nearStrength * 115.0f);
    ledIdentity(b);
    return;
  }
  ledIdentity(200);
}

void ledBootTest() {
  setLed(255, 0, 0);
  delay(250);
  ledIdentity(255);
  delay(450);
  setLed(0, 0, 0);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(200);
    setLed(140, 70, 0);
    delay(80);
    setLed(0, 0, 0);
  }
}

bool initEspNow() {
  if (esp_now_init() != ESP_OK) return false;
  esp_now_peer_info_t peer{};
  memcpy(peer.peer_addr, broadcastAddress, 6);
  peer.channel = 0;
  peer.encrypt = false;
  if (esp_now_is_peer_exist(broadcastAddress)) return true;
  return esp_now_add_peer(&peer) == ESP_OK;
}

void sendStatus() {
  if (WiFi.status() != WL_CONNECTED) return;
  JsonDocument doc;
  doc["t"] = "lex.status";
  doc["node"] = nodeId;
  doc["role"] = "tx";
  doc["ble_count"] = (int)lastDevices.size();
  doc["wifi_ok"] = true;
  doc["uptime_s"] = millis() / 1000.0;
  JsonArray arr = doc["devices"].to<JsonArray>();
  for (const auto& d : lastDevices) {
    JsonObject o = arr.add<JsonObject>();
    o["addr"] = d.addr;
    o["name"] = d.name.length() ? d.name : d.addr;
    o["rssi"] = d.rssi;
  }
  char buf[2048];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  udp.beginPacket(collectorIp.c_str(), collectorPort);
  udp.write((const uint8_t*)buf, n);
  udp.endPacket();
}

void bleTick() {
  if (!pScan || millis() - lastBleMs < 4000) return;
  lastBleMs = millis();
  BLEScanResults* results = pScan->start(2, false);
  std::vector<BleDev> found;
  int raw = results ? results->getCount() : 0;
  for (int i = 0; i < raw; i++) {
    BLEAdvertisedDevice d = results->getDevice(i);
    int rssi = d.getRSSI();
    if (rssi < -85) continue;
    BleDev bd;
    bd.addr = d.getAddress().toString().c_str();
    bd.name = d.haveName() ? String(d.getName().c_str()) : String("");
    bd.rssi = rssi;
    // Prefer named or strong devices for a cleaner LEX demo list
    if (bd.name.length() == 0 && rssi < -70) continue;
    found.push_back(bd);
  }
  pScan->clearResults();
  std::sort(found.begin(), found.end(), [](const BleDev& a, const BleDev& b) {
    return a.rssi > b.rssi;
  });
  if (found.size() > 8) found.resize(8);
  lastDevices = found;
}

void setup() {
  Serial.begin(115200);
  delay(400);
  ledBootTest();
  Serial.println("[TX] boot");
  loadConfig();
  handleSerialProvision(6000);
  Serial.printf("[TX] ssid=%s collector=%s\n", wifiSsid.c_str(), collectorIp.c_str());
  connectWifi();
  udp.begin(4210);
  bool nowOk = initEspNow();
  Serial.printf("[TX] esp-now=%s\n", nowOk ? "ok" : "FAIL");

  BLEDevice::init("");
  pScan = BLEDevice::getScan();
  pScan->setActiveScan(true);
  pScan->setInterval(100);
  pScan->setWindow(80);

  updateStatusLed();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[TX] ip=");
    Serial.println(WiFi.localIP());
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setLed(180, 0, 0);
    connectWifi();
  }

  pollCommands();
  updateStatusLed();

  // ESP-NOW illuminator ~50 Hz
  beaconPayload[5]++;
  esp_now_send(broadcastAddress, beaconPayload, sizeof(beaconPayload));

  bleTick();
  if (millis() - lastStatusMs > 1000) {
    lastStatusMs = millis();
    sendStatus();
  }
  delay(20);
}
