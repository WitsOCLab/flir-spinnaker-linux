"""Teledyne FLIR cameras through libSpinnaker_C and ctypes."""

from .camera import PIXEL_FORMATS, SPINNAKER_ERR_TIMEOUT, Camera, SpinnakerError
from .sim import SimCamera

__all__ = ['SimCamera', "Camera", "PIXEL_FORMATS", "SPINNAKER_ERR_TIMEOUT", "SpinnakerError"]
__version__ = "0.1.0"
