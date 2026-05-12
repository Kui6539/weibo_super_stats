from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import core.history as history
from core.cache import CacheStore


class HistoryScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_history = tempfile.TemporaryDirectory()
        self.old_history_path = history.HISTORY_PATH
        history.HISTORY_PATH = Path(self.tmp_history.name) / "weibo_stats_history.json"
        self.output_root = Path.cwd() / "output"
        self.output_root.mkdir(exist_ok=True)
        self.tmp_output = tempfile.TemporaryDirectory(dir=self.output_root, prefix="history_scan_")

    def tearDown(self) -> None:
        history.HISTORY_PATH = self.old_history_path
        self.tmp_output.cleanup()
        self.tmp_history.cleanup()

    def test_scan_manifests_skips_broken_manifest_and_sorts(self) -> None:
        first = Path(self.tmp_output.name) / "20260511_010101"
        second = Path(self.tmp_output.name) / "20260512_010101"
        broken = Path(self.tmp_output.name) / "20260510_010101"
        for run_dir in (first, second, broken):
            run_dir.mkdir(parents=True)
        self._write_manifest(first, "2026-05-11 01:01:01")
        self._write_manifest(second, "2026-05-12 01:01:01")
        (broken / "manifest.json").write_text("{broken", encoding="utf-8")

        result = history.scan_output_history(Path(self.tmp_output.name))
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["run_id"], "20260512_010101")
        self.assertTrue(result["warnings"])

    def _write_manifest(self, run_dir: Path, created_at: str) -> None:
        store = CacheStore(run_dir)
        store.write_stage("run_config", {})
        store.write_stage("posts_scored", [{"post_id": "1"}])
        store.write_stage("selected_posts", [{"post_id": "1"}])
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "status": "completed",
                    "files": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
