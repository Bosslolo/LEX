#!/usr/bin/env python3
"""Push a fake presence signal into the LEX local server (no hardware)."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:3847/api/status"


def post(payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        resp.read()


def main() -> None:
    print("LEX sim →", URL)
    print("Ctrl+C to stop")
    t0 = time.time()
    while True:
        t = time.time() - t0
        # Slow occupancy wave + a bit of motion noise
        wave = 0.5 + 0.5 * math.sin(t / 8.0)
        presence = wave > 0.45
        confidence = min(0.98, max(0.08, abs(wave - 0.5) * 1.8 + 0.2))
        motion = abs(math.sin(t * 1.7)) * (0.55 if presence else 0.12)
        try:
            post(
                {
                    "presence": presence,
                    "confidence": round(confidence, 3),
                    "motion": round(motion, 3),
                    "mode": "sim",
                    "room": "LEX Lab",
                }
            )
        except urllib.error.URLError as exc:
            print("waiting for server…", exc.reason)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
