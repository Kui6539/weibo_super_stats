from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore


class CacheStatusTests(unittest.TestCase):
    def test_complete_cache_can_reexport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.write_stage("run_config", {})
            store.write_stage("posts_scored", [{"post_id": "1"}])
            store.write_stage("selected_posts", [{"post_id": "1"}])
            status = store.get_cache_status()
            self.assertTrue(status["has_cache"])
            self.assertTrue(status["can_reexport"])

    def test_missing_selected_posts_blocks_reexport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.write_stage("run_config", {})
            store.write_stage("posts_scored", [{"post_id": "1"}])
            status = store.get_cache_status()
            self.assertFalse(status["can_reexport"])
            self.assertIn("selected_posts.json", status["missing"])

    def test_missing_scored_posts_blocks_reexport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.write_stage("run_config", {})
            store.write_stage("selected_posts", [{"post_id": "1"}])
            status = store.get_cache_status()
            self.assertFalse(status["can_reexport"])
            self.assertIn("posts_scored.json 或 posts_hydrated.json", status["missing"])


if __name__ == "__main__":
    unittest.main()

