# LEX

School project workspace — **separate from RuView**.

Goal: try camera-free room presence sensing as cheaply as possible, with headmistress approval for the school pilot.

## Cheap-first plan

| Phase | What | Cost |
|-------|------|------|
| **0 (now)** | Local dashboard + software sim | €0 |
| **1** | One ESP32-S3 SuperMini as CSI node | ~€6–9 |
| **2** | Optional second node / Pi later | only if phase 1 works |

No Rust, no ESP-IDF, no Docker required for phase 0.

## Quick start

```bash
cd /path/to/LEX
npm start
```

In a second terminal:

```bash
npm run sim
```

Open http://127.0.0.1:3847

## Check installs

```bash
npm run check
```

## Layout

```
LEX/
├── server/     local API + static file server
├── web/        dashboard UI
├── tools/      presence simulator (Python)
└── README.md
```

## Not this repo

The big RuView / wifi-densepose tree stays at `/path/to/RuView`. LEX is the clean school pilot only.
