from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheError, CacheStore, sanitize_for_cache


class CacheStoreTests(unittest.TestCase):
    def test_init_creates_cache_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.init()
            self.assertTrue(store.cache_dir.is_dir())
            self.assertTrue(store.comments_dir.is_dir())

    def test_write_and_read_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.write_json("sample.json", {"ok": True})
            self.assertEqual(store.read_json("sample.json"), {"ok": True})

    def test_broken_json_raises_friendly_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.init()
            (store.cache_dir / "broken.json").write_text("{bad", encoding="utf-8")
            with self.assertRaises(CacheError):
                store.read_json("broken.json")

    def test_sensitive_fields_removed(self) -> None:
        clean = sanitize_for_cache({"cookie": "secret", "nested": {"access_token": "abc", "content": "ok"}})
        self.assertNotIn("cookie", clean)
        self.assertNotIn("access_token", clean["nested"])
        self.assertEqual(clean["nested"]["content"], "ok")


if __name__ == "__main__":
    unittest.main()

