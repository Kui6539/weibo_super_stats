"""A failed export must not cost the user the crawl.

The common Windows case is that last week's weibo_posts.xlsx or
weekly_report.docx is still open in Excel or Word, so save() raises
PermissionError. That used to fall through to the generic handler, which
deleted both the output directory and the project-root cache -- discarding a
completed crawl, comment analysis, manual selection and image download, and
forcing a full re-crawl against weibo.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore
from core.job import cleanup_incomplete_artifacts


class ExportFailureRecoveryTests(unittest.TestCase):
    def test_recoverable_cache_survives_a_failed_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_040404"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            (run_dir / "weibo_posts.csv").write_text("partial", encoding="utf-8")

            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})
            store.write_stage("posts_scored", [{"post_id": "1"}])
            store.write_stage("selected_posts", [{"post_id": "1"}])

            result = cleanup_incomplete_artifacts(run_dir, output_dir, store, keep_cache=True)

            self.assertTrue(run_dir.exists(), "run directory is the history panel's entry point")
            self.assertTrue((cache_root / run_dir.name).exists())
            self.assertTrue(store.get_cache_status()["can_reexport"])
            self.assertEqual(result["deleted_dirs"], [])
            self.assertTrue(result["kept_cache"])

    def test_cancel_still_discards_everything(self) -> None:
        """Cancelling is an explicit "throw it away"; only failures preserve."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_050505"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            store = CacheStore(run_dir, cache_root=cache_root)
            store.write_stage("run_config", {"ok": True})
            store.write_stage("selected_posts", [{"post_id": "1"}])

            cleanup_incomplete_artifacts(run_dir, output_dir, store, keep_cache=False)

            self.assertFalse(run_dir.exists())
            self.assertFalse((cache_root / run_dir.name).exists())

    def test_export_failed_manifest_is_not_treated_as_garbage(self) -> None:
        """A partially exported run must survive a later cleanup pass."""
        from core.artifact_cleanup import is_run_dir_deletable as _is_cancel_run_dir_deletable

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_dir = base / "output"
            run_dir = output_dir / "20260602_060606"
            run_dir.mkdir(parents=True)
            for status, deletable in (
                ("completed", False),
                ("reexported", False),
                ("export_failed", False),
                ("partial", False),
                ("failed", True),
            ):
                with self.subTest(status=status):
                    (run_dir / "manifest.json").write_text(
                        f'{{"status": "{status}"}}', encoding="utf-8"
                    )
                    self.assertEqual(
                        _is_cancel_run_dir_deletable(run_dir, output_dir), deletable
                    )


if __name__ == "__main__":
    unittest.main()
