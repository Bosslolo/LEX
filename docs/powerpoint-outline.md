# LEX PowerPoint outline — Triple Sense

## 1. Hook
- Can we sense a room **without cameras naming people**?
- Three ways: radio bodies (CSI), camera boxes, phone radios (BLE)

## 2. Problem
- Schools/offices want occupancy / safety
- Cameras work but raise privacy
- Phones are common but not everyone carries one / airplane mode

## 3. Physics in one slide
- WiFi multipath → Channel State / RSSI disturbance when a body moves
- Diagram: TX left wall · person · RX right wall

## 4. Hardware
- 2× ESP32-S3 (power only after provision)
- Laptop: collector + webcam + web visualizer

## 5. System
- CSI bump map
- Camera person detect (P1, P2 — **no faces**)
- Anonymized BLE device density
- Fusion + “which is best” scorecard

## 6. Live demo
- Empty calibrate
- Walk the path → CSI + camera
- Cover camera / lights idea → CSI still moves
- Airplane mode → phones drop, bodies remain

## 7. Results
- Insert charts from `data/experiments/`
- On-path vs off-path
- Modality comparison

## 8. Which is best?
| Goal | Winner |
|------|--------|
| Count people in view | Camera |
| Privacy | CSI |
| Dark / occluded | CSI (then phones) |
| Rough “devices nearby” | Phones |
| No smartphone | CSI / camera |

**Conclusion:** combine them — don’t pick one forever.

## 9. Limits (teacher trust)
- CSI is not precise XY radar with 2 boards
- BLE ≠ people (shared phones, random MACs)
- Camera fails in dark / outside FOV

## 10. Future work
- True Espressif CSI IDF path
- More RX nodes
- Minecraft viz (fun, not required)
