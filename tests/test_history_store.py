from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import core.history as history
from core.cache import CacheStore
from tests.helpers import assert_no_sensitive_fields


class HistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = history.HISTORY_PATH
        history.HISTORY_PATH = Path(self.tmp.name) / "weibo_stats_history.json"

    def tearDown(self) -> None:
        history.HISTORY_PATH = self.old_path
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
        store = CacheStore(run_dir)
        store.write_stage("run_config", {})
        store.write_stage("posts_scored", [{"post_id": "1"}])
        store.write_stage("selected_posts", [{"post_id": "1"}])
        manifest = {
            "run_id": run_dir.name,
            "created_at": "2026-05-12 01:01:01",
            "updated_at": "2026-05-12 01:02:01",
            "super_topic": "100808abc",
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
        assert_no_sensitive_fields(self, loaded)

        history.remove_history_item(run_dir.name)
        self.assertEqual(history.load_history()["items"], [])


if __name__ == "__main__":
    unittest.main()
