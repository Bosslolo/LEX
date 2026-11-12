#!/usr/bin/env bash
# Stop LEX demo processes cleanly (camera window + optional RuView sensing).
set -euo pipefail

echo "Stopping camera compare…"
pkill -f 'tools/camera_compare.py' 2>/dev/null || true
pkill -f 'camera_compare.py' 2>/dev/null || true

echo "Stopping LEX host (room UI)…"
pkill -f 'python -m host.main' 2>/dev/null || true
pkill -f 'host.main' 2>/dev/null || true

if [[ "${1:-}" == "--all" ]]; then
  echo "Unloading RuView sensing LaunchAgent (won't auto-restart)…"
  launchctl bootout "gui/$(id -u)/com.ruview.sensing" 2>/dev/null \
    || launchctl unload ~/Library/LaunchAgents/com.ruview.sensing.plist 2>/dev/null \
    || true
  pkill -f 'sensing-server' 2>/dev/null || true
fi

sleep 0.4
echo "Left running:"
pgrep -lf 'camera_compare|host.main|sensing-server' || echo "  (nothing)"
echo "Done. Camera should be free. Use --all to also stop RuView CSI."
