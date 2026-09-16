"""What can be checked without a camera attached: the package imports, the constants are what
users rely on, and errors are the package's own type."""
import unittest

import spinnaker_ctypes


class ImportTest(unittest.TestCase):
    def test_public_surface(self):
        self.assertEqual(spinnaker_ctypes.PIXEL_FORMATS, ("Mono8", "Mono16", "BayerRG8", "BayerRG16"))
        self.assertTrue(issubclass(spinnaker_ctypes.SpinnakerError, RuntimeError))
        self.assertEqual(spinnaker_ctypes.SPINNAKER_ERR_TIMEOUT, -1011)
        self.assertTrue(callable(spinnaker_ctypes.Camera))

    def test_version_is_the_package_version(self):
        self.assertRegex(spinnaker_ctypes.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
