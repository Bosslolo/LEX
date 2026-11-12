"""Synthetic DensePose-style frames from LEX presence (for RuView Live Demo)."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from host.ruview_ui.frame import hub_to_sensing_update


# COCO-17 offsets relative to torso center (canvas px, ~640x480 space)
_OFFSETS = [
    (0, -80), (-10, -90), (10, -90), (-20, -85), (20, -85),
    (-40, -40), (40, -40), (-60, 10), (60, 10), (-65, 60), (65, 60),
    (-20, 60), (20, 60), (-25, 120), (25, 120), (-25, 180), (25, 180),
]


def _keypoints(cx: float, cy: float, *, sway: float = 0.0) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for i, (ox, oy) in enumerate(_OFFSETS):
        # Mild sway on arms/legs when "active"
        extra = sway * (8.0 if i >= 7 else 2.0) * math.sin(time.time() * 3.0 + i)
        out.append(
            {
                "x": cx + ox + extra,
                "y": cy + oy,
                "confidence": 0.82,
            }
        )
    return out


def _person_from_camera(p: dict[str, Any], i: int) -> dict[str, Any]:
    """Map LEX camera person box (normalized-ish) into canvas keypoints."""
    try:
        x = float(p.get("x") or 0.5)
        y = float(p.get("y") or 0.5)
        conf = float(p.get("conf") or 0.7)
    except (TypeError, ValueError):
        x, y, conf = 0.5, 0.5, 0.7
    cx = 80.0 + x * 480.0
    cy = 120.0 + y * 220.0
    name = str(p.get("name") or "")
    return {
        "person_id": f"cam_{p.get('id', i)}",
        "confidence": max(0.55, min(0.98, conf)),
        "bbox": {"x": cx - 45, "y": cy - 95, "width": 90, "height": 200},
        "keypoints": _keypoints(cx, cy, sway=0.35),
        "zone_id": "school-room",
        "name": name,
    }


def hub_to_pose_message(snap: dict[str, Any]) -> dict[str, Any]:
    frame = hub_to_sensing_update(snap)
    cls = frame.get("classification") or {}
    presence = bool(cls.get("presence"))
    active = str(cls.get("motion_level") or "") == "active"
    persons: list[dict[str, Any]] = []

    # Stick figures ONLY from the LEX camera. Inventing COCO skeletons from
    # 2-node CSI made Live Demo look like the orange "Demo" button was on.
    # CSI presence still drives Sensing tab / classification — not fake limbs.
    cam_people = snap.get("people") or []
    if cam_people:
        persons = [
            _person_from_camera(p if isinstance(p, dict) else {}, i)
            for i, p in enumerate(cam_people[:4])
        ]
        presence = True

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    activity = "empty"
    if persons:
        activity = "walking" if active else "standing"
    elif presence:
        activity = "present_no_pose"  # CSI says someone, no camera bbox yet

    return {
        "type": "pose_data",
        "timestamp": now,
        "zone_id": "school-room",
        # RuView UI only understands signal_derived | model_inference
        "pose_source": "signal_derived",
        "data": {
            "pose": {"persons": persons},
            "confidence": float(cls.get("confidence") or 0.0),
            "activity": activity,
            "pose_source": "signal_derived",
            "csi_presence": presence,
            "metadata": {
                "frame_id": f"lex_{int(time.time() * 1000)}",
                "processing_time_ms": 8,
            },
        },
        "metadata": {
            "frame_id": f"lex_{int(time.time() * 1000)}",
            "processing_time_ms": 8,
            "lex_dual": True,
        },
    }
