# CSH Floor Locator

Pin **people** (not raw devices) onto a **switchable floor plan** using whatever the network tells you: AP association, RSSI, RADIUS username, hostname, MAC.

**RuView integration (later):** multi-AP fingerprinting and quality gates from the RuView research repo will land in `server/positioning/` and `server/integrations/ruview/` — not as a separate hub app. See [server/integrations/ruview/README.md](server/integrations/ruview/README.md).

## Quick start

```bash
cd csh-floor-locator
npm install
npm run dev
# → http://localhost:5190
```

Default mode uses **mock data** that cycles demo people between Erdgeschoss and 1. OG.

## How it works

```
WiFi controller / DHCP / RADIUS / ARP  →  ClientObservation[]
        ↓
Identity resolver (same radiusUser, hostname patterns, manual MAC)
        ↓
Position engine (AP zone + RSSI-weighted centroid)  ← server/positioning/
        ↓
Floor plan SVG (ground | floor1)
```

### Person ↔ device matching

Configured in `data/people.json`:

| Signal | Example |
|--------|---------|
| RADIUS username | `demo.user` on Mac + iPhone |
| Hostname patterns | `*demo*`, `Demo-*` |
| Known MACs | Your MacBook MAC |

### Position

Each device reports which **AP** it is on (and ideally **RSSI**). APs are placed on the floor plan in `data/building.json`. Multiple devices for one person are merged; position uses the strongest signals.

Accuracy without a controller API: **room-level (~3–8 m)**, not sub-meter.

## Configuration

| File | Purpose |
|------|---------|
| `data/building.json` | Floors, rooms (schematic), AP positions + BSSID map |
| `data/people.json` | Who owns which devices / usernames |
| `data/clients.json` | Live feed when `LOCATOR_SOURCE=file` |

Replace the schematic rooms in `building.json` with your real CSH layout when you have a floor plan.

## Wiring real network data

1. **Best:** WiFi controller API (UniFi, Aruba, Sophos Central…) → script writes `data/clients.json` every 30s.
2. **Good:** RADIUS accounting logs → username + MAC + NAS (AP) identifier.
3. **Fallback:** DHCP lease export with hostname + VLAN.

Set `LOCATOR_SOURCE=file` and point a poller at your controller.

### `clients.json` format

```json
{
  "clients": [
    {
      "mac": "aa:bb:cc:dd:ee:ff",
      "hostname": "Demo-iPhone",
      "radiusUser": "demo.user",
      "apId": "ap-demo-1",
      "rssi": -62,
      "ssid": "SCHOOL-WIFI",
      "lastSeen": "2026-07-01T12:00:00Z"
    }
  ]
}
```

`apId` must match an entry in `building.json` → `accessPoints[].id`.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/building` | Floor plans + AP layout |
| `GET /api/locate?floor=ground` | People on selected floor |
| `GET /api/health` | Source name |

## Next steps for CSH

1. Map real AP names/locations onto `building.json` (ask IT for AP list).
2. Add everyone you care about to `people.json`.
3. Build a poller once the WiFi platform is known (Sophos / Aruba / …).
4. Expose via Cloudflare tunnel or school LAN when ready.
