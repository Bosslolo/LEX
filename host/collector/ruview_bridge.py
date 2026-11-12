"""Pull RuView sensing-server API into the LEX StateHub (side-by-side demo).

Boards can only stream CSI to one UDP sink. RuView owns :5005; this bridge
polls RuView's HTTP API and mirrors motion / field / person markers into LEX
so both UIs can run at once (RuView :3000, LEX :8080).
"""

from __future__ import annotations

import asyncio
import json
import math
import urllib.error
import urllib.request
from typing import Any

from .field import GRID
from .state import StateHub


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _motion_from_class(motion_level: str, presence: bool) -> float:
    table = {
        "empty": 0.0,
        "present_still": 0.25,
        "present_moving": 0.75,
        "high_motion": 1.0,
    }
    base = table.get((motion_level or "").lower(), 0.4 if presence else 0.0)
    return base


def _resample_field(values: list[float], src_w: int, src_d: int, dst: int = GRID) -> list[float]:
    if not values or src_w <= 0 or src_d <= 0:
        return [0.0] * (dst * dst)
    if src_w == dst and src_d == dst and len(values) == dst * dst:
        return [float(_clamp(v)) for v in values]
    out = [0.0] * (dst * dst)
    for z in range(dst):
        for x in range(dst):
            sx = min(src_w - 1, int((x / dst) * src_w))
            sz = min(src_d - 1, int((z / dst) * src_d))
            out[z * dst + x] = float(_clamp(values[sz * src_w + sx]))
    return out


def _near_side_from_nodes(nodes: list[dict[str, Any]]) -> str:
    """Node 1 ≈ TX (left), node 2 ≈ RX (right) in our provision."""
    by_id = {int(n.get("node_id") or 0): n for n in nodes}
    n1 = by_id.get(1) or {}
    n2 = by_id.get(2) or {}
    m1 = _motion_from_class(
        ((n1.get("classification") or {}).get("motion_level") or ""),
        bool((n1.get("classification") or {}).get("presence")),
    )
    m2 = _motion_from_class(
        ((n2.get("classification") or {}).get("motion_level") or ""),
        bool((n2.get("classification") or {}).get("presence")),
    )
    if m1 < 0.2 and m2 < 0.2:
        return "none"
    if abs(m1 - m2) < 0.15:
        return "mid"
    return "tx" if m1 > m2 else "rx"


def _map_person(p: dict[str, Any], i: int) -> dict[str, Any]:
    pos = p.get("position") or [0.0, 0.0, 0.0]
    # RuView meters with nodes ~0..6 on X → LEX room ~±7 on X, ±5 on Z
    try:
        x = float(pos[0])
        z = float(pos[2] if len(pos) > 2 else pos[1])
    except (TypeError, ValueError, IndexError):
        x, z = 0.0, 0.0
    lx = _clamp((x + 1.0) / 8.0, 0.05, 0.95)  # rough 0..1 along path
    lz = _clamp((z + 3.0) / 6.0, 0.05, 0.95)
    return {
        "id": f"rv{p.get('id', i)}",
        "source": "csi",
        "name": "",
        "position": [(lx - 0.5) * 14.0, 0.0, (lz - 0.5) * 10.0],
        "motion_score": round(float(p.get("confidence") or 0.5) * 100, 1),
    }


def translate(payload: dict[str, Any]) -> dict[str, Any]:
    cls = payload.get("classification") or {}
    presence = bool(cls.get("presence"))
    motion = _motion_from_class(str(cls.get("motion_level") or ""), presence)
    feats = payload.get("features") or {}
    var = float(feats.get("variance") or 0.0)
    # Soft energy cue from variance (not calibrated CSI amp_std)
    energy = _clamp(var / 150.0)

    sf = payload.get("signal_field") or {}
    grid = sf.get("grid_size") or [20, 1, 20]
    try:
        gw, _gh, gd = int(grid[0]), int(grid[1]), int(grid[2])
    except (TypeError, ValueError, IndexError):
        gw, gd = 20, 20
    values = [float(v) for v in (sf.get("values") or [])]
    field_vals = _resample_field(values, gw, gd, GRID)

    persons_in = payload.get("persons") or []
    # Prefer estimated count; take top-N by confidence to avoid ghost swarm
    est = int(payload.get("estimated_persons") or 0)
    ranked = sorted(persons_in, key=lambda p: float(p.get("confidence") or 0), reverse=True)
    keep = ranked[: max(est, 1 if presence and ranked else 0)]
    room_persons = [_map_person(p, i) for i, p in enumerate(keep)]

    nodes = payload.get("node_features") or []
    side = _near_side_from_nodes(nodes)
    path_pos = {"tx": 0.25, "mid": 0.5, "rx": 0.75, "none": 0.5}.get(side, 0.5)

    return {
        "csi_motion": motion,
        "csi_presence": 1.0 if presence else 0.0,
        "csi_energy": energy,
        "csi_path_pos": path_pos,
        "csi_calibrated": True,
        "csi_calibrating": False,
        "csi_pps": float(len(payload.get("nodes") or [])) * 20.0,
        "boards_ok": bool(nodes) or bool(payload.get("nodes")),
        "near_side": side,
        "signal_field": {"grid_size": [GRID, 1, GRID], "values": field_vals},
        "room_persons": room_persons,
        "mode": "ruview-bridge",
        "notes": [
            "Radio layer mirrored from RuView CSI (same boards).",
            "2 nodes ≠ seat-accurate XY — compare honesty, not magic.",
        ],
    }


async def run_ruview_bridge(
    hub: StateHub,
    *,
    url: str = "http://127.0.0.1:3000/api/v1/sensing/latest",
    hz: float = 10.0,
) -> None:
    delay = 1.0 / max(1.0, hz)
    while True:
        try:
            raw = await asyncio.to_thread(_http_get_json, url)
            if raw:
                hub.mark_csi_packet()
                hub.update(**translate(raw))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(delay)


def _http_get_json(url: str) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lex-ruview-bridge"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
