# flir-spinnaker-linux

Teledyne FLIR (Point Grey) cameras from Python on Linux, through the Spinnaker SDK's C library and ctypes. Works with whatever Python you have, and with Spinnaker 3 or 4. There is no PySpin wheel to match to your Python version.

## Creator

**Warwick Brown**  
_School of Electrical and Information Engineering, University of the Witwatersrand, Johannesburg, South Africa_  
Email: [warwickb10@gmail.com](mailto:warwickb10@gmail.com)  
Homepage: [https://www.wits.ac.za/oclab](https://www.wits.ac.za/oclab)

If you use this in published work, please cite the repository (see CITATION.cff) or acknowledge the Wits OC Lab. Pull requests are welcome.

## Install

1. Install the Spinnaker SDK from Teledyne (the Ubuntu .deb; the 22.04 build also runs on 24.04). Its installer adds the udev rule and the `flirimaging` group.
2. `echo 1000 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb` for long bursts (the SDK's install script offers to make this permanent).
3. `pip install flir-spinnaker-linux` (before the PyPI release: `pip install git+https://github.com/WitsOCLab/flir-spinnaker-linux`), then `flir-spinnaker list`.

Tested with a Blackfly S BFS-U3-19S4C over USB 3 on Pop!_OS 24.04: 119 frames/s at full resolution, no dropped frames in bursts of 300, checked by the camera's frame counter.

## From Python

```python
from spinnaker_ctypes import Camera

with Camera() as cam:                                  # or Camera(serial="20181896")
    cam.configure(exposure_us=5000, gain_db=0, pixel_format="Mono16")
    frame = cam.grab()                                 # one software-triggered frame, numpy array
    burst = cam.grab(n=300)                            # free-running at full rate, (300, h, w)
    print(cam.last_info)                               # frame ids, timestamps, dropped count
```

`SimCamera` has the same interface and no hardware, for tests.

## From MATLAB

```matlab
pyenv(Version="/usr/bin/python3");
cam = py.spinnaker_ctypes.Camera();
cam.configure(pyargs('exposure_us', 5000, 'pixel_format', 'Mono8'));
img = uint8(cam.grab());                               % numpy to MATLAB, R2022a and later
imagesc(img); axis image;
cam.close();
```

`matlab/grab_frame.m` is a working script. Tested with R2026a. The rig this came from also has a MATLAB class that talks to a camera daemon over TCP, for when several programs need the camera; ask if you need that.

## Command line

| Command | Does |
|---|---|
| `flir-spinnaker list` | cameras the SDK can see |
| `flir-spinnaker grab frame.pgm --exposure-us 3000` | one frame to a file |
| `flir-spinnaker grab burst.npy -n 100` | a burst, stacked along the first axis |

## Troubleshooting

* `libSpinnaker_C.so not found`: the SDK is not installed, or is under a path other than `/opt/spinnaker/lib`. Set `SPINNAKER_LIB` to the file.
* Frames drop in long bursts: `usbfs_memory_mb` is at its default 16; see Install.
* Nothing found by `list` but `lsusb` shows `1e10:`: you are not in the `flirimaging` group, or another program (SpinView) holds the camera.

## Disclaimer

Not affiliated with or endorsed by Teledyne FLIR. "FLIR", "Spinnaker" and "Blackfly" are trademarks of Teledyne FLIR, used here only to say which hardware and SDK this works with. The Spinnaker SDK is Teledyne's software under Teledyne's licence and none of it is included: install it from Teledyne and accept their terms. This package only calls the SDK's public C API, the one its own headers and examples document.

## License

MIT. Copyright (c) 2026 Wits OC Lab. See LICENSE.

## Acknowledgements

Written for the OC Lab optical computing rig after PySpin stopped importing on a Python upgrade.
