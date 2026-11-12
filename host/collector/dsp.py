"""Motion / presence DSP: short-window variance vs empty-room baseline."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
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
        self._cal_start: float | None = None
        self._calibrating = False
        self._baseline_mean = 0.05
        self._baseline_std = 0.02
        self._threshold = 0.15
        self._calibrated = False
        self._ema = 0.0
        self._path_pos = 0.5

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
        self._cal_start = time.time()

    def poll_calibration(self) -> bool:
        """Finish calibration on wall-clock even if CSI packets stalled."""
        if not self._calibrating or self._cal_start is None:
            return False
        if time.time() - self._cal_start < self.calibrate_s:
            return False
        self._finish_calibration()
        return True

    def push(self, ts: float, amp_std: float, phase_std: float, subcarriers: list[float]) -> SenseScores:
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

        if self._calibrating:
            self._cal_values.append(self._ema)
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

        # Presence trips on sustained motion; stay quiet while calibrating
        # so empty-room baseline isn't polluted by false "someone's here" UI.
        if self._calibrating:
            presence = 0.0
            motion_n = min(motion_n, 0.2)
        else:
            presence = (
                1.0
                if motion_n >= (0.35 if self._calibrated else 0.5)
                or (self._calibrated and self._ema >= self._threshold)
                else 0.0
            )

        # Soft along-beam cue from subcarrier tilt (not true XY radar)
        if subcarriers and len(subcarriers) >= 8:
            half = len(subcarriers) // 2
            left = sum(subcarriers[:half]) / half
            right = sum(subcarriers[half:]) / max(1, len(subcarriers) - half)
            tilt = (right - left) / max(1e-3, abs(left) + abs(right))
            target = max(0.2, min(0.8, 0.5 + 0.4 * tilt))
            self._path_pos = 0.85 * self._path_pos + 0.15 * target

        return SenseScores(
            motion=motion_n,
            presence=presence,
            energy=self._ema,
            calibrated=self._calibrated,
            baseline=self._baseline_mean,
            threshold=self._threshold,
            path_pos=self._path_pos,
        )

    def _finish_calibration(self) -> None:
        # Always clear the calibrating flag so the UI can't stick forever.
        if self._cal_values:
            mean = sum(self._cal_values) / len(self._cal_values)
            var = sum((v - mean) ** 2 for v in self._cal_values) / max(1, len(self._cal_values))
            std = max(var ** 0.5, 0.015)
            self._baseline_mean = mean
            self._baseline_std = std
            # Sensitive enough for body motion on ESP-NOW RSSI variance
            self._threshold = mean + max(self.k_sigma * std, 0.08 * abs(mean), 0.25)
        self._calibrating = False
        self._calibrated = True

    def waterfall(self) -> list[list[float]]:
        return list(self._waterfall)
