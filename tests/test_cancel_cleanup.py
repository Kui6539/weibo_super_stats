from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore
from core.crawl_types import CrawlConfig
from core.job import CrawlJob, cleanup_cancelled_artifacts, cleanup_incomplete_artifacts


class CancelCleanupTests(unittest.TestCase):
    def test_cleanup_cancelled_artifacts_removes_run_dir_and_project_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_010101"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            (run_dir / "partial.txt").write_text("partial", encoding="utf-8")

            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})

            result = cleanup_cancelled_artifacts(run_dir, output_dir, store)

            self.assertFalse(run_dir.exists())
            self.assertFalse((cache_root / run_dir.name).exists())
            self.assertIn(str(run_dir.resolve()), result["deleted_dirs"])
            self.assertIn(str((cache_root / run_dir.name).resolve()), result["deleted_dirs"])
            self.assertEqual(result["errors"], [])

    def test_cleanup_incomplete_artifacts_removes_failed_run_dir_and_project_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_030303"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            (run_dir / "partial_export.txt").write_text("partial", encoding="utf-8")

            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})

            result = cleanup_incomplete_artifacts(run_dir, output_dir, store)

            self.assertFalse(run_dir.exists())
            self.assertFalse((cache_root / run_dir.name).exists())
            self.assertIn(str(run_dir.resolve()), result["deleted_dirs"])
            self.assertIn(str((cache_root / run_dir.name).resolve()), result["deleted_dirs"])
            self.assertEqual(result["errors"], [])

    def test_cleanup_cancelled_artifacts_preserves_completed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_020202"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            (run_dir / "manifest.json").write_text('{"status": "completed"}', encoding="utf-8")

            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})

            result = cleanup_cancelled_artifacts(run_dir, output_dir, store)

            self.assertTrue(run_dir.exists())
            self.assertTrue((cache_root / run_dir.name).exists())
            self.assertEqual(result["deleted_dirs"], [])
            self.assertTrue(result["skipped"])

    def test_cleanup_cancelled_artifacts_rejects_non_run_dir_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "not_a_run"
            run_dir.mkdir(parents=True)

            result = cleanup_cancelled_artifacts(run_dir, output_dir)

            self.assertTrue(run_dir.exists())
            self.assertEqual(result["deleted_dirs"], [])
            self.assertTrue(result["skipped"])

    def test_request_cancel_keeps_awaiting_selection_active_until_worker_cleans_up(self) -> None:
        job = CrawlJob(CrawlConfig(super_topic="测试超话", cookie=""), Path("output"))
        job.status = "awaiting_selection"
        job.stage = "selection"

        accepted = job.request_cancel("正在取消，请等待当前请求结束。")

        self.assertTrue(accepted)
        self.assertEqual(job.status, "awaiting_selection")
        self.assertTrue(job.cancel_requested.is_set())

    def test_failed_cleanup_records_artifact_cleanup_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_040404"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})

            job = CrawlJob(CrawlConfig(super_topic="测试超话", cookie=""), output_dir)
            job.run_dir = run_dir
            job._cleanup_incomplete_artifacts(run_dir, store, reason="failed")
            snapshot = job.snapshot()

            self.assertFalse(run_dir.exists())
            self.assertFalse((cache_root / run_dir.name).exists())
            self.assertIsInstance(snapshot.get("artifact_cleanup"), dict)
            self.assertIsNone(snapshot.get("cancel_cleanup"))
            self.assertTrue(any("已自动清理未完成任务目录与缓存" in row["message"] for row in snapshot["logs"]))


if __name__ == "__main__":
    unittest.main()
