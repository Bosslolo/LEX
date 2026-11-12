# School lobby — one firmware, two demos

## Idea

Boards stay on **power + WiFi**, talking to the **school server**.  
Your Mac only opens a URL. The lobby picks the demo; boards change LEDs; you jump into that UI. Exit returns to rainbow.

| Lobby choice | Board LEDs | Browser goes to |
|--------------|------------|-----------------|
| *(idle)* | Rainbow cycle | `http://<school>:8080/` |
| **LEX** | TX cyan · RX amber | `http://<school>:8080/lex` |
| **RuView** | Purple pulse | `http://<school>:3000/` (stock RuView UI) |
| **Back to lobby** | Rainbow again | `/` |

Command to boards (UDP 4210/4211 + USB serial fallback):

```json
{"cmd":"mode","mode":"lobby"|"lex"|"ruview"}
```

## Who owns what

| Piece | Owner |
|-------|--------|
| LED look | **Unified LEX firmware** modes (lobby / lex / ruview) |
| CSI / status UDP | Boards → school server `:5005` (LEX protocol) |
| LEX visuals | School host `:8080/lex` |
| RuView visuals | **Stock `_ruview_ref/ui`** on `:3000`, sensing WS on `:3001`, fed from the same LEX hub |

One ESP image cannot be both native RuView CSI firmware and LEX LED lobby at once. Dual mode keeps **LEX firmware** on the boards and runs the **real RuView UI** against mirrored sensing frames. For a native RuView CSI A/B, flash RuView firmware and run `sensing-server`, then start LEX with `--ruview` (skips UDP bind + built-in UI adapter).

## School server bring-up

```powershell
# Flash unified LEX firmware (once)
.\.venv\Scripts\python.exe -m platformio run -t upload --upload-port COM7 -d firmware\tx
.\.venv\Scripts\python.exe -m platformio run -t upload --upload-port COM5 -d firmware\rx

# Point boards at the demo server (power-only target)
python tools/provision.py --port COM7 --role tx --ssid SCHOOL-WIFI --password "…" --collector 192.168.1.50
python tools/provision.py --port COM5 --role rx --ssid SCHOOL-WIFI --password "…" --collector 192.168.1.50

# On 192.168.1.50 — lobby + LEX (:8080) + stock RuView UI (:3000 / WS :3001)
python -m host.main --camera 0
```

Clients: open `http://192.168.1.50:8080/` → LEX or RuView → Lobby to return (`:8080/`).

### Power-only checklist

| Ready? | Item |
|--------|------|
| Yes | LEX firmware with lobby/lex/ruview LED modes |
| Yes | Boards → collector CSI/status UDP `:5005` (works without USB) |
| Do this | Re-provision both boards `--collector 192.168.1.50` while USB still plugged |
| Do this | Run `python -m host.main --camera 0` on **192.168.1.50** (firewall: TCP 8080/3000/3001, UDP 5005) |
| Do this | Confirm `boards_ok` + `csi_pps` on the new host, then unplug USB |
| Maybe | Lobby LED mode over WiFi (UDP 4210/4211). School WiFi often blocks server→ESP; if LEDs stay rainbow, use serial once or a shared hotspot |

If school WiFi blocks PC→ESP UDP, mode changes only work while USB is plugged (serial fallback), or put phone hotspot under all three devices.
