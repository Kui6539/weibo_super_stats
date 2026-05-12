from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from core.cache import CacheStore
from core.errors import ReexportCacheMissingError
from export.reexport import reexport_from_cache
from tests.helpers import assert_file_exists, assert_no_sensitive_fields, make_temp_run_dir, write_cache_fixture


class ReexportBundleTests(unittest.TestCase):
    def test_reexport_bundle_generates_all_outputs_without_network(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            with patch("requests.sessions.Session.request", side_effect=AssertionError("network disabled")):
                result = reexport_from_cache(
                    run_dir,
                    export_types=["markdown", "csv", "summary", "docx", "excel"],
                )

            assert_file_exists(self, run_dir / "weekly_report.md")
            assert_file_exists(self, run_dir / "weibo_posts.csv")
            assert_file_exists(self, run_dir / "weibo_summary.txt")
            assert_file_exists(self, run_dir / "weibo_posts.xlsx")
            self.assertTrue(list(run_dir.glob("weekly_report_*.docx")) or (run_dir / "weekly_report.docx").exists())
            manifest_path = run_dir / "manifest.json"
            assert_file_exists(self, manifest_path)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["reexport_count"], 1)
            self.assertIsNotNone(manifest["last_reexport_at"])
            assert_no_sensitive_fields(self, manifest)
            assert_no_sensitive_fields(self, result["manifest"])

    def test_missing_selected_posts_has_friendly_error(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            (run_dir / "cache" / "selected_posts.json").unlink()
            with self.assertRaises(ReexportCacheMissingError) as ctx:
                reexport_from_cache(run_dir)
            self.assertEqual(ctx.exception.code, "REEXPORT_CACHE_MISSING")
            self.assertIn("selected_posts", ctx.exception.suggestion)

    def test_missing_posts_cache_has_friendly_error(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            (run_dir / "cache" / "posts_scored.json").unlink()
            (run_dir / "cache" / "posts_hydrated.json").unlink()
            with self.assertRaises(ReexportCacheMissingError) as ctx:
                reexport_from_cache(run_dir)
            self.assertEqual(ctx.exception.code, "REEXPORT_CACHE_MISSING")
            self.assertIn("posts", ctx.exception.suggestion.lower())

    def test_missing_images_only_adds_warning(self) -> None:
        with make_temp_run_dir() as run_dir:
            store = write_cache_fixture(run_dir)
            posts = store.read_stage("selected_posts")
            posts[0]["image_local_paths"] = "images/missing/post.jpg"
            store.write_stage("selected_posts", posts)
            result = reexport_from_cache(run_dir, export_types=["markdown", "summary"])
            self.assertTrue(result["manifest"]["warnings"])
            assert_file_exists(self, run_dir / "weekly_report.md")


if __name__ == "__main__":
    unittest.main()
