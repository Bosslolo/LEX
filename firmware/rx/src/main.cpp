/**
 * LEX RX — measures ESP-NOW RSSI from TX (the sensing link), streams to collector.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_now.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

Preferences prefs;
WiFiUDP udp;

String wifiSsid = "LEX-HOTSPOT";
String wifiPass = "change-me-lab-only";
String collectorIp = "192.168.4.2";
uint16_t collectorPort = 5005;
String nodeId = "rx1";

static const int HIST = 40;
float rssiHist[HIST];
int histIdx = 0;
bool histFilled = false;
volatile int lastEspRssi = -100;
volatile uint32_t lastEspMs = 0;
uint32_t lastSendMs = 0;
uint32_t calibrateUntilMs = 0;
uint32_t nearUntilMs = 0;
float nearStrength = 0.0f;

// Demo modes (school lobby switches these over UDP/serial)
enum DemoMode : uint8_t { MODE_LOBBY = 0, MODE_LEX = 1, MODE_RUVIEW = 2 };
DemoMode demoMode = MODE_LOBBY;
uint32_t ledClockOffset = 0;  // host wall sync so TX/RX rainbow match

// RX identity = amber (not status-green)
static const uint8_t ID_R = 255;
static const uint8_t ID_G = 160;
static const uint8_t ID_B = 20;

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

void noteLedSync(uint32_t sync_ms) {
  if (sync_ms == 0) return;
  ledClockOffset = sync_ms - millis();
}

uint32_t ledClock() {
  return millis() + ledClockOffset;
}

void setDemoMode(const char* mode) {
  if (!mode) return;
  if (strcmp(mode, "lex") == 0) demoMode = MODE_LEX;
  else if (strcmp(mode, "ruview") == 0) demoMode = MODE_RUVIEW;
  else demoMode = MODE_LOBBY;
  calibrateUntilMs = 0;
  nearUntilMs = 0;
  Serial.printf("[RX] mode=%s\n", mode);
}

void applyCommand(JsonDocument& doc) {
  const char* cmd = doc["cmd"] | "";
  if (strcmp(cmd, "mode") == 0) {
    setDemoMode(doc["mode"] | "lobby");
    if (!doc["sync_ms"].isNull()) noteLedSync((uint32_t)doc["sync_ms"].as<unsigned long>());
  } else if (strcmp(cmd, "sync") == 0) {
    if (!doc["sync_ms"].isNull()) noteLedSync((uint32_t)doc["sync_ms"].as<unsigned long>());
  } else if (strcmp(cmd, "calibrate") == 0) {
    float sec = doc["seconds"] | 20.0f;
    calibrateUntilMs = millis() + (uint32_t)(sec * 1000.0f);
    Serial.printf("[RX] calibrate %.1fs\n", sec);
  } else if (strcmp(cmd, "near") == 0) {
    const char* side = doc["side"] | "none";
    nearStrength = doc["strength"] | 0.0f;
    if (strcmp(side, "rx") == 0 || strcmp(side, "mid") == 0) {
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

void ledLobbyFrame() {
  uint8_t phase = (uint8_t)((ledClock() / 40) % 256);
  uint8_t r = 0, g = 0, b = 0;
  if (phase < 85) {
    r = 255 - phase * 3;
    g = phase * 3;
    b = 0;
  } else if (phase < 170) {
    phase -= 85;
    r = 0;
    g = 255 - phase * 3;
    b = phase * 3;
  } else {
    phase -= 170;
    r = phase * 3;
    g = 0;
    b = 255 - phase * 3;
  }
  setLed(r, g, b);
}

void ledRuviewFrame() {
  bool on = ((ledClock() / 320) % 2) == 0;
  if (on) setLed(160, 0, 220);
  else setLed(40, 0, 60);
}

void updateStatusLed() {
  if (WiFi.status() != WL_CONNECTED) {
    setLed(180, 0, 0);
    return;
  }
  if (demoMode == MODE_LOBBY) {
    ledLobbyFrame();
    return;
  }
  if (demoMode == MODE_RUVIEW) {
    ledRuviewFrame();
    return;
  }
  if (millis() < calibrateUntilMs) {
    bool on = ((millis() / 250) % 2) == 0;
    if (on) ledIdentity(255);
    else setLed(0, 0, 0);
    return;
  }
  if (millis() < nearUntilMs && nearStrength > 0.2f) {
    uint8_t b = 140 + (uint8_t)(nearStrength * 115.0f);
    ledIdentity(b);
    return;
  }
  ledIdentity(200);
}

void ledRainbowBoot() {
  // Full RGB sweep so you can see the pixel works, then settle on RX amber.
  const uint8_t steps[][3] = {
      {255, 0, 0},
      {255, 90, 0},
      {255, 200, 0},
      {0, 220, 0},
      {0, 180, 255},
      {255, 160, 20},  // RX identity
      {120, 0, 255},
      {255, 0, 180},
  };
  for (unsigned i = 0; i < sizeof(steps) / sizeof(steps[0]); i++) {
    setLed(steps[i][0], steps[i][1], steps[i][2]);
    delay(140);
  }
  ledIdentity(255);
  delay(350);
}

void ledBootTest() {
  ledRainbowBoot();
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(200);
    setLed(140, 70, 0);
    delay(80);
    setLed(0, 0, 0);
  }
}

void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  (void)data;
  (void)len;
  if (!info || !info->rx_ctrl) return;
  lastEspRssi = info->rx_ctrl->rssi;
  lastEspMs = millis();
}

bool initEspNow() {
  if (esp_now_init() != ESP_OK) return false;
  return esp_now_register_recv_cb(onEspNowRecv) == ESP_OK;
}

float meanN(const float* a, int n) {
  float s = 0;
  for (int i = 0; i < n; i++) s += a[i];
  return s / n;
}

float stdN(const float* a, int n, float m) {
  float s = 0;
  for (int i = 0; i < n; i++) {
    float d = a[i] - m;
    s += d * d;
  }
  return sqrtf(s / n);
}

void sendCsi() {
  if (WiFi.status() != WL_CONNECTED) return;

  // Prefer ESP-NOW link RSSI; fall back to AP RSSI only if link silent
  float rssi = (millis() - lastEspMs < 500) ? (float)lastEspRssi : (float)WiFi.RSSI();
  rssiHist[histIdx++] = rssi;
  if (histIdx >= HIST) {
    histIdx = 0;
    histFilled = true;
  }
  int n = histFilled ? HIST : max(histIdx, 1);
  float m = meanN(rssiHist, n);
  float sd = stdN(rssiHist, n, m);

  float sc[32];
  for (int i = 0; i < 32; i++) {
    sc[i] = 40.0f + rssiHist[(histIdx + i) % n] + 2.0f * sinf(i * 0.4f);
  }

  JsonDocument doc;
  doc["t"] = "lex.csi";
  doc["node"] = nodeId;
  doc["rssi"] = rssi;
  doc["amp_mean"] = fabsf(m);
  doc["amp_std"] = sd;
  doc["phase_std"] = sd * 0.5f;
  doc["link"] = (millis() - lastEspMs < 500) ? "espnow" : "ap-fallback";
  JsonArray arr = doc["sc"].to<JsonArray>();
  for (int i = 0; i < 32; i++) arr.add(sc[i]);

  char buf[768];
  size_t len = serializeJson(doc, buf, sizeof(buf));
  udp.beginPacket(collectorIp.c_str(), collectorPort);
  udp.write((const uint8_t*)buf, len);
  udp.endPacket();
}

void setup() {
  Serial.begin(115200);
  delay(400);
  ledBootTest();
  Serial.println("[RX] boot");
  loadConfig();
  handleSerialProvision(6000);
  Serial.printf("[RX] ssid=%s collector=%s\n", wifiSsid.c_str(), collectorIp.c_str());
  connectWifi();
  udp.begin(4211);
  bool nowOk = initEspNow();
  Serial.printf("[RX] esp-now=%s\n", nowOk ? "ok" : "FAIL");
  updateStatusLed();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[RX] ip=");
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
  if (millis() - lastSendMs >= 50) {
    lastSendMs = millis();
    sendCsi();
  }
}
