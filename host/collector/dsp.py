"""Motion / presence DSP: short-window variance vs empty-room baseline."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time


@dataclass
class SenseScores:
    motion: float
    presence: float
    energy: float
    calibrated: bool
    baseline: float
    threshold: float
    path_pos: float  # 0=near TX .. 1=near RX (soft estimate along the beam only)
    near_side: str  # tx | rx | mid | none


class CsiDsp:
    def __init__(
        self,
        window_s: float = 1.5,
        calibrate_s: float = 20.0,
        k_sigma: float = 1.6,
    ) -> None:
        self.window_s = window_s
        self.calibrate_s = calibrate_s
        self.k_sigma = k_sigma
        self._samples: deque[tuple[float, float]] = deque(maxlen=300)
        self._waterfall: deque[list[float]] = deque(maxlen=90)
        self._cal_values: list[float] = []
        self._cal_amp_mean: list[float] = []
        self._cal_start: float | None = None
        self._calibrating = False
        self._baseline_mean = 0.05
        self._baseline_std = 0.02
        self._baseline_amp_mean = 50.0  # |RSSI| while empty
        self._threshold = 0.15
        self._calibrated = False
        self._ema = 0.0
        self._path_pos = 0.5
        self._path_raw = 0.5
        self._near_side = "none"
        self._side_candidate = "none"
        self._side_since = 0.0
        self._presence = 0.0
        self._presence_hold_until = 0.0

    @property
    def calibrated(self) -> bool:
        return self._calibrated

    @property
    def calibrating(self) -> bool:
        return self._calibrating

    def start_calibration(self, duration_s: float | None = None) -> None:
        if duration_s is not None:
            self.calibrate_s = duration_s
        self._calibrating = True
        self._calibrated = False
        self._cal_values.clear()
        self._cal_amp_mean.clear()
        self._samples.clear()
        self._ema = 0.0
        self._cal_start = time.time()
        self._near_side = "none"
        self._side_candidate = "none"
        self._path_raw = 0.5
        self._path_pos = 0.5
        self._presence = 0.0
        self._presence_hold_until = 0.0

    def poll_calibration(self) -> bool:
        """Finish calibration on wall-clock even if CSI packets stalled."""
        if not self._calibrating or self._cal_start is None:
            return False
        if time.time() - self._cal_start < self.calibrate_s:
            return False
        self._finish_calibration()
        return True

    def push(
        self,
        ts: float,
        amp_std: float,
        phase_std: float,
        subcarriers: list[float],
        amp_mean: float = 0.0,
        rssi: float = 0.0,
    ) -> SenseScores:
        # Primary signal: reported link variance (ESP-NOW RSSI std on RX)
        energy = float(amp_std) + 0.25 * float(phase_std)
        if subcarriers:
            mean = sum(subcarriers) / len(subcarriers)
            var = sum((x - mean) ** 2 for x in subcarriers) / max(1, len(subcarriers))
            energy = 0.75 * energy + 0.25 * (var ** 0.5)
            self._waterfall.append([float(x) for x in subcarriers[:32]])

        self._samples.append((ts, energy))
        cutoff = ts - self.window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        vals = [v for _, v in self._samples]
        # Also use short-term std of energy (catches bursts even if mean drifts)
        mean = sum(vals) / max(1, len(vals))
        var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals))
        burst = var ** 0.5
        score = 0.55 * mean + 0.45 * burst
        # Heavier smoothing — ESP-NOW RSSI variance is bursty and was
        # flickering presence on/off every few hundred ms.
        self._ema = 0.82 * self._ema + 0.18 * score

        amp_mag = float(amp_mean) if amp_mean > 1.0 else abs(float(rssi) or 0.0)
        if self._calibrating:
            self._cal_values.append(self._ema)
            if amp_mag > 1.0:
                self._cal_amp_mean.append(amp_mag)
            assert self._cal_start is not None
            if time.time() - self._cal_start >= self.calibrate_s:
                self._finish_calibration()

        if self._calibrated:
            excess = max(0.0, self._ema - self._baseline_mean)
            denom = max(self._threshold - self._baseline_mean, 0.05)
            motion_n = min(1.0, excess / denom)
        else:
            # Before empty-room calibrate finishes, only relative burst counts.
            # Absolute excess vs the tiny default baseline always pegged at 1.0.
            quiet = mean if vals else max(self._ema, 0.05)
            motion_n = min(1.0, burst / max(0.06, 0.28 * quiet))

        # Presence: trip on motion, hold while link still faded (sitting),
        # and keep a short timer so WS/UI don't flicker every RSSI burst.
        if self._calibrating:
            presence = 0.0
            motion_n = min(motion_n, 0.2)
            self._presence = 0.0
            self._presence_hold_until = 0.0
        else:
            trip = motion_n >= (0.35 if self._calibrated else 0.5) or (
                self._calibrated and self._ema >= self._threshold
            )
            # Strong fade alone can keep presence briefly after motion (sitting),
            # but must not latch forever on slow RSSI drift — require recent trip
            # or a clear fade AND a short hold window.
            faded = False
            if self._calibrated and amp_mag > 1.0 and self._presence_hold_until > 0:
                faded = amp_mag >= (self._baseline_amp_mean + 4.0)
            if trip:
                self._presence_hold_until = ts + 2.8
            elif faded and ts <= self._presence_hold_until + 1.5:
                # extend slightly while still deeply faded after a trip
                self._presence_hold_until = max(self._presence_hold_until, ts + 0.6)
            presence = 1.0 if (trip or ts <= self._presence_hold_until) else 0.0
            self._presence = presence

        self._update_path(ts, motion_n, presence, amp_mag)

        return SenseScores(
            motion=motion_n,
            presence=presence,
            energy=self._ema,
            calibrated=self._calibrated,
            baseline=self._baseline_mean,
            threshold=self._threshold,
            path_pos=self._path_pos,
            near_side=self._near_side,
        )

    def _update_path(self, ts: float, motion_n: float, presence: float, amp_mag: float) -> None:
        """Along-beam estimate from link fade — not fake subcarrier tilt.

        Firmware `sc[]` is RSSI history + sine, so left/right tilt was random.
        Deeper |RSSI| vs empty baseline usually means body near the RX antenna;
        milder fade → mid. Hold while sitting still so the figure doesn't thrash.
        """
        if presence < 0.5 and motion_n < 0.22:
            self._set_side(ts, "none", dwell_s=0.45)
            if self._near_side == "none":
                # Ease toward mid when empty so the next walk starts clean
                self._path_raw = 0.96 * self._path_raw + 0.04 * 0.5
                self._path_pos = self._path_raw
            return

        # Fade: higher amp_mag (= weaker RSSI) than empty room → bias toward RX
        base = max(self._baseline_amp_mean, 20.0)
        fade = (amp_mag - base) / max(4.0, 0.12 * base) if amp_mag > 1.0 else 0.0
        fade = max(-0.8, min(2.2, fade))
        # Map fade → path: strong fade ≈ near RX, weak/negative ≈ TX side of mid
        target = 0.5 + 0.38 * math.tanh(0.9 * fade)
        target = max(0.12, min(0.88, target))

        if motion_n < 0.28 and presence > 0.5:
            # Sitting still: freeze continuous estimate, keep settled zone
            self._set_side(ts, self._side_from_path(self._path_raw), dwell_s=0.9)
            self._path_pos = self._snap_path(self._near_side)
            return

        # Deadband + heavy EMA while moving — ignore tiny RSSI chatter
        if abs(target - self._path_raw) >= 0.07 or motion_n >= 0.5:
            alpha = 0.08 if motion_n < 0.45 else 0.14
            self._path_raw = (1.0 - alpha) * self._path_raw + alpha * target

        raw_side = self._side_from_path(self._path_raw)
        self._set_side(ts, raw_side, dwell_s=0.75)
        # Display path snaps to zone centers so the model parks, not jitters
        want = self._snap_path(self._near_side if self._near_side != "none" else raw_side)
        self._path_pos = 0.88 * self._path_pos + 0.12 * want

    @staticmethod
    def _side_from_path(path: float) -> str:
        # Wide mid band; enter TX/RX only near the ends
        if path <= 0.30:
            return "tx"
        if path >= 0.70:
            return "rx"
        return "mid"

    @staticmethod
    def _snap_path(side: str) -> float:
        return {"tx": 0.18, "rx": 0.82, "mid": 0.50, "none": 0.50}.get(side, 0.50)

    def _set_side(self, ts: float, candidate: str, *, dwell_s: float) -> None:
        """Hysteresis: require sustained agreement before flipping TX/mid/RX."""
        if candidate == self._near_side:
            self._side_candidate = candidate
            self._side_since = ts
            return
        if candidate != self._side_candidate:
            self._side_candidate = candidate
            self._side_since = ts
            return
        if (ts - self._side_since) >= dwell_s:
            self._near_side = candidate

    def _finish_calibration(self) -> None:
        # Always clear the calibrating flag so the UI can't stick forever.
        self._calibrating = False
        if len(self._cal_values) < 8:
            # No / too few packets — do NOT pretend we have an empty-room baseline.
            self._calibrated = False
            self._cal_values.clear()
            self._cal_amp_mean.clear()
            return
        mean = sum(self._cal_values) / len(self._cal_values)
        var = sum((v - mean) ** 2 for v in self._cal_values) / max(1, len(self._cal_values))
        std = max(var ** 0.5, 0.015)
        self._baseline_mean = mean
        self._baseline_std = std
        # Sensitive enough for body motion on ESP-NOW RSSI variance
        self._threshold = mean + max(self.k_sigma * std, 0.08 * abs(mean), 0.25)
        if self._cal_amp_mean:
            self._baseline_amp_mean = sum(self._cal_amp_mean) / len(self._cal_amp_mean)
        self._cal_amp_mean.clear()
        self._cal_values.clear()
        self._calibrated = True
        self._path_raw = 0.5
        self._path_pos = 0.5
        self._near_side = "none"
        self._side_candidate = "none"
        self._presence = 0.0
        self._presence_hold_until = 0.0
        self._ema = mean  # start clean — don't carry pre-cal motion into live score

    def waterfall(self) -> list[list[float]]:
        return list(self._waterfall)
