from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path

from core.cache import CACHE_ROOT_ENV, CacheError, CacheStore, sanitize_for_cache


class CacheStoreTests(unittest.TestCase):
    def test_init_creates_project_cache_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "20260512_010101"
            root = Path(tmp) / "project_cache"
            store = CacheStore(run_dir, cache_root=root)
            store.init()
            self.assertEqual(store.cache_dir, root / run_dir.name)
            self.assertTrue(store.cache_dir.is_dir())
            self.assertTrue(store.comments_dir.is_dir())
            self.assertFalse((run_dir / "cache").exists())

    def test_legacy_run_cache_is_read_when_project_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project_cache"
            run_dir = Path(tmp) / "output" / "20260512_010101"
            legacy = run_dir / "cache"
            legacy.mkdir(parents=True)
            (legacy / "run_config.json").write_text("{}", encoding="utf-8")
            store = CacheStore(run_dir, cache_root=root)
            self.assertEqual(store.cache_dir, legacy.resolve())
            self.assertEqual(store.cache_location, "run_dir_legacy")

    def test_write_and_read_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp), cache_root=Path(tmp) / "project_cache")
            store.write_json("sample.json", {"ok": True})
            self.assertEqual(store.read_json("sample.json"), {"ok": True})

    def test_broken_json_raises_friendly_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp), cache_root=Path(tmp) / "project_cache")
            store.init()
            (store.cache_dir / "broken.json").write_text("{bad", encoding="utf-8")
            with self.assertRaises(CacheError):
                store.read_json("broken.json")

    def test_env_cache_root_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "20260512_010101"
            root = Path(tmp) / "env_cache"
            old = os.environ.get(CACHE_ROOT_ENV)
            try:
                os.environ[CACHE_ROOT_ENV] = str(root)
                store = CacheStore(run_dir)
                store.write_stage("run_config", {})
                self.assertTrue((root / run_dir.name / "run_config.json").exists())
            finally:
                if old is None:
                    os.environ.pop(CACHE_ROOT_ENV, None)
                else:
                    os.environ[CACHE_ROOT_ENV] = old

    def test_sensitive_fields_removed(self) -> None:
        clean = sanitize_for_cache({"cookie": "secret", "nested": {"access_token": "abc", "content": "ok"}})
        self.assertNotIn("cookie", clean)
        self.assertNotIn("access_token", clean["nested"])
        self.assertEqual(clean["nested"]["content"], "ok")


if __name__ == "__main__":
    unittest.main()

