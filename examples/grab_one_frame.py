"""Open the first camera, take one software-triggered frame, print its statistics."""
from spinnaker_ctypes import Camera

with Camera() as cam:                       # or Camera(serial="20181896")
    cam.configure(exposure_us=5000, pixel_format="Mono8")
    frame = cam.grab()
    print(frame.shape, frame.dtype, "min", frame.min(), "max", frame.max(), "mean", round(float(frame.mean()), 1))
