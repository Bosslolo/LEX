# RuView (optional upstream)

LEX is the school project. RuView is a separate open-source sensing stack we used for Mac RSSI + ESP32-S3 CSI when we wanted a ready sensing-server on `:3000`.

## What lives here

| File | Purpose |
|------|---------|
| `school.html` | Snapshot of the honest school dashboard UI |
| `school-mac-esp32.patch` | Diff of our Mac/ESP32 honesty + anti-flicker changes vs upstream `main` |

## Run RuView sensing (optional)

```bash
# fork with school branch
cd /path/to/RuView
git checkout school-mac-esp32
# then start sensing-server as you already do → http://127.0.0.1:3000
```

Remote: `https://github.com/Bosslolo/RuView` branch `school-mac-esp32`.

## Compare against RuView CSI

From this LEX repo (sensing-server must be up):

```bash
python tools/camera_compare.py
```

Camera person count is the ground-truth baseline. CSI person counts are correlation only — not a seat map.
