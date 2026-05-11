from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.paths import ensure_dir, safe_resolve, sanitize_filename


class PathTests(unittest.TestCase):
    def test_safe_resolve_rejects_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaises(ValueError):
                safe_resolve(base, "../outside.txt")

    def test_sanitize_filename_keeps_chinese(self) -> None:
        self.assertEqual(sanitize_filename("周报:测试?.docx"), "周报_测试_.docx")

    def test_ensure_dir_creates_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b"
            ensure_dir(path)
            self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()

