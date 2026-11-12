"""Floor signal field from CSI + optional camera people (GRID x GRID).

Honest scope (same as RuView field_localize with 1 link): peak along TX↔RX
corridor only — not calibrated multi-person XY radar. Camera dots are real
image positions mapped into the room when available.
"""

from __future__ import annotations

import math
from typing import Sequence


GRID = 32


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
    people: Sequence[object] | None = None,
) -> dict:
    """Return `{grid_size:[GRID,1,GRID], values:[GRID*GRID floats]}`."""
    vals = [0.0] * (GRID * GRID)
    # Quiet-room floor noise (RuView _flatField vibe)
    for iz in range(GRID):
        for ix in range(GRID):
            idx = iz * GRID + ix
            gradient = math.sin(ix * 0.3) * math.sin(iz * 0.25) * 0.02
            vals[idx] = _clamp(0.04 + gradient, 0.0, 0.12)

    # TX at left-center, RX at right-center → corridor along x, mid z
    # path_pos 0..1 maps peak along that corridor
    cx = 2.0 + path_pos * (GRID - 4)
    cz = GRID / 2.0
    radius = 2.0 + motion * 2.8
    amp = max(motion, 0.15 if presence > 0.5 else 0.0) * 0.85

    if amp > 0.02:
        for iz in range(GRID):
            for ix in range(GRID):
                d = math.hypot(ix - cx, iz - cz)
                # Slight elongation along the beam (tomography corridor)
                beam = abs(iz - cz) / (GRID * 0.35)
                v = _gaussian(d, radius) * amp * (1.0 - 0.25 * beam)
                idx = iz * GRID + ix
                vals[idx] = _clamp(vals[idx] + v)

    def _xy(p: object) -> tuple[float, float, float, object]:
        if isinstance(p, dict):
            return (
                float(p.get("x", 0.5)),
                float(p.get("y", 0.5)),
                float(p.get("conf", 0.6)),
                p.get("id", "?"),
            )
        return (
            float(getattr(p, "x", 0.5)),
            float(getattr(p, "y", 0.5)),
            float(getattr(p, "conf", 0.6)),
            getattr(p, "id", "?"),
        )

    # Camera people → extra hot spots (real where-in-frame → room map)
    if people:
        for p in people:
            px, py, conf, _ = _xy(p)
            ix = _clamp(px, 0.05, 0.95) * (GRID - 1)
            iz = _clamp(py, 0.05, 0.95) * (GRID - 1)
            for z in range(GRID):
                for x in range(GRID):
                    d = math.hypot(x - ix, z - iz)
                    vals[z * GRID + x] = _clamp(
                        vals[z * GRID + x] + _gaussian(d, 1.4) * 0.55 * conf
                    )

    peak_x, peak_z, peak_v = 10.0, 10.0, 0.0
    for iz in range(GRID):
        for ix in range(GRID):
            v = vals[iz * GRID + ix]
            if v > peak_v:
                peak_v = v
                peak_x = float(ix)
                peak_z = float(iz)

    persons: list[dict] = []
    if peak_v >= 0.22 and (motion >= 0.2 or presence > 0.5):
        # Map grid cell → room coords roughly [-5..5]
        persons.append(
            {
                "id": "radio",
                "source": "csi",
                "position": [(peak_x / (GRID - 1) - 0.5) * 14.0, 0.0, (peak_z / (GRID - 1) - 0.5) * 10.0],
                "motion_score": round(motion * 100, 1),
            }
        )
    if people:
        for i, p in enumerate(people):
            px, py, conf, pid = _xy(p)
            if isinstance(p, dict):
                pname = str(p.get("name") or "")
                psrc = str(p.get("source") or "camera")
            else:
                pname = str(getattr(p, "name", "") or "")
                psrc = str(getattr(p, "source", "camera") or "camera")
            persons.append(
                {
                    "id": f"cam{pid if pid != '?' else i}",
                    "source": "face" if pname else psrc,
                    "name": pname,
                    "position": [(px - 0.5) * 14.0, 0.0, (py - 0.5) * 10.0],
                    "motion_score": round(conf * 80, 1),
                }
            )

    return {
        "grid_size": [GRID, 1, GRID],
        "values": vals,
        "peak": {"x": peak_x, "z": peak_z, "v": peak_v},
        "persons": persons,
    }
