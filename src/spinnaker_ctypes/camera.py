"""FLIR/Teledyne Blackfly S via Teledyne's own Spinnaker C library (libSpinnaker_C), called with ctypes.

Why not PySpin or a GenTL consumer: PySpin has no wheel for this Python, and Harvesters + the Spinnaker
GenTL producer hangs forever in device close (observed on the OCLab rig, September 2026). The C API is what SpinView
and the SDK examples use; it opens and closes cleanly.

The camera streams in software-trigger mode, so every grab is exposed *after* it is requested:
a frame can never predate the pattern that was just displayed. Long sequences (32 frames or more) free-run at
the camera's full frame rate instead of triggering each frame, and they too start only after the request.
"""

from __future__ import annotations

import ctypes as C
import os
import time

import numpy as np

PIXEL_FORMATS = ("Mono8", "Mono16", "BayerRG8", "BayerRG16")
SPINNAKER_ERR_TIMEOUT = -1011


class SpinnakerError(RuntimeError):
    pass


class _Lib:
    """libSpinnaker_C with error checking: every call returns a spinError, 0 on success."""

    def __init__(self):
        last = None
        # SPINNAKER_LIB names the library file for an SDK installed somewhere other than /opt/spinnaker.
        candidates = [os.environ["SPINNAKER_LIB"]] if os.environ.get("SPINNAKER_LIB") else []
        for name in candidates + ["libSpinnaker_C.so.4", "/opt/spinnaker/lib/libSpinnaker_C.so.4",
                                  "libSpinnaker_C.so.3", "/opt/spinnaker/lib/libSpinnaker_C.so.3"]:
            try:
                self.lib = C.CDLL(name)
                break
            except OSError as e:
                last = e
        else:
            raise SpinnakerError("cannot load libSpinnaker_C (is the Spinnaker SDK installed? set SPINNAKER_LIB to the .so "
                                 f"if it is elsewhere): {last}") from None

    def __getattr__(self, name: str):
        fn = getattr(self.lib, name)
        fn.restype = C.c_int

        def call(*args, ok=(0,)):
            err = fn(*args)
            if err not in ok:
                buf, n = C.create_string_buffer(512), C.c_size_t(512)
                self.lib.spinErrorGetLastMessage(buf, C.byref(n))
                raise SpinnakerError(f"{name}: {buf.value.decode(errors='replace')} (error {err})")
            return err

        return call


class Camera:
    def __init__(self, serial: str | int | None = None, pixel_format: str = "Mono8",
                 exposure_us: float | None = None, gain_db: float | None = None, roi: list[int] | None = None):
        self._s = _Lib()
        s = self._s
        self._system, self._list, self._cam = C.c_void_p(), C.c_void_p(), C.c_void_p()
        self._nm, self._tl_nm, self._stream_nm = C.c_void_p(), C.c_void_p(), C.c_void_p()
        self._streaming = False
        self._exposure_us = 0.0
        self.last_info: dict = {}
        s.spinSystemGetInstance(C.byref(self._system))
        try:
            s.spinCameraListCreateEmpty(C.byref(self._list))
            s.spinSystemGetCameras(self._system, self._list)
            count = C.c_size_t()
            s.spinCameraListGetSize(self._list, C.byref(count))
            if count.value == 0:
                raise LookupError("no Spinnaker cameras found (check USB, the flirimaging group and udev rules)")
            if serial is None:
                s.spinCameraListGet(self._list, 0, C.byref(self._cam))
            else:
                try:
                    s.spinCameraListGetBySerial(self._list, str(serial).encode(), C.byref(self._cam))
                except SpinnakerError:
                    raise LookupError(f"camera with serial {serial} not found ({count.value} camera(s) connected)") from None
            s.spinCameraInit(self._cam)
            s.spinCameraGetNodeMap(self._cam, C.byref(self._nm))
            s.spinCameraGetTLDeviceNodeMap(self._cam, C.byref(self._tl_nm))
            s.spinCameraGetTLStreamNodeMap(self._cam, C.byref(self._stream_nm))

            self._set("TriggerMode", "Off")  # trigger source/selector only change while triggering is off
            for name, value in (("AcquisitionMode", "Continuous"), ("ExposureAuto", "Off"), ("GainAuto", "Off"),
                                ("GammaEnable", False), ("TriggerSelector", "FrameStart"),
                                ("TriggerSource", "Software"), ("AcquisitionStatusSelector", "FrameTriggerWait")):
                self._set(name, value, optional=True)
            self._set("TriggerMode", "On")
            self._set("StreamBufferHandlingMode", "NewestOnly", nodemap=self._stream_nm, optional=True)
            self.configure(pixel_format=pixel_format, exposure_us=exposure_us, gain_db=gain_db, roi=roi)
        except Exception:
            self.close()
            raise

    def configure(self, pixel_format: str | None = None, exposure_us: float | None = None,
                  gain_db: float | None = None, roi: list[int] | None = None) -> dict:
        """Change settings; `roi` is [x, y, width, height] in sensor pixels (snapped to valid steps)."""
        if pixel_format is not None or roi is not None:
            self._stream(False)
        try:
            if pixel_format is not None:
                if pixel_format not in PIXEL_FORMATS:
                    raise ValueError(f"pixel_format must be one of {PIXEL_FORMATS}")
                self._set("PixelFormat", pixel_format)
            if roi is not None:
                x, y, w, h = (int(v) for v in roi)
                self._set("OffsetX", 0)
                self._set("OffsetY", 0)
                self._set("Width", self._snap("Width", w))
                self._set("Height", self._snap("Height", h))
                self._set("OffsetX", self._snap("OffsetX", x))
                self._set("OffsetY", self._snap("OffsetY", y))
            if exposure_us is not None:
                self._set("ExposureTime", float(exposure_us))
            if gain_db is not None:
                self._set("Gain", float(gain_db))
        finally:
            self._stream(True)
        settings = self.settings()
        self._exposure_us = settings["exposure_us"] or 0.0
        return settings

    @property
    def exposure_hint_s(self) -> float:
        """The last configured exposure in seconds, without camera I/O (for timeouts and deadlines)."""
        return self._exposure_us / 1e6

    def settings(self) -> dict:
        g = self._get
        return {
            "model": g("DeviceModelName"), "serial": g("DeviceSerialNumber"), "firmware": g("DeviceFirmwareVersion"),
            "pixel_format": g("PixelFormat"), "exposure_us": g("ExposureTime", float), "gain_db": g("Gain", float),
            "roi": [g(n, int) for n in ("OffsetX", "OffsetY", "Width", "Height")],
            "sensor": [g("SensorWidth", int), g("SensorHeight", int)],
            "max_fps": g("AcquisitionResultingFrameRate", float),
            "link_MBps": (g("DeviceLinkSpeed", int) or 0) / 1e6,
        }

    BURST_MIN_FRAMES = 32   # measured break-even: triggered 9.8 ms/frame vs free-running 8.5 ms/frame + ~40 ms mode switch

    def grab(self, n: int = 1, timeout_s: float | None = None) -> np.ndarray:
        """(height, width) for n == 1, else (n, height, width). Every frame is exposed after the call.

        Short sequences are software-triggered frame by frame. From BURST_MIN_FRAMES on, the camera free-runs
        at its full frame rate with frames queued in order (no trigger round trip per frame, none silently
        replaced by a newer one). Either way `last_info` holds the camera's frame_id and timestamp_ns for every
        frame returned, plus dropped (gaps in the frame IDs) and the measured fps."""
        if n < 1:
            raise ValueError("n must be at least 1")
        timeout_ms = int(1e3 * (timeout_s if timeout_s is not None else self._exposure_us / 1e6 + 2.0))
        if n >= self.BURST_MIN_FRAMES:
            return self._burst(n, timeout_ms)
        frames, ids, stamps = None, [], []
        for i in range(n):
            frame, frame_id, stamp = self._grab_one(timeout_ms)
            if frames is None:
                frames = np.empty((n, *frame.shape), frame.dtype)
            frames[i] = frame
            ids.append(frame_id)
            stamps.append(stamp)
        self.last_info = self._info("trigger", ids, stamps)
        return frames[0] if n == 1 else frames

    def _burst(self, n: int, timeout_ms: int) -> np.ndarray:
        """Free-run for n frames. Trigger mode is switched while the stream keeps running: restarting the stream
        costs ~0.3 s of buffer allocation each way. Cameras that refuse the switch get the stop/start path."""
        sn = self._stream_nm
        self._drain(1)                                              # nothing stale from an earlier grab
        self._set("StreamBufferHandlingMode", "OldestFirst", nodemap=sn, optional=True)
        restart = False
        try:
            self._set("TriggerMode", "Off")
        except SpinnakerError:
            restart = True
            self._stream(False)
            self._set("TriggerMode", "Off")
            self._stream(True)
        frames, ids, stamps = None, [], []
        try:
            for i in range(n):
                frame, frame_id, stamp = self._grab_one(timeout_ms, trigger=False)
                if frames is None:
                    frames = np.empty((n, *frame.shape), frame.dtype)
                frames[i] = frame
                ids.append(frame_id)
                stamps.append(stamp)
        finally:
            if restart:
                self._stream(False)
            self._set("TriggerMode", "On", optional=True)
            self._set("StreamBufferHandlingMode", "NewestOnly", nodemap=sn, optional=True)
            if restart:
                self._stream(True)
            else:
                self._wait_trigger_ready()                          # the frame being read out when triggering resumed ...
                self._drain(20)                                     # ... must not be mistaken for the next triggered frame
        self.last_info = self._info("burst", ids, stamps)
        return frames

    @staticmethod
    def list() -> list[dict]:
        """Every camera the SDK can see, without opening any: [{"serial", "model"}]."""
        s = _Lib()
        system, cameras = C.c_void_p(), C.c_void_p()
        s.spinSystemGetInstance(C.byref(system))
        found = []
        try:
            s.spinCameraListCreateEmpty(C.byref(cameras))
            s.spinSystemGetCameras(system, cameras)
            count = C.c_size_t()
            s.spinCameraListGetSize(cameras, C.byref(count))
            for i in range(count.value):
                cam, nodemap = C.c_void_p(), C.c_void_p()
                s.spinCameraListGet(cameras, i, C.byref(cam))
                try:
                    s.spinCameraGetTLDeviceNodeMap(cam, C.byref(nodemap))   # readable without CameraInit
                    entry = {}
                    for key, node in (("serial", "DeviceSerialNumber"), ("model", "DeviceModelName")):
                        h = C.c_void_p()
                        s.spinNodeMapGetNode(nodemap, node.encode(), C.byref(h))
                        buf, n = C.create_string_buffer(256), C.c_size_t(256)
                        s.spinNodeToString(h, buf, C.byref(n))
                        entry[key] = buf.value.decode(errors="replace")
                    found.append(entry)
                finally:
                    s.spinCameraRelease(cam)
        finally:
            if cameras:
                s.spinCameraListClear(cameras)
                s.spinCameraListDestroy(cameras)
            s.spinSystemReleaseInstance(system)
        return found

    @staticmethod
    def _info(mode: str, ids: list[int], stamps: list[int]) -> dict:
        span_s = (stamps[-1] - stamps[0]) / 1e9
        return {"mode": mode, "frame_id": ids, "timestamp_ns": stamps, "dropped": int(ids[-1] - ids[0] + 1 - len(ids)),
                "fps": (len(ids) - 1) / span_s if len(ids) > 1 and span_s > 0 else None}

    def __enter__(self) -> "Camera":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        s = self._s
        if self._cam:
            self._stream(False)
            if self._nm:
                self._set("TriggerMode", "Off", optional=True)
            s.spinCameraDeInit(self._cam)
            s.spinCameraRelease(self._cam)
            self._cam = C.c_void_p()
        if self._list:
            s.spinCameraListClear(self._list)
            s.spinCameraListDestroy(self._list)
            self._list = C.c_void_p()
        if self._system:
            s.spinSystemReleaseInstance(self._system)
            self._system = C.c_void_p()

    # --- internals ------------------------------------------------------------------------------

    def _grab_one(self, timeout_ms: int, trigger: bool = True) -> tuple[np.ndarray, int, int]:
        """One frame plus the camera's frame ID and timestamp (ns). trigger=False reads the next free-running frame."""
        s = self._s
        if trigger:
            self._wait_trigger_ready()
            s.spinCommandExecute(self._node("TriggerSoftware"))
        img = C.c_void_p()
        s.spinCameraGetNextImageEx(self._cam, timeout_ms, C.byref(img))
        try:
            incomplete = C.c_uint8()
            s.spinImageIsIncomplete(img, C.byref(incomplete))
            if incomplete.value:
                raise SpinnakerError("incomplete image (USB bandwidth or usbfs_memory_mb too low?)")
            w, h, stride, bpp, size = (C.c_size_t() for _ in range(5))
            s.spinImageGetWidth(img, C.byref(w))
            s.spinImageGetHeight(img, C.byref(h))
            s.spinImageGetStride(img, C.byref(stride))
            s.spinImageGetBitsPerPixel(img, C.byref(bpp))
            s.spinImageGetBufferSize(img, C.byref(size))
            data = C.c_void_p()
            s.spinImageGetData(img, C.byref(data))
            raw = np.frombuffer(C.string_at(data, size.value), dtype=np.uint8)  # copies out of the SDK buffer
            dtype = np.uint16 if bpp.value == 16 else np.uint8
            rows = raw[: stride.value * h.value].reshape(h.value, stride.value)
            frame_id, stamp = C.c_uint64(), C.c_uint64()
            s.spinImageGetFrameID(img, C.byref(frame_id))
            s.spinImageGetTimeStamp(img, C.byref(stamp))
            return rows[:, : w.value * np.dtype(dtype).itemsize].copy().view(dtype), int(frame_id.value), int(stamp.value)
        finally:
            s.spinImageRelease(img)

    def _drain(self, wait_ms: int) -> int:
        """Discard frames already queued (or arriving within wait_ms). Returns how many."""
        n = 0
        while True:
            img = C.c_void_p()
            err = self._s.spinCameraGetNextImageEx(self._cam, wait_ms, C.byref(img), ok=(0, SPINNAKER_ERR_TIMEOUT))
            if err != 0 or not img:
                return n
            self._s.spinImageRelease(img)
            n += 1

    def _wait_trigger_ready(self, timeout_s: float = 1.0) -> None:
        # A trigger sent while the sensor is still reading out is ignored, and the grab would time out.
        end = time.perf_counter() + timeout_s
        while time.perf_counter() < end:
            if self._get("AcquisitionStatus", bool) is not False:
                return
            time.sleep(0.0005)

    def _stream(self, on: bool) -> None:
        if on and not self._streaming:
            self._s.spinCameraBeginAcquisition(self._cam)
        elif not on and self._streaming:
            self._s.spinCameraEndAcquisition(self._cam)
        self._streaming = on

    def _node(self, name: str, nodemap=None) -> C.c_void_p:
        h = C.c_void_p()
        self._s.spinNodeMapGetNode(nodemap or self._nm, name.encode(), C.byref(h))
        if not h:
            raise SpinnakerError(f"node {name!r} does not exist on this camera")
        return h

    def _get(self, name: str, kind=str):
        """Read any node as text (the SDK formats it), converted to `kind`; None when missing/unreadable."""
        try:
            h = self._node(name)
            readable = C.c_uint8()
            self._s.spinNodeIsReadable(h, C.byref(readable))
            if not readable.value:
                return None
            if kind is bool:
                v = C.c_uint8()
                self._s.spinBooleanGetValue(h, C.byref(v))
                return bool(v.value)
            buf, n = C.create_string_buffer(256), C.c_size_t(256)
            self._s.spinNodeToString(h, buf, C.byref(n))
            return kind(buf.value.decode())
        except (SpinnakerError, ValueError):
            return None

    def _set(self, name: str, value, optional: bool = False, nodemap=None) -> None:
        """Write a node; the Python type picks the GenICam type (str=enum entry, bool, int, float)."""
        s = self._s
        try:
            h = self._node(name, nodemap)
            if isinstance(value, bool):
                s.spinBooleanSetValue(h, C.c_uint8(value))
            elif isinstance(value, int):
                s.spinIntegerSetValue(h, C.c_int64(value))
            elif isinstance(value, float):
                s.spinFloatSetValue(h, C.c_double(value))
            else:
                entry, ivalue = C.c_void_p(), C.c_int64()
                s.spinEnumerationGetEntryByName(h, str(value).encode(), C.byref(entry))
                if not entry:
                    raise SpinnakerError(f"{name} has no entry {value!r}")
                s.spinEnumerationEntryGetIntValue(entry, C.byref(ivalue))
                s.spinEnumerationSetIntValue(h, ivalue)
        except SpinnakerError as e:
            if not optional:
                raise SpinnakerError(f"cannot set {name} = {value!r}: {e}") from None

    def _snap(self, name: str, value: int) -> int:
        h = self._node(name)
        lo, hi, inc = C.c_int64(), C.c_int64(), C.c_int64()
        self._s.spinIntegerGetMin(h, C.byref(lo))
        self._s.spinIntegerGetMax(h, C.byref(hi))
        self._s.spinIntegerGetInc(h, C.byref(inc))
        step = max(inc.value, 1)
        value = min(max(int(value), lo.value), hi.value)
        return value - (value - lo.value) % step
