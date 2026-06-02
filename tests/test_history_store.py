from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import core.history as history
from core.cache import CACHE_ROOT_ENV, CacheStore
from tests.helpers import assert_no_sensitive_fields


class HistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = history.HISTORY_PATH
        self.old_cache_root = os.environ.get(CACHE_ROOT_ENV)
        history.HISTORY_PATH = Path(self.tmp.name) / "weibo_stats_history.json"
        os.environ[CACHE_ROOT_ENV] = str(Path(self.tmp.name) / ".project_cache")

    def tearDown(self) -> None:
        history.HISTORY_PATH = self.old_path
        if self.old_cache_root is None:
            os.environ.pop(CACHE_ROOT_ENV, None)
        else:
            os.environ[CACHE_ROOT_ENV] = self.old_cache_root
        self.tmp.cleanup()

    def test_load_save_history(self) -> None:
        data = history.save_history({"items": [{"run_id": "20260512_010101", "cookie": "secret"}]})
        self.assertEqual(data["version"], 1)
        loaded = history.load_history()
        self.assertEqual(loaded["items"][0]["run_id"], "20260512_010101")
        assert_no_sensitive_fields(self, loaded)

    def test_broken_history_is_backed_up(self) -> None:
        history.HISTORY_PATH.write_text("{broken", encoding="utf-8")
        loaded = history.load_history()
        self.assertEqual(loaded["items"], [])
        self.assertTrue(history.HISTORY_PATH.with_name("weibo_stats_history.broken.json").exists())

    def test_add_and_remove_history_item_from_manifest(self) -> None:
        run_dir = Path(self.tmp.name) / "output" / "20260512_010101"
        run_dir.mkdir(parents=True)
        store = CacheStore(run_dir)
        store.write_stage("run_config", {})
        store.write_stage("posts_scored", [{"post_id": "1"}])
        store.write_stage("selected_posts", [{"post_id": "1"}])
        manifest = {
            "run_id": run_dir.name,
            "created_at": "2026-05-12 01:01:01",
            "updated_at": "2026-05-12 01:02:01",
            "super_topic": "100808abc",
            "super_topic_name": "原神",
            "super_topic_id": "100808abc",
            "report_title": "原神超话周报",
            "issue": "6",
            "selected_count": 1,
            "total_posts": 3,
            "status": "completed",
            "files": {"markdown": "weekly_report.md"},
            "cookie": "SHOULD_NOT_APPEAR",
        }
        (run_dir / "weekly_report.md").write_text("# ok", encoding="utf-8")
        history.add_history_item_from_manifest(run_dir, manifest)
        loaded = json.loads(history.HISTORY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded["items"]), 1)
        self.assertTrue(loaded["items"][0]["can_reexport"])
        self.assertEqual(loaded["items"][0]["report_title"], "原神超话周报")
        self.assertEqual(loaded["items"][0]["issue"], "6")
        self.assertEqual(loaded["items"][0]["title_with_issue"], "原神超话周报 第6期")
        assert_no_sensitive_fields(self, loaded)

        duplicate = history.find_history_duplicate("https://weibo.com/p/100808abc/super_index", "第6期")
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["run_id"], run_dir.name)
        self.assertIsNone(history.find_history_duplicate("100808abc", "7"))
        self.assertIsNone(history.find_history_duplicate("100808def", "6"))

        history.remove_history_item(run_dir.name)
        self.assertEqual(history.load_history()["items"], [])


if __name__ == "__main__":
    unittest.main()
