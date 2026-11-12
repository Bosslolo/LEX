# Demo runbook

## At home (first time)
1. From the **LEX** repo root: `python -m venv .venv` then activate and `pip install -r requirements.txt`
2. Install PlatformIO: `pip install platformio`
3. Flash TX: `cd firmware/tx && pio run -t upload --upload-port COM7`
4. Flash RX: `cd firmware/rx && pio run -t upload --upload-port COM5`
5. Provision (use your laptop LAN IP):
   ```
   python tools/provision.py --port COM7 --role tx --ssid YOURSSID --password YOURPASS --collector 192.168.x.x
   python tools/provision.py --port COM5 --role rx --ssid YOURSSID --password YOURPASS --collector 192.168.x.x
   ```
6. Unplug data cables; power boards from USB chargers.
7. Start host: `python -m host.main`
8. Open `http://localhost:8080` — press **Calibrate CSI** in an empty path.

## School day
1. Connect laptop to school WiFi; note laptop IP (`ipconfig`).
2. Temporarily plug each board USB, re-run `provision.py` with school SSID/password + new collector IP.
3. Power-only again; start `python -m host.main`
4. Phones on same WiFi can open `http://<laptop-ip>:8080`

If school WiFi blocks device-to-device UDP: use a phone hotspot and provision that SSID instead.

## Live talk sequence (≈3 min)
1. Presenter mode on the visualizer
2. Show empty fusion map
3. Walk between boards → CSI bump + camera P-boxes
4. Cover webcam → CSI continues
5. Airplane mode on phones → phone map drops
6. Point at scorecard winners changing
7. Slide: limits + which-is-best table

## Backup if RF/WiFi fails
```
python -m host.main --sim --no-camera
```
Still shows the triple UI with synthetic motion for the story.
