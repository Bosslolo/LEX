# LEX sensing report — are we still using CSI?

**Short answer: no.** The live school stack does **not** read Espressif Channel State Information (CSI). It measures **ESP-NOW link RSSI** on one RX board, packages that as `lex.csi` frames (names kept for history / RuView-shaped APIs), and estimates **presence / motion along the TX↔RX path**.

True CSI (per-subcarrier complex H) was a goal and was touched via RuView’s ESP32 path, but the boards running LEX firmware today are an **RSSI illuminator + sensor** pair.

---

## What “CSI” means here vs in papers

| Term | Meaning |
|------|---------|
| **True CSI** | Per-subcarrier channel matrix from the Wi‑Fi PHY (amplitude + phase). Needs CSI-capable chip/driver (e.g. Espressif CSI examples / RuView node firmware). |
| **LEX live link** | TX sends ESP-NOW beacons (~50 Hz). RX records `rx_ctrl->rssi`, keeps a short history, sends `amp_mean`, `amp_std`, and a synthetic `sc[]` array to the host. |
| **Protocol name `lex.csi`** | Historical / dual-UI label. Host DSP, field map, and RuView adapter still say “CSI” in code and HUD. |

Firmware source of truth:

- `firmware/tx` — ESP-NOW illuminator + BLE device list + Wi‑Fi uplink  
- `firmware/rx` — ESP-NOW RSSI history → UDP JSON (`t: lex.csi`)  
- Synthetic subcarriers on RX: `sc[i] = 40 + rssiHist[…] + 2*sin(i*0.4)` — **not** PHY CSI  

---

## What we have tried so far

### 1. Two-board LEX radio path (current school demo)

**Tried:** 1× TX + 1× RX ESP32, empty-room calibrate, motion from RSSI variance vs baseline, presence threshold, corridor heat map, person figure on the TX↔RX line.

**Works for:** “Something moved on the radio path,” rough near-TX / mid / near-RX after hardening.

**Does not work for:** Full-room XY, seat maps, multi-person DensePose, stable “you are at desk X” without strong assumptions.

**Hardening history (host DSP):**

1. Raw variance → motion score (too flickery)  
2. EMA + empty-room calibrate + burst/pre-cal honesty  
3. Fake **subcarrier tilt** for `path_pos` → unstable (tilt was noise on synthetic `sc[]`)  
4. Replaced tilt with **RSSI fade vs baseline**, hold-when-still, side hysteresis / zone snap  

### 2. Camera as ground truth (then removed from LEX display)

**Tried:** Webcam + person detect, compare counts / presence to radio, optional faces.

**Outcome:** Useful for honesty (“camera counts; radio correlates”). Camera was later **stripped from the LEX room UI** for the radio-only school story; compare tooling remains under `tools/camera_compare.py` and docs.

### 3. BLE / phone density

**Tried:** TX scans BLE, status frames list anonymized devices.

**Outcome:** Rough “devices nearby,” not people. Airplane mode / shared phones break the mapping. Still in the Tools drawer.

### 4. RuView dual stack (UI + optional native CSI)

**Tried:**

- Run **real RuView UI** (`_ruview_ref/ui`) from LEX on `:3000` / sensing WS `:3001`  
- Adapter: LEX hub → RuView `sensing_update` / pose stubs  
- Signal-derived Live Demo (no invented stick figures; orange Demo button still invents poses — avoid it)  
- DensePose / `.rvf` model APIs stubbed as `no_model` (needs 4+ real CSI nodes + weights — we don’t have that)  
- Optional path: flash RuView CSI firmware + `sensing-server`, LEX `--ruview` bridge  

**Outcome:** Dual UI for demos. With LEX firmware, RuView shows **mirrored RSSI-derived sensing**, not a loaded DensePose model. Native RuView CSI firmware is a separate A/B, not the default school flash.

### 5. School / ops experiments

**Tried:** Lobby LED modes (rainbow / LEX cyan-amber / RuView purple), UDP/serial commands, power-only boards after provision, cutover collector IP (demo LAN host), school Wi‑Fi client isolation (PC→board UDP often blocked → serial fallback).

**Outcome:** Sensing UDP board→PC usually works; command path often needs USB or hotspot.

### 6. Explicitly not pursued (or abandoned as primary)

| Idea | Why not (for this pilot) |
|------|---------------------------|
| Invented CSI skeletons from 2 RSSI nodes | Dishonest; looked like RuView “Demo” stick figures |
| Full 9×7 m seat map with 2 nodes | Physics: one link = corridor, not a grid radar |
| Relying on synthetic `sc[]` tilt for position | Random walk; replaced |
| Shipping a fake purple “RuView skin” of LEX | Rejected — dual means real RuView UI + LEX radio |

---

## Current sensing pipeline (honest)

```
TX ESP-NOW beacon  →  RX RSSI history
                         ↓
              amp_mean / amp_std (+ fake sc[])
                         ↓  UDP :5005  lex.csi
              host CsiDsp (calibrate, motion, presence,
                           fade→path zone with hysteresis)
                         ↓
         LEX UI :8080  ·  RuView UI adapter :3000/:3001
```

**Still “radio sensing”: yes.**  
**Still “true CSI”: no.**

---

## Limits to state in demos / slides

1. Two nodes → **one path**, not a room scan.  
2. Labels like CSI / `lex.csi` / “Where (WiFi path)” mean **RSSI-disturbance sensing**.  
3. Near TX / mid / near RX is a **soft, laggy estimate** (fade + dwell), not localization.  
4. RuView Live Demo without a `.rvf` model is **signal-derived**; model APIs correctly report no model loaded.  
5. BLE ≠ occupants.

---

## If we want real CSI later

1. Flash / run **CSI-capable** firmware (RuView ESP32 CSI nodes or Espressif CSI example), not LEX RSSI-only RX.  
2. Prefer **≥4 nodes** before DensePose / `.rvf` expectations.  
3. Keep LEX RSSI path as the **simple school demo**; treat true CSI as a parallel experiment.  
4. Rename UI strings from “CSI” → “WiFi path / RSSI” when presenting, or keep “CSI” only with a footnote.

---

## Key code pointers

| Piece | Path |
|-------|------|
| RX RSSI → UDP | `firmware/rx/src/main.cpp` (`sendCsi`) |
| TX illuminator | `firmware/tx/src/main.cpp` |
| Motion / path DSP | `host/collector/dsp.py` |
| Corridor field + figure | `host/collector/field.py` |
| RuView frame adapter | `host/ruview_ui/frame.py`, `pose.py`, `http_app.py` |
| Dual / cutover notes | `docs/mode-switch.md` |
| RuView upstream notes | `docs/ruview/README.md` |

---

*Report written for the school LEX pilot so demos stay honest about RSSI-based sensing vs true CSI.*
