"""Floor signal field from CSI (GRID x GRID).

Honest scope with 1 TX↔RX link: peak along the radio corridor only —
not calibrated multi-person XY radar / full-room scan.
Room mapping uses ~9×7 m (school classroom).
"""

from __future__ import annotations

import math
from typing import Sequence


GRID = 32
# Visual / marker scale in meters (matches room3d.js)
ROOM_W = 9.0
ROOM_D = 7.0


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _gaussian(d: float, radius: float) -> float:
    if radius <= 1e-6:
        return 0.0
    return math.exp(-(d * d) / (2.0 * radius * radius))


def build_signal_field(
    *,
    motion: float,
    path_pos: float,
    presence: float,
    people: Sequence[object] | None = None,  # unused — kept for call-site compat
    calibrating: bool = False,
) -> dict:
    """Return `{grid_size, values, persons}` — CSI corridor only (no camera)."""
    del people  # camera intentionally not mixed into the radio field
    vals = [0.0] * (GRID * GRID)
    if calibrating:
        # Quiet floor only — never invent a person while empty-room baseline runs.
        for iz in range(GRID):
            for ix in range(GRID):
                idx = iz * GRID + ix
                gradient = math.sin(ix * 0.3) * math.sin(iz * 0.25) * 0.02
                vals[idx] = _clamp(0.04 + gradient, 0.0, 0.12)
        return {
            "grid_size": [GRID, 1, GRID],
            "values": vals,
            "peak": {"x": GRID / 2.0, "z": GRID / 2.0, "v": 0.0},
            "persons": [],
        }
    # Quiet-room floor noise
    for iz in range(GRID):
        for ix in range(GRID):
            idx = iz * GRID + ix
            gradient = math.sin(ix * 0.3) * math.sin(iz * 0.25) * 0.02
            vals[idx] = _clamp(0.04 + gradient, 0.0, 0.12)

    # TX left · RX right → corridor along x, mid z
    # path_pos 0..1 maps peak along that corridor (near TX → near RX)
    cx = 2.0 + path_pos * (GRID - 4)
    cz = GRID / 2.0
    radius = 2.0 + motion * 2.8
    amp = max(motion, 0.15 if presence > 0.5 else 0.0) * 0.85

    if amp > 0.02:
        for iz in range(GRID):
            for ix in range(GRID):
                d = math.hypot(ix - cx, iz - cz)
                beam = abs(iz - cz) / (GRID * 0.35)
                v = _gaussian(d, radius) * amp * (1.0 - 0.25 * beam)
                idx = iz * GRID + ix
                vals[idx] = _clamp(vals[idx] + v)

    peak_x, peak_z, peak_v = GRID / 2.0, GRID / 2.0, 0.0
    for iz in range(GRID):
        for ix in range(GRID):
            v = vals[iz * GRID + ix]
            if v > peak_v:
                peak_v = v
                peak_x = float(ix)
                peak_z = float(iz)

    persons: list[dict] = []
    if peak_v >= 0.22 and (motion >= 0.2 or presence > 0.5):
        # Stay on the TX↔RX line (boards sit at ±(ROOM_W/2 − 0.9), z=0).
        # path_pos 0 = next to TX, 1 = next to RX — not free XY in the room.
        tx_x = -(ROOM_W / 2.0) + 0.9
        rx_x = (ROOM_W / 2.0) - 0.9
        t = _clamp(float(path_pos), 0.0, 1.0)
        x = tx_x + t * (rx_x - tx_x)
        if t <= 0.32:
            label = "Near TX"
        elif t >= 0.68:
            label = "Near RX"
        else:
            label = "Mid path"
        persons.append(
            {
                "id": "wifi-motion",
                "source": "csi",
                "name": label,
                "path_pos": round(t, 3),
                "position": [x, 0.0, 0.0],
                "motion_score": round(motion * 100, 1),
            }
        )

    return {
        "grid_size": [GRID, 1, GRID],
        "values": vals,
        "peak": {"x": peak_x, "z": peak_z, "v": peak_v},
        "persons": persons,
    }
