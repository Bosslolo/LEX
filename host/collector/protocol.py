"""UDP / JSON line protocol shared with ESP32 firmware."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


MAGIC_CSI = "lex.csi"
MAGIC_STATUS = "lex.status"


@dataclass
class CsiFrame:
    ts: float
    node: str
    rssi: float
    amp_mean: float
    amp_std: float
    phase_std: float
    subcarriers: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], ts: float) -> "CsiFrame":
        return cls(
            ts=ts,
            node=str(data.get("node", "rx")),
            rssi=float(data.get("rssi", 0.0)),
            amp_mean=float(data.get("amp_mean", 0.0)),
            amp_std=float(data.get("amp_std", 0.0)),
            phase_std=float(data.get("phase_std", 0.0)),
            subcarriers=[float(x) for x in data.get("sc", data.get("subcarriers", []))[:64]],
        )


@dataclass
class BleDevice:
    addr: str
    name: str
    rssi: int


@dataclass
class StatusFrame:
    ts: float
    node: str
    role: str
    ble_count: int
    wifi_ok: bool
    uptime_s: float
    devices: list[BleDevice] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], ts: float) -> "StatusFrame":
        devices: list[BleDevice] = []
        for item in data.get("devices", []) or []:
            if not isinstance(item, dict):
                continue
            devices.append(
                BleDevice(
                    addr=str(item.get("addr", "")),
                    name=str(item.get("name", "(no name)")),
                    rssi=int(item.get("rssi", -100)),
                )
            )
        return cls(
            ts=ts,
            node=str(data.get("node", "tx")),
            role=str(data.get("role", "tx")),
            ble_count=int(data.get("ble_count", len(devices))),
            wifi_ok=bool(data.get("wifi_ok", True)),
            uptime_s=float(data.get("uptime_s", 0.0)),
            devices=devices,
        )


def parse_datagram(raw: bytes, ts: float) -> CsiFrame | StatusFrame | None:
    try:
        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            return None
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    kind = data.get("t") or data.get("type") or data.get("magic")
    try:
        if kind in (MAGIC_CSI, "csi"):
            return CsiFrame.from_dict(data, ts)
        if kind in (MAGIC_STATUS, "status"):
            return StatusFrame.from_dict(data, ts)
        if "amp_std" in data or "sc" in data:
            return CsiFrame.from_dict(data, ts)
        if "ble_count" in data or "devices" in data:
            return StatusFrame.from_dict(data, ts)
    except (TypeError, ValueError, KeyError):
        return None
    return None
