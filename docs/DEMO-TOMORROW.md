# Tomorrow — camera people-detect demo

## One-time (tonight if you want)

```bash
cd /path/to/LEX
chmod +x scripts/demo-start.sh scripts/demo-stop.sh
# .venv already set up from today
```

## Clean start (Mac built-in camera)

```bash
cd /path/to/LEX
./scripts/demo-stop.sh          # kills leftover camera window
./scripts/demo-start.sh         # opens LEX camera ↔ CSI window
```

**Quit:** click the video window, press **`q`** (or the red X).  
**Force stop:** `./scripts/demo-stop.sh`  
**Also stop RuView CSI auto-restart:** `./scripts/demo-stop.sh --all`

## Use your iPhone as the camera (Continuity)

1. iPhone unlocked, same Apple ID, Bluetooth + Wi‑Fi on, near the Mac  
2. On Mac: Control Centre → **Video effects** / camera picker → choose **iPhone**  
   (or System Settings → Continuity Camera)  
3. Find the index:

```bash
./scripts/demo-start.sh --list
```

4. Start with phone camera:

```bash
./scripts/demo-start.sh --phone
# or: ./scripts/demo-start.sh --camera 1
```

Show classmates walking through the frame → green person boxes, orange face boxes when looking at the lens.

## Phone as *viewer* (dashboard on school Wi‑Fi)

With RuView sensing already running (LaunchAgent keeps it on `:3000`):

1. On the Mac, note IP: `ipconfig getifaddr en0`  
2. On the phone (same Wi‑Fi): open  
   `http://<that-ip>:3000/ui/school.html`  
3. Or the LEX room UI (if you started `python -m host.main`):  
   `http://<that-ip>:8080`

School Wi‑Fi sometimes blocks phone→laptop. Backup: personal hotspot from your phone, Mac joins hotspot, then use the hotspot IP.

## Talk order (≈2 min)

1. Empty room / you alone → **CAMERA persons 1**  
2. Friend steps in → count goes up (boxes on people)  
3. Cover Mac camera / look away → faces drop; persons may stay  
4. Point at **CSI** line: presence/motion from ESP32 — correlation, not exact headcount  
5. Optional: switch to Continuity (`--phone`) so the room sees the phone video feed on the projector via the Mac window

## If something sticks

| Symptom | Fix |
|---------|-----|
| Window won’t close | `./scripts/demo-stop.sh` |
| Camera busy / black | stop demo, quit Zoom/Photo Booth, start again |
| CSI says offline | ESP32 on same Wi‑Fi; or ignore CSI and show camera only |
| Sensing keeps coming back | `./scripts/demo-stop.sh --all` (unloads LaunchAgent) |
| Re-enable CSI later | `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ruview.sensing.plist` |
