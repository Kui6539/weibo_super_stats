from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore
from export.reexport import reexport_from_cache


class ReexportTests(unittest.TestCase):
    def test_reexport_from_cache_updates_manifest_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            store = CacheStore(run_dir)
            post = {
                "post_id": "123",
                "user_name": "作者",
                "publish_time": "2026-05-01 12:00",
                "content": "正文",
                "post_url": "https://weibo.com/123",
                "likes": 1,
                "comments": 0,
                "reposts": 0,
                "score": 1.0,
                "top_comments_data": [],
            }
            store.write_stage("run_config", {"super_topic": "100808abc", "cookie": "SHOULD_NOT_WRITE"})
            store.write_stage("posts_scored", [post])
            store.write_stage("selected_posts", [post])
            result = reexport_from_cache(run_dir, export_types=["markdown", "csv", "summary"])
            manifest = result["manifest"]
            self.assertEqual(manifest["reexport_count"], 1)
            self.assertIsNotNone(manifest["last_reexport_at"])
            self.assertTrue((run_dir / "warma_weekly_report.md").exists())
            self.assertTrue((run_dir / "weibo_posts.csv").exists())
            self.assertNotIn("cookie", str(manifest).lower())


if __name__ == "__main__":
    unittest.main()

