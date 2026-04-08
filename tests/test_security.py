import unittest
import os
from pathlib import Path
from utils.custom_indices import get_safe_path, INDEX_PATH

class TestSecurity(unittest.TestCase):
    def test_get_safe_path_valid(self):
        # Assumes iAc.csv exists in indices/
        path = get_safe_path("iAc")
        self.assertIsNotNone(path)
        self.assertEqual(path, (INDEX_PATH / "iAc.csv").resolve())

    def test_get_safe_path_traversal(self):
        # Try to go up from indices
        path = get_safe_path("../README.md")
        self.assertIsNone(path)

    def test_get_safe_path_absolute(self):
        # Try absolute path
        path = get_safe_path("/etc/passwd")
        self.assertIsNone(path)

if __name__ == "__main__":
    unittest.main()
