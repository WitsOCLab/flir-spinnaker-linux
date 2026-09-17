"""The command line, without a camera: listing and saving."""
import io
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from spinnaker_ctypes import cli


class CliTest(unittest.TestCase):
    def test_list_prints_serial_and_model(self):
        with mock.patch("spinnaker_ctypes.camera.Camera.list", return_value=[{"serial": "20181896", "model": "Blackfly S BFS-U3-19S4C"}]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(cli.main(["list"]), 0)
        self.assertIn("20181896", out.getvalue())
        self.assertIn("Blackfly", out.getvalue())

    def test_pgm_round_trip(self):
        image = (np.arange(12, dtype=np.uint16).reshape(3, 4) * 5000)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f.pgm")
            cli._save(path, image)
            with open(path, "rb") as f:
                header = f.readline() + f.readline() + f.readline()
                data = np.frombuffer(f.read(), dtype=">u2").reshape(3, 4)
        self.assertEqual(header, b"P5\n4 3\n65535\n")
        self.assertTrue(np.array_equal(data, image))

    def test_missing_sdk_is_an_error_not_a_traceback(self):
        from spinnaker_ctypes.camera import SpinnakerError
        with mock.patch("spinnaker_ctypes.camera.Camera.list", side_effect=SpinnakerError("cannot load libSpinnaker_C")), \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(cli.main(["list"]), 1)
        self.assertIn("libSpinnaker_C", err.getvalue())


if __name__ == "__main__":
    unittest.main()
