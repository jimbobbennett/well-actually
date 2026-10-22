import unittest

import well_actually_processing


class PackageTests(unittest.TestCase):
    def test_package_has_description(self):
        self.assertIn("Arduino UNO Q", well_actually_processing.__doc__)


if __name__ == "__main__":
    unittest.main()
