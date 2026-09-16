# flir-spinnaker-linux

Teledyne FLIR (Point Grey) cameras from Python, through the Spinnaker SDK's C library
(`libSpinnaker_C`) and `ctypes`. No PySpin wheel, no compiler, no Python-version lock.

## The problem it solves

FLIR's official Python binding, PySpin, ships as a wheel built for one Python version per SDK
release. Upgrade your distribution's Python and the camera stops importing until FLIR ship a new
wheel, which on Linux arrives a year or more later. Third-party bindings (rotpy) compile against
the SDK and inherit the same coupling. The C API underneath has been stable across SDK 3 and 4;
Micro-Manager moved its adapter onto it for exactly that reason.

This package loads `libSpinnaker_C.so` at run time and talks to it with `ctypes`. It works with
whatever Python the machine has, and with any SDK from 3.x on.

```
pip install flir-spinnaker-linux
```
```python
from spinnaker_ctypes import Camera
```

## What it does

- enumerate cameras, open by serial number
- GenICam nodes: exposure, gain, pixel format (Mono8/16, Bayer), ROI with the sensor's alignment rules
- software trigger for show-then-grab work, free-running bursts for throughput
- every frame carries the camera's own frame id and timestamp, so dropped frames are detected, not guessed
- stream buffer handling (`OldestFirst`/`NewestOnly`) chosen per call
- a simulator with the same interface, so software using it can be tested without a camera

Measured on a Blackfly S BFS-U3-19S4C over USB 3: 119 frames/s at full resolution, 0 dropped in
a 300-frame burst, with frame ids proving it.

## Requirements

The Spinnaker SDK (Linux `.deb` from Teledyne; the 22.04 build runs on 24.04) with
`libSpinnaker_C.so` on the loader path or under `/opt/spinnaker/lib`. Group access to the camera
comes from the SDK's own udev rules. Set `usbcore.usbfs_memory_mb=1000` for long bursts.

## Status

Extracted from a working laboratory rig (Wits OCLab). The API is the rig's; it will settle over
the first releases. Contributions from other labs with other camera models are welcome.
