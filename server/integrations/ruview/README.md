# RuView → Floor Locator (planned)

The standalone [RuView](https://github.com/ruvnet/RuView) repo on the dev Mac is **reference material**. Positioning ideas will land here—not as a full vendored copy of the CSI/ESP32 stack.

## What we take from RuView (later)

| Phase | RuView source | Floor locator target |
|-------|---------------|----------------------|
| Now | — | Controller RSSI + AP zone (`server/locator.ts`, `server/positioning/`) |
| Next | Multi-AP fingerprinting | `server/positioning/fingerprint.ts` + `data/fingerprints.json` |
| Next | Quality gates (stale RSSI, min APs) | `server/positioning/quality-gate.ts` |
| Optional | RSSI motion overlay | Sidecar or `sensing-client.ts` |
| Future | ESP32 CSI stream | WebSocket ingest — only if CSH deploys nodes |

## What we do **not** merge

ESP32 firmware, vitals/pose models, Home Assistant blueprints, full Rust workspace, Docker sensing stack.

## Why

CSH floor plans need **room-level** placement from WiFi controller data (AP association + RSSI). RuView’s own research notes RSSI-only is weak for sub-meter pose but useful for fingerprint refinement—same problem as our locator.

## Dev note

You can delete the top-level `RuView/` folder from `Informatik/` once fingerprinting is ported. Until then, keep it locally as algorithm reference only—it is **not** monitored separately on Laurin IT Check.
