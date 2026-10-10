// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC reference hardware bridge for an ESP32 (ADR-0032). Not a certified product (brief section 2).
//
// Supervised inputs: each loop is read on an ADC pin as a fraction of 3.3 V. With an end-of-line resistor the
// idle loop reads about half the supply ("rest"), the closed contact adds a parallel resistor ("active"), a
// broken wire reads near the supply and a short near zero (both "fault"). Changes are debounced, kept in a small
// queue and sent to EVAC over HTTPS with a unique id until EVAC confirms them; a heartbeat goes out every 10 s.
// Build with the Arduino ESP32 core; set the values in the CONFIG block (or load them from NVS).

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ---------------------------------------------------------------- CONFIG
static const char *WIFI_SSID = "venue-ops";
static const char *WIFI_PASS = "change-me";
static const char *EVAC_URL = "https://evac.example.org/bridge/v1/";  // trailing slash
static const char *EVAC_TOKEN = "evacb_...";
static const char *CA_PEM = nullptr;  // PEM of the server's CA; nullptr = Arduino's default bundle if set up

struct Input {
  const char *key;  // must match the input key configured in EVAC
  int pin;          // ADC1 pin (ADC2 is unusable while Wi-Fi is on)
  float restLo, restHi, activeLo, activeHi;  // bands as fraction of the supply
};
static Input INPUTS[] = {
  {"in1", 34, 0.35f, 0.65f, 0.05f, 0.35f},
  {"in2", 35, 0.35f, 0.65f, 0.05f, 0.35f},
};
static const int N_INPUTS = sizeof(INPUTS) / sizeof(INPUTS[0]);
static const uint32_t DEBOUNCE_MS = 200;
static uint32_t heartbeatMs = 10000;
static const int STATUS_LED = 2;
// ---------------------------------------------------------------- end CONFIG

static const char *stable[N_INPUTS];
static const char *pendingState[N_INPUTS];
static uint32_t pendingSince[N_INPUTS];

struct Change { char id[33]; int input; const char *state; };
static Change queue[16];
static int qHead = 0, qLen = 0;

static const char *classify(const Input &in, float ratio) {
  if (ratio >= in.activeLo && ratio < in.activeHi) return "active";
  if (ratio >= in.restLo && ratio <= in.restHi) return "rest";
  return "fault";
}

static void enqueue(int input, const char *state) {
  if (qLen == 16) { qHead = (qHead + 1) % 16; qLen--; }  // drop the oldest; the heartbeat re-sends states anyway
  Change &c = queue[(qHead + qLen) % 16];
  snprintf(c.id, sizeof(c.id), "%08lx%08lx%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random(),
           (unsigned long)esp_random(), (unsigned long)millis());
  c.input = input;
  c.state = state;
  qLen++;
}

static int post(const char *path, const String &body, String &answer) {
  WiFiClientSecure tls;
  if (CA_PEM) tls.setCACert(CA_PEM); else tls.setInsecure();  // set CA_PEM in production
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(tls, String(EVAC_URL) + path)) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + EVAC_TOKEN);
  int code = http.POST(body);
  answer = http.getString();
  http.end();
  return code;
}

static bool flush() {
  while (qLen > 0) {
    Change &c = queue[qHead];
    String body = String("{\"input\":\"") + INPUTS[c.input].key + "\",\"state\":\"" + c.state + "\",\"id\":\"" + c.id + "\"}";
    String answer;
    int code = post("input", body, answer);
    if (code == 200 || code == 400 || code == 401 || code == 404) {  // done, or refused for good
      qHead = (qHead + 1) % 16;
      qLen--;
      continue;
    }
    return false;  // unreachable: keep it, retry later
  }
  return true;
}

static bool heartbeat() {
  String body = "{\"inputs\":{";
  for (int i = 0; i < N_INPUTS; i++) {
    if (i) body += ",";
    body += String("\"") + INPUTS[i].key + "\":\"" + (stable[i] ? stable[i] : "rest") + "\"";
  }
  body += "},\"info\":{\"firmware\":\"evac-bridge-esp32 1.0.0\",\"model\":\"esp32\",\"rssi\":\"" + String(WiFi.RSSI()) + "\"}}";
  String answer;
  int code = post("heartbeat", body, answer);
  int at = answer.indexOf("\"heartbeat_seconds\":");
  if (code == 200 && at >= 0) heartbeatMs = max(2000L, answer.substring(at + 20).toInt() * 1000L);
  return code == 200;
}

void setup() {
  pinMode(STATUS_LED, OUTPUT);
  analogReadResolution(12);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void loop() {
  static uint32_t lastBeat = 0, retryAt = 0, backoffMs = 1000;
  uint32_t now = millis();
  for (int i = 0; i < N_INPUTS; i++) {
    float ratio = analogRead(INPUTS[i].pin) / 4095.0f;
    const char *s = classify(INPUTS[i], ratio);
    if (stable[i] && strcmp(s, stable[i]) == 0) { pendingState[i] = nullptr; continue; }
    if (!pendingState[i] || strcmp(s, pendingState[i]) != 0) { pendingState[i] = s; pendingSince[i] = now; continue; }
    if (now - pendingSince[i] >= DEBOUNCE_MS) { stable[i] = s; pendingState[i] = nullptr; enqueue(i, s); }
  }
  if (WiFi.status() != WL_CONNECTED) { digitalWrite(STATUS_LED, (now / 250) % 2); delay(20); return; }
  if (now >= retryAt && (qLen > 0 || now - lastBeat >= heartbeatMs)) {
    bool ok = flush() && heartbeat();
    if (ok) { lastBeat = now; backoffMs = 1000; retryAt = now; digitalWrite(STATUS_LED, HIGH); }
    else { retryAt = now + backoffMs; backoffMs = min(backoffMs * 2, (uint32_t)30000); digitalWrite(STATUS_LED, LOW); }
  }
  delay(20);
}
