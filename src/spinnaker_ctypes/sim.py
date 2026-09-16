"""A simulated camera with the same interface as spinnaker_ctypes.Camera: frames are a smooth
gradient plus noise scaled by exposure and gain, so image code sees realistic numbers."""

from __future__ import annotations

import threading
import time

import numpy as np

from .camera import PIXEL_FORMATS

SIM_SENSOR = (1616, 1240)


class SimCamera:
    def __init__(self, serial="SIM0001", pixel_format="Mono8", exposure_us=None, gain_db=None, roi=None, **_):
        self.serial = str(serial)
        self._fmt, self._exp, self._gain = "Mono8", 5000.0, 0.0
        self._roi = [0, 0, *SIM_SENSOR]
        self._rng = np.random.default_rng(0)
        self._frame_id, self.last_info = 0, {}
        self.configure(pixel_format=pixel_format, exposure_us=exposure_us, gain_db=gain_db, roi=roi)

    def configure(self, pixel_format=None, exposure_us=None, gain_db=None, roi=None) -> dict:
        if pixel_format is not None:
            if pixel_format not in PIXEL_FORMATS:
                raise ValueError(f"pixel_format must be one of {PIXEL_FORMATS}")
            self._fmt = pixel_format
        if roi is not None:
            x, y, w, h = (int(v) for v in roi)
            w, h = max(8, min(w, SIM_SENSOR[0])), max(8, min(h, SIM_SENSOR[1]))
            x, y = min(max(x, 0), SIM_SENSOR[0] - w), min(max(y, 0), SIM_SENSOR[1] - h)
            self._roi = [x - x % 4, y - y % 2, w - w % 4, h - h % 2]
        if exposure_us is not None:
            self._exp = float(min(max(exposure_us, 10.0), 30e6))
        if gain_db is not None:
            self._gain = float(min(max(gain_db, 0.0), 48.0))
        return self.settings()

    @property
    def exposure_hint_s(self) -> float:
        return self._exp / 1e6

    def settings(self) -> dict:
        return {"model": "Simulated Blackfly S", "serial": self.serial, "firmware": "sim", "pixel_format": self._fmt,
                "exposure_us": self._exp, "gain_db": self._gain, "roi": list(self._roi), "sensor": list(SIM_SENSOR),
                "max_fps": min(53.0, 1e6 / self._exp), "link_MBps": 500.0}

    def grab(self, n: int = 1, timeout_s: float | None = None) -> np.ndarray:
        if n < 1:
            raise ValueError("n must be at least 1")
        x, y, w, h = self._roi
        yy, xx = np.mgrid[y:y + h, x:x + w]
        signal = 0.5 + 0.5 * np.sin(xx / 40.0) * np.cos(yy / 55.0)            # a stable "beam"
        scale = (self._exp / 5000.0) * 10 ** (self._gain / 20.0)
        full = 255.0 if self._fmt.endswith("8") else 65535.0
        frames = []
        for _ in range(n):
            time.sleep(self._exp / 1e6)
            img = np.clip(signal * 0.6 * full * scale + self._rng.normal(0, 0.004 * full, signal.shape), 0, full)
            frames.append(img.astype(np.uint8 if full == 255.0 else np.uint16))
        period_ns = int(max(self._exp * 1e3, 1e9 / 119))                       # the real camera's 600-row rate
        now = time.perf_counter_ns()
        self.last_info = {"mode": "burst" if n >= 32 else "trigger", "frame_id": list(range(self._frame_id, self._frame_id + n)),
                          "timestamp_ns": [now - (n - 1 - i) * period_ns for i in range(n)], "dropped": 0,
                          "fps": None if n == 1 else 1e9 / period_ns}
        self._frame_id += n
        return frames[0] if n == 1 else np.stack(frames)

    def close(self) -> None:
        pass
