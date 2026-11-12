"""Translate LEX StateHub snapshots into RuView `sensing_update` frames."""

from __future__ import annotations

import math
import time
from typing import Any


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _motion_level(motion: float, presence: float) -> str:
    if presence < 0.25 and motion < 0.28:
        return "absent"
    if motion >= 0.55:
        return "active"
    if presence < 0.25:
        return "absent"
    return "present_still"


def _persons_from_hub(snap: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, p in enumerate(snap.get("room_persons") or []):
        pos = p.get("position") or [0.0, 0.0, 0.0]
        try:
            lx = float(pos[0])
            lz = float(pos[2] if len(pos) > 2 else 0.0)
        except (TypeError, ValueError, IndexError):
            lx, lz = 0.0, 0.0
        # LEX room ≈ ±7 X, ±5 Z → RuView meters roughly 0..6 along X
        rx = _clamp((lx + 7.0) / 14.0) * 6.0
        rz = _clamp((lz + 5.0) / 10.0) * 4.0 - 2.0
        conf = _clamp(float(p.get("motion_score") or 50) / 100.0, 0.2, 0.98)
        out.append(
            {
                "id": i + 1,
                "track_id": i + 1,
                "confidence": round(conf, 3),
                "position": [round(rx, 3), 0.0, round(rz, 3)],
                "bbox": None,
            }
        )
    if out:
        return out
    # Soft blob from CSI path when presence is up but no person markers yet
    if float(snap.get("csi_presence") or 0) < 0.35:
        return []
    path = float(snap.get("csi_path_pos") or 0.5)
    motion = float(snap.get("csi_motion") or 0)
    return [
        {
            "id": 1,
            "track_id": 1,
            "confidence": round(_clamp(0.45 + motion * 0.4), 3),
            "position": [round(path * 6.0, 3), 0.0, 0.0],
            "bbox": None,
        }
    ]


def _resample_field_20(values: list[float], src_w: int, src_d: int) -> list[float]:
    """RuView gaussian splat renderer is fixed at 20×20."""
    dst = 20
    if not values or src_w <= 0 or src_d <= 0:
        return [0.0] * (dst * dst)
    if src_w == dst and src_d == dst and len(values) == dst * dst:
        return [float(_clamp(v)) for v in values]
    out = [0.0] * (dst * dst)
    for z in range(dst):
        for x in range(dst):
            sx = min(src_w - 1, int((x / dst) * src_w))
            sz = min(src_d - 1, int((z / dst) * src_d))
            idx = sz * src_w + sx
            out[z * dst + x] = float(_clamp(values[idx] if idx < len(values) else 0.0))
    return out


def hub_to_sensing_update(snap: dict[str, Any]) -> dict[str, Any]:
    """Build a RuView-compatible sensing WebSocket / API payload."""
    motion = float(snap.get("csi_motion") or 0.0)
    presence_f = float(snap.get("csi_presence") or 0.0)
    energy = float(snap.get("csi_energy") or 0.0)
    boards_ok = bool(snap.get("boards_ok"))
    path = float(snap.get("csi_path_pos") or 0.5)
    near = str(snap.get("near_side") or "none")
    pps = float(snap.get("csi_pps") or 0.0)

    # Require clearer motion than the DSP floor (calibrate caps at 0.2)
    presence = presence_f >= 0.35 or motion >= 0.28
    level = _motion_level(motion, presence_f)
    # Honest HUD: quiet room stays quiet; don't invent huge variance from baseline energy
    # amp_std is often ~5–20 in our ESP-NOW units; RuView HUD bars top out ~10
    amp_std = float(snap.get("csi_amp_std") or 0.0)
    if amp_std > 0.01:
        variance = max(0.3, min(18.0, amp_std * 0.4 + motion * 8.0))
    else:
        variance = 0.4 + motion * 12.0
    if not presence and motion < 0.12:
        variance = min(variance, 1.2)
    raw_rssi = float(snap.get("csi_rssi") or 0.0)
    mean_rssi = raw_rssi if raw_rssi < -5.0 else (-52.0 if boards_ok else -75.0)
    breath = 0.015 + presence_f * 0.08 + motion * 0.05
    motion_band = 0.02 + motion * 0.4

    sf = snap.get("signal_field") or {}
    grid = sf.get("grid_size") or [32, 1, 32]
    try:
        gw, _gh, gd = int(grid[0]), int(grid[1]), int(grid[2])
    except (TypeError, ValueError, IndexError):
        gw, gd = 32, 32
    raw_vals = [float(v) for v in (sf.get("values") or [])]
    if not raw_vals:
        raw_vals = [0.0] * (gw * gd)
    values = _resample_field_20(raw_vals, gw, gd)

    persons = _persons_from_hub(snap)
    est = max(len(persons), 1 if presence else 0)

    # Node 1 ≈ TX (left), node 2 ≈ RX (right)
    tx_boost = 1.0 if near == "tx" else (0.55 if near == "mid" else 0.25)
    rx_boost = 1.0 if near == "rx" else (0.55 if near == "mid" else 0.25)

    def _node(nid: int, boost: float, sides: tuple[str, ...]) -> dict[str, Any]:
        n_var = variance * boost
        n_motion = motion_band * boost
        on_side = near in sides or near == "none"
        return {
            "node_id": nid,
            "rssi_dbm": mean_rssi + (1.0 if nid == 2 else -2.0) + boost * motion * 6.0,
            "variance": n_var,
            "motion_band_power": n_motion,
            "stale": not boards_ok,
            "features": {
                "variance": n_var,
                "std": math.sqrt(max(0.0, n_var)),
                "motion_band_power": n_motion,
                "mean_rssi": mean_rssi,
            },
            "classification": {
                "motion_level": level if (presence and on_side) else "absent",
                "presence": bool(presence and on_side),
                "confidence": _clamp(0.5 + motion * 0.4),
            },
        }

    node_features = [
        _node(1, tx_boost, ("tx", "mid")),
        _node(2, rx_boost, ("rx", "mid")),
    ]

    nodes = [
        {
            "node_id": 1,
            "rssi_dbm": node_features[0]["rssi_dbm"],
            "position": [0.5, 0.0, 1.2],
            "amplitude": [],
            "subcarrier_count": 0,
        },
        {
            "node_id": 2,
            "rssi_dbm": node_features[1]["rssi_dbm"],
            "position": [5.5, 0.0, 1.2],
            "amplitude": [],
            "subcarrier_count": 0,
        },
    ]

    source = "esp32" if boards_ok or pps > 0.5 else "wifi"
    t = float(snap.get("ts") or time.time())

    return {
        "type": "sensing_update",
        "timestamp": t,
        "source": source,
        "nodes": nodes,
        "node_features": node_features,
        "features": {
            "mean_rssi": mean_rssi,
            "variance": variance,
            "std": math.sqrt(variance),
            "motion_band_power": motion_band,
            "breathing_band_power": breath,
            "dominant_freq_hz": 0.25 + motion * 0.2,
            "change_points": int(motion * 4),
            "spectral_power": motion_band + breath,
            "range": variance * 3,
            "iqr": variance * 1.5,
            "skewness": (path - 0.5) * 0.4,
            "kurtosis": 1.0 + motion,
        },
        "classification": {
            "motion_level": level,
            "presence": presence,
            "confidence": round(_clamp(0.55 + motion * 0.35 + presence_f * 0.1), 3),
        },
        "signal_field": {
            "grid_size": [20, 1, 20],
            "values": values,
        },
        "persons": persons,
        "estimated_persons": est,
        "path_pos": path,
        "near_side": near,
        "lex_bridge": True,
    }


def status_from_hub(snap: dict[str, Any]) -> dict[str, Any]:
    boards_ok = bool(snap.get("boards_ok"))
    pps = float(snap.get("csi_pps") or 0.0)
    live = boards_ok or pps > 0.5
    # Avoid "LIVE ESP32 Connected" when nothing is streaming — RuView maps
    # live_unverified / wifi → "live". Prefer an explicit offline signal.
    if live:
        source, source_state = "esp32", "live_verified"
        hw = "connected"
    else:
        source, source_state = "disconnected", "offline"
        hw = "waiting"
    return {
        "ok": True,
        "source": source,
        "source_state": source_state,
        "services": {
            "api": "running",
            "hardware": hw,
            "inference": "idle",
            "streaming": "active" if live else "idle",
        },
        "streaming": {
            "active_connections": 1 if live else 0,
            "total_messages": int(pps * 10),
            "uptime": 0,
        },
        "boards_ok": boards_ok,
        "demo_mode": snap.get("demo_mode") or "lobby",
        "lex_dual": True,
    }
