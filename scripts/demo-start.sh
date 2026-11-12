#!/usr/bin/env bash
# Clean LEX demo startup for school talk.
# Usage:
#   ./scripts/demo-start.sh              # Mac FaceTime cam + RuView CSI if available
#   ./scripts/demo-start.sh --phone      # Continuity Camera (iPhone) — tries index 1
#   ./scripts/demo-start.sh --camera 2   # explicit camera index
#   ./scripts/demo-start.sh --list       # list cameras then exit
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CAMERA=0
LIST=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phone) CAMERA=1; shift ;;
    --camera) CAMERA="${2:?}"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Always start from a clean camera process
"$ROOT/scripts/demo-stop.sh" >/dev/null 2>&1 || true

if [[ "$LIST" -eq 1 ]]; then
  exec "$PY" "$ROOT/tools/list_cameras.py"
fi

# Ensure RuView sensing-server for CSI column (LaunchAgent or manual)
if ! curl -sf --max-time 0.5 http://127.0.0.1:3000/api/health >/dev/null 2>&1 \
  && ! curl -sf --max-time 0.5 http://127.0.0.1:3000/api/v1/sensing/latest >/dev/null 2>&1; then
  if [[ -f ~/Library/LaunchAgents/com.ruview.sensing.plist ]]; then
    echo "Starting RuView sensing LaunchAgent…"
    launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.ruview.sensing.plist 2>/dev/null \
      || launchctl load ~/Library/LaunchAgents/com.ruview.sensing.plist 2>/dev/null \
      || true
    sleep 1
  else
    echo "Note: no sensing on :3000 — camera still works; CSI column may be empty."
  fi
else
  echo "RuView sensing already up on :3000"
fi

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 'unknown')"
echo ""
echo "════════════════════════════════════════"
echo "  LEX camera demo"
echo "  Camera index: $CAMERA"
echo "  Quit: click window + press q   (or red X)"
echo "  Stop later:  ./scripts/demo-stop.sh"
echo "  Phone UI:    open http://${IP}:3000/ui/school.html  (same Wi‑Fi)"
echo "  Continuity:  ./scripts/demo-start.sh --phone"
echo "════════════════════════════════════════"
echo ""

exec "$PY" tools/camera_compare.py --camera "$CAMERA" --width 960 --height 540
