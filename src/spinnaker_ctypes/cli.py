"""`flir-spinnaker`: the camera from the shell - list, grab."""

from __future__ import annotations

import argparse
import sys

import numpy as np


def _save(path: str, image: np.ndarray) -> None:
    if path.endswith(".npy"):
        np.save(path, image)
    elif path.endswith(".pgm"):
        maxval = 255 if image.dtype == np.uint8 else 65535
        with open(path, "wb") as f:
            f.write(f"P5\n{image.shape[1]} {image.shape[0]}\n{maxval}\n".encode())
            f.write(image.astype(">u2" if maxval > 255 else "u1").tobytes())
    else:
        raise SystemExit("save as .npy or .pgm")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flir-spinnaker", description="Teledyne FLIR cameras through libSpinnaker_C.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="cameras the SDK can see")
    s = sub.add_parser("grab", help="take frames and save them")
    s.add_argument("output", help=".npy (any format) or .pgm (Mono8/Mono16)")
    s.add_argument("--serial")
    s.add_argument("-n", type=int, default=1, help="frames (default 1); more than one stacks along axis 0")
    s.add_argument("--exposure-us", type=float)
    s.add_argument("--gain-db", type=float)
    s.add_argument("--pixel-format", choices=["Mono8", "Mono16", "BayerRG8", "BayerRG16"])
    return p


def main(argv: list[str] | None = None) -> int:
    from .camera import Camera, SpinnakerError
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            for cam in Camera.list():
                print(f"{cam['serial']:12} {cam['model']}")
            return 0
        with Camera(serial=args.serial) as cam:
            settings = {k: v for k, v in (("exposure_us", args.exposure_us), ("gain_db", args.gain_db),
                                          ("pixel_format", args.pixel_format)) if v is not None}
            if settings:
                cam.configure(**settings)
            frames = cam.grab(n=args.n)
            _save(args.output, frames)
            print(f"{args.output}: {frames.shape} {frames.dtype}  min {frames.min()}  max {frames.max()}  "
                  f"mean {float(frames.mean()):.1f}")
    except (SpinnakerError, LookupError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
