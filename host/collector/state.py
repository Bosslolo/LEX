"""Shared live state for visualizer + logging."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import threading
import time
from pathlib import Path
from typing import Any


@dataclass
class PersonBox:
    id: int
    x: float
    y: float
    conf: float
    name: str = ""
    source: str = "camera"  # camera | face


@dataclass
class BleDeviceView:
    addr: str
    name: str
    rssi: int


@dataclass
class LiveState:
    ts: float = 0.0
    csi_motion: float = 0.0
    csi_presence: float = 0.0
    csi_energy: float = 0.0
    csi_path_pos: float = 0.5
    csi_calibrated: bool = False
    csi_calibrating: bool = False
    csi_baseline: float = 0.0
    csi_threshold: float = 0.0
    csi_pps: float = 0.0
    csi_rssi: float = -90.0
    csi_amp_mean: float = 0.0
    csi_amp_std: float = 0.0
    ble_count: int = 0

    devices: list[BleDeviceView] = field(default_factory=list)
    camera_count: int = 0
    people: list[PersonBox] = field(default_factory=list)
    named_faces: list[str] = field(default_factory=list)
    face_gallery: list[dict[str, Any]] = field(default_factory=list)
    comparison: dict[str, Any] = field(default_factory=dict)
    waterfall: list[list[float]] = field(default_factory=list)
    signal_field: dict[str, Any] = field(
        default_factory=lambda: {"grid_size": [32, 1, 32], "values": [0.0] * 1024}
    )
    room_persons: list[dict[str, Any]] = field(default_factory=list)
    camera_ok: bool = False
    boards_ok: bool = False
    tx_ip: str = ""
    rx_ip: str = ""
    near_side: str = "none"  # tx | rx | mid | none
    mode: str = "live"
    demo_mode: str = "lobby"  # lobby | lex | ruview (school lobby LED/UI switch)
    winners: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


class StateHub:
    def __init__(self, replay_dir: Path) -> None:
        self._lock = threading.Lock()
        self.state = LiveState(ts=time.time())
        self.replay_dir = replay_dir
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self._recording = False
        self._record_fh = None
        self._csi_packet_times: list[float] = []
        self._last_csi_ts: float = 0.0

    def update(self, **kwargs: Any) -> LiveState:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)
            self.state.ts = time.time()
            self.state.winners = self._scorecard(self.state)
            self.state.notes = self._notes(self.state)
            snap = LiveState(**asdict(self.state))
            if self._recording and self._record_fh:
                self._record_fh.write(json.dumps(snap.to_public()) + "\n")
                self._record_fh.flush()
            return snap

    def mark_csi_packet(self) -> float:
        now = time.time()
        with self._lock:
            self._last_csi_ts = now
            self._csi_packet_times.append(now)
            cutoff = now - 2.0
            self._csi_packet_times = [t for t in self._csi_packet_times if t >= cutoff]
            pps = len(self._csi_packet_times) / 2.0
            self.state.csi_pps = pps
            return pps

    def tick_liveness(self) -> None:
        """Decay CSI HUD/field when boards go quiet so the room doesn't freeze."""
        now = time.time()
        with self._lock:
            cutoff = now - 2.0
            self._csi_packet_times = [t for t in self._csi_packet_times if t >= cutoff]
            self.state.csi_pps = len(self._csi_packet_times) / 2.0
            age = now - self._last_csi_ts if self._last_csi_ts else 999.0
            if age < 1.2:
                return
            self.state.csi_motion *= 0.72
            if self.state.csi_motion < 0.08:
                self.state.csi_motion = 0.0
                self.state.csi_presence = 0.0
                self.state.near_side = "none"
                self.state.signal_field = {
                    "grid_size": [32, 1, 32],
                    "values": [0.0] * 1024,
                }
                self.state.room_persons = [
                    p for p in self.state.room_persons if p.get("source") != "csi"
                ]
            self.state.boards_ok = age < 4.0
            self.state.ts = now

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_public()

    def start_recording(self, name: str | None = None) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.replay_dir / f"{name or 'demo'}-{stamp}.jsonl"
        with self._lock:
            if self._record_fh:
                self._record_fh.close()
            self._record_fh = path.open("w", encoding="utf-8")
            self._recording = True
        return path

    def stop_recording(self) -> None:
        with self._lock:
            self._recording = False
            if self._record_fh:
                self._record_fh.close()
                self._record_fh = None

    @staticmethod
    def _scorecard(s: LiveState) -> dict[str, str]:
        if s.named_faces:
            presence = "faces"
        elif s.camera_count > 0:
            presence = "camera"
        elif s.csi_motion > 0.35:
            presence = "csi"
        elif s.ble_count > 0:
            presence = "phones"
        else:
            presence = "csi" if s.csi_calibrated else "—"
        return {
            "presence": presence,
            "counting": "camera" if s.camera_ok else "camera (needs view)",
            "identity": "faces" if s.named_faces else "enroll faces",
            "privacy": "csi",
            "overall_now": presence,
        }

    @staticmethod
    def _notes(s: LiveState) -> list[str]:
        notes: list[str] = []
        if s.csi_calibrating:
            notes.append("CSI calibrating — keep the room path empty.")
        if s.comparison and s.comparison.get("headline"):
            notes.append(str(s.comparison["headline"]))
        notes.append("Faces = opt-in gallery only. CSI/phones are not seat maps.")
        if s.camera_count > 0 and s.csi_motion < 0.15 and s.csi_calibrated:
            notes.append("Camera sees people; CSI quiet — maybe off the radio path.")
        if s.csi_motion > 0.45 and s.camera_count == 0:
            notes.append("CSI motion without camera — dark, occluded, or outside FOV.")
        if s.ble_count == 0 and (s.camera_count > 0 or s.csi_presence > 0.5):
            notes.append("Bodies without BLE phones nearby.")
        if s.ble_count > 0 and s.camera_count == 0 and s.csi_motion < 0.2:
            notes.append("BLE devices nearby without body motion on the CSI link.")
        return notes
