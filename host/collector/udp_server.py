"""Async UDP listener for CSI + status frames from ESP32 boards."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from .board_cmd import TX_CMD_PORT, RX_CMD_PORT, _send
from .dsp import CsiDsp
from .field import build_signal_field
from .protocol import CsiFrame, StatusFrame, parse_datagram
from .state import BleDeviceView, StateHub


def _near_side(motion: float, path_pos: float, presence: float) -> str:
    if motion < 0.22 and presence < 0.5:
        return "none"
    if path_pos <= 0.35:
        return "tx"
    if path_pos >= 0.65:
        return "rx"
    return "mid"


class LexUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, dsp: CsiDsp, hub: StateHub, on_frame: Callable | None = None) -> None:
        self.dsp = dsp
        self.hub = hub
        self.on_frame = on_frame
        self._last_near_ms = 0.0

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        try:
            ts = time.time()
            frame = parse_datagram(data, ts)
            if frame is None:
                return
            ip = addr[0] if addr else ""
            if isinstance(frame, CsiFrame):
                scores = self.dsp.push(ts, frame.amp_std, frame.phase_std, frame.subcarriers)
                self.hub.mark_csi_packet()
                snap = self.hub.snapshot()
                field = build_signal_field(
                    motion=scores.motion,
                    path_pos=scores.path_pos,
                    presence=scores.presence,
                    people=snap.get("people") or [],
                )
                side = _near_side(scores.motion, scores.path_pos, scores.presence)
                self.hub.update(
                    csi_motion=scores.motion,
                    csi_presence=scores.presence,
                    csi_energy=scores.energy,
                    csi_path_pos=scores.path_pos,
                    csi_calibrated=scores.calibrated,
                    csi_calibrating=self.dsp.calibrating,
                    csi_baseline=scores.baseline,
                    csi_threshold=scores.threshold,
                    csi_rssi=float(frame.rssi),
                    csi_amp_mean=float(frame.amp_mean),
                    csi_amp_std=float(frame.amp_std),
                    waterfall=self.dsp.waterfall(),
                    signal_field={"grid_size": field["grid_size"], "values": field["values"]},
                    room_persons=field["persons"],
                    near_side=side,
                    rx_ip=ip or snap.get("rx_ip") or "",
                    boards_ok=True,
                    mode="live",
                )
                self._pulse_near(side, scores.motion, snap.get("tx_ip") or "", ip)
            elif isinstance(frame, StatusFrame):
                devices = [
                    BleDeviceView(addr=d.addr, name=d.name, rssi=d.rssi) for d in frame.devices
                ]
                self.hub.update(
                    ble_count=len(devices),
                    devices=devices,
                    tx_ip=ip,
                    boards_ok=True,
                )
            if self.on_frame:
                self.on_frame(frame, addr)
        except Exception:
            # Never let one bad datagram kill the UDP protocol.
            return

    def _pulse_near(self, side: str, motion: float, tx_ip: str, rx_ip: str) -> None:
        now = time.time()
        if now - self._last_near_ms < 0.25:
            return
        self._last_near_ms = now
        payload = {"cmd": "near", "side": side, "strength": float(motion)}
        try:
            if tx_ip:
                _send(tx_ip, TX_CMD_PORT, payload)
            if rx_ip:
                _send(rx_ip, RX_CMD_PORT, payload)
        except OSError:
            pass


async def start_udp_server(
    host: str,
    port: int,
    dsp: CsiDsp,
    hub: StateHub,
) -> tuple[asyncio.DatagramTransport, LexUdpProtocol]:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LexUdpProtocol(dsp, hub),
        local_addr=(host, port),
    )
    return transport, protocol
