# LEX

School WiFi sensing pilot — **one repo** for CSI boards, room UI, camera baseline, and RuView notes.

Formerly split across `LEX` + `lex-wifi-csi`; everything school-related lives here now.


## Branches

| Branch | What |
|--------|------|
| `main` | School WiFi sensing host + ESP firmware + lobby/RuView dual UI (this default) |
| `floor-locator` | Former `csh-floor-locator` — floor-plan people map (Node/Vite). Different stack; kept as its own branch. |

Archived: `lex-wifi-csi` → use this repo. Floor locator remote `csh-floor-locator` is archived into the `floor-locator` branch here.
## What you get

1. **Host + room UI** — TX↔RX CSI heat, camera people, BLE devices, compare scorecard  
2. **Firmware** — PlatformIO TX/RX ESP32 nodes  
3. **Camera ↔ CSI** — YOLO person count vs RuView/ESP32 sensing-server (`:3000`)  
4. **Phase 0** — tiny Node sim dashboard (no boards)  
5. **RuView notes** — school UI snapshot + patch under [`docs/ruview/`](docs/ruview/)

## Quick start (Mac)

```bash
cd /path/to/LEX
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m host.main --camera 0
```

Open [http://localhost:8080](http://localhost:8080).

No boards yet?

```bash
python -m host.main --sim --no-camera
```

## Boards

Provision to **this Mac’s LAN IP** (UDP `5005`):

```bash
python tools/provision.py --list
python tools/provision.py --port /dev/cu.usbmodemXXXX --role tx \
  --ssid YOURSSID --password '…' --collector 192.168.x.x
python tools/provision.py --port /dev/cu.usbmodemYYYY --role rx \
  --ssid YOURSSID --password '…' --collector 192.168.x.x
```

Flash: see [`docs/demo-runbook.md`](docs/demo-runbook.md).

School WiFi often blocks laptop→board commands (client isolation). Calibrate over USB serial, or use a phone hotspot for laptop + boards.

## Camera ↔ RuView CSI

With RuView sensing-server on `:3000`:

```bash
python tools/camera_compare.py
```

Keys: `q` quit · `s` save row · `f` toggle faces.  
Logs: `data/camera_compare/`.

Honest rule: **camera counts people in view; CSI is presence/motion correlation**, not a precise headcount.

## Layout

```
LEX/
├── host/                 CSI collector + FastAPI room UI (:8080)
├── firmware/tx|rx        PlatformIO board firmware
├── tools/                provision, probes, camera_compare, phase-0 sim
├── server/ + web/        phase-0 Node dashboard (:3847)
├── docs/                 demo runbook, slides outline, ruview/
├── data/                 replays / experiments / models (gitignored payloads)
└── requirements.txt
```

## Docs

- [docs/sensing-csi-report.md](docs/sensing-csi-report.md) — **are we using real CSI?** what we tried (RSSI vs CSI)  
- [docs/audit-2026-11-12.md](docs/audit-2026-11-12.md) — full stack audit + fixes  
- [docs/demo-runbook.md](docs/demo-runbook.md)  
- [docs/powerpoint-outline.md](docs/powerpoint-outline.md)  
- [docs/ruview/](docs/ruview/) — optional RuView fork notes + school patch  

## School demo (start / stop)

See [`docs/DEMO-TOMORROW.md`](docs/DEMO-TOMORROW.md).

```bash
./scripts/demo-stop.sh       # kill stuck camera window
./scripts/demo-start.sh      # Mac camera + CSI compare
./scripts/demo-start.sh --phone   # Continuity / iPhone camera
./scripts/demo-stop.sh --all # also unload RuView auto-start
```

## npm aliases (optional)

```bash
npm run setup      # venv + pip
npm start          # python -m host.main
npm run start:sim  # synthetic CSI, no camera
npm run demo       # clean camera demo start
npm run demo:stop  # clean stop
npm run compare    # camera ↔ RuView CSI window
npm run phase0     # tiny Node dashboard
```
