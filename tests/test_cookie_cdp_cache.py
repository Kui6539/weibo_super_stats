from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cookie_helper import clear_cdp_debug_cache


class CookieCdpCacheTests(unittest.TestCase):
    def test_clear_cdp_debug_cache_removes_fixed_profile_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / ".edge_cdp_profile"
            chrome = root / ".chrome_cdp_profile"
            edge.mkdir()
            chrome.mkdir()
            (edge / "state.txt").write_text("edge", encoding="utf-8")
            (chrome / "state.txt").write_text("chrome", encoding="utf-8")

            result = clear_cdp_debug_cache(root, close_browsers=False)

            self.assertEqual(result["errors"], [])
            self.assertEqual(len(result["deleted"]), 2)
            self.assertFalse(edge.exists())
            self.assertFalse(chrome.exists())

    def test_clear_cdp_debug_cache_treats_missing_dirs_as_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = clear_cdp_debug_cache(Path(tmp), close_browsers=False)

            self.assertEqual(result["errors"], [])
            self.assertEqual(result["deleted"], [])
            self.assertEqual(len(result["missing"]), 2)


if __name__ == "__main__":
    unittest.main()
