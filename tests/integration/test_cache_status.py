from __future__ import annotations

import json
import unittest

from core.cache import CacheStore
from tests.helpers import assert_no_sensitive_fields, load_fixture, make_temp_run_dir, write_cache_fixture


class CacheStatusIntegrationTests(unittest.TestCase):
    def test_complete_cache_can_reexport(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            status = CacheStore(run_dir).get_cache_status()
            self.assertTrue(status["has_cache"])
            self.assertTrue(status["can_reexport"])
            self.assertEqual(status["missing"], [])
            self.assertGreaterEqual(status["comments_count"], 3)
            assert_no_sensitive_fields(self, status)

    def test_missing_selected_posts_disables_reexport(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            (run_dir / "cache" / "selected_posts.json").unlink()
            status = CacheStore(run_dir).get_cache_status()
            self.assertFalse(status["can_reexport"])
            self.assertTrue(any("selected_posts" in item for item in status["missing"]))

    def test_missing_posts_scored_and_hydrated_disables_reexport(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            (run_dir / "cache" / "posts_scored.json").unlink()
            (run_dir / "cache" / "posts_hydrated.json").unlink()
            status = CacheStore(run_dir).get_cache_status()
            self.assertFalse(status["can_reexport"])
            self.assertTrue(any("posts" in item for item in status["missing"]))

    def test_no_cache_directory(self) -> None:
        with make_temp_run_dir() as run_dir:
            status = CacheStore(run_dir).get_cache_status()
            self.assertFalse(status["has_cache"])
            self.assertFalse(status["can_reexport"])

    def test_manifest_read_and_broken_manifest_is_tolerated(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            (run_dir / "manifest.json").write_text(
                json.dumps(load_fixture("sample_manifest.json"), ensure_ascii=False),
                encoding="utf-8",
            )
            status = CacheStore(run_dir).get_cache_status()
            self.assertIsInstance(status["manifest"], dict)
            assert_no_sensitive_fields(self, status["manifest"])

            (run_dir / "manifest.json").write_text("{bad json", encoding="utf-8")
            broken = CacheStore(run_dir).get_cache_status()
            self.assertIsNone(broken["manifest"])


if __name__ == "__main__":
    unittest.main()
