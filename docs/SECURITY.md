# Security notes

## Safe for a public GitHub repo

Source, firmware skeletons, demo scripts, and docs with **placeholder** SSIDs/IPs only.

## Never commit

- Real school Wi‑Fi passwords or `.env` / API keys  
- `data/faces/`, `data/camera_compare/`, `data/replays/`, `data/recordings/`  
- Live MAC addresses, RADIUS usernames, or student identity maps  
- Provision state under `~/Library/.../esp32-provision-state`

## Lab defaults

Firmware falls back to hotspot SSID `LEX-HOTSPOT` / password `change-me-lab-only`.  
Provision real credentials over USB; do not bake them into git.

## Network exposure

Host binds for LAN demos. Do not expose `:8080` camera/face APIs to the public internet without auth.
