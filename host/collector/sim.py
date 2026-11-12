"""Synthetic CSI / BLE generator for UI development and offline demos."""

from __future__ import annotations

import asyncio
import math
import random
import time

from .dsp import CsiDsp
from .field import build_signal_field
from .state import BleDeviceView, StateHub


async def run_simulator(dsp: CsiDsp, hub: StateHub, hz: float = 20.0) -> None:
    dsp.start_calibration(duration_s=8.0)
    t0 = time.time()
    interval = 1.0 / hz
    while True:
        t = time.time() - t0
        phase = t % 12.0
        walking = 3.0 < phase < 7.5
        amp_std = 0.04 + random.uniform(0, 0.02)
        phase_std = 0.03 + random.uniform(0, 0.02)
        if walking:
            amp_std = 0.35 + 0.25 * abs(math.sin(t * 3.2)) + random.uniform(0, 0.08)
            phase_std = 0.2 + random.uniform(0, 0.1)
        sc = [
            20
            + 4 * math.sin(i * 0.2 + t)
            + (8 * math.sin(t * 2.5 + i * 0.05) if walking else 0)
            + random.uniform(-1, 1)
            for i in range(48)
        ]
        # amp_mean rises while "near RX" so fade-based path matches live boards
        amp_mean = 48.0 + (10.0 if walking else 0.0) * max(0.0, math.sin(t * 0.7))
        scores = dsp.push(
            time.time(),
            amp_std,
            phase_std,
            sc,
            amp_mean=amp_mean,
            rssi=-amp_mean,
        )
        devices = [
            BleDeviceView(addr="aa:bb:cc:dd:ee:01", name="DemoPhone", rssi=-55 if walking else -72),
            BleDeviceView(addr="aa:bb:cc:dd:ee:02", name="Watch", rssi=-68),
        ]
        if walking:
            devices.append(
                BleDeviceView(addr="aa:bb:cc:dd:ee:03", name="GuestPixel", rssi=-60)
            )
        path = (0.5 + 0.35 * math.sin(t * 0.7)) if walking else scores.path_pos
        side = scores.near_side
        if walking:
            if path <= 0.32:
                side = "tx"
            elif path >= 0.68:
                side = "rx"
            else:
                side = "mid"
        field = build_signal_field(
            motion=scores.motion,
            path_pos=path,
            presence=scores.presence,
            people=[],
        )
        hub.mark_csi_packet()
        hub.update(
            csi_motion=scores.motion,
            csi_presence=scores.presence,
            csi_energy=scores.energy,
            csi_path_pos=path,
            csi_calibrated=scores.calibrated,
            csi_calibrating=dsp.calibrating,
            csi_baseline=scores.baseline,
            csi_threshold=scores.threshold,
            csi_amp_mean=amp_mean,
            waterfall=dsp.waterfall()[-12:],
            signal_field={"grid_size": field["grid_size"], "values": field["values"]},
            room_persons=field["persons"],
            near_side=side,
            ble_count=len(devices),
            devices=devices,
            boards_ok=True,
            mode="sim",
        )
        await asyncio.sleep(interval)
