from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.output_cleanup import cleanup_output, cleanup_preview, output_summary
from server.handlers import parse_optional_int


class OutputCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_root = Path.cwd() / "output"
        self.output_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.output_root, prefix="cleanup_root_")
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_summary_and_preview(self) -> None:
        self._make_run("20260510_010101", can_reexport=False)
        self._make_run("20260511_010101", can_reexport=True)
        summary = output_summary(self.root)
        self.assertEqual(summary["run_count"], 2)

        preview = cleanup_preview(self.root, keep_recent=0, incomplete_only=True)
        self.assertEqual(preview["delete_count"], 1)
        self.assertEqual(preview["items"][0]["run_id"], "20260510_010101")

    def test_cleanup_requires_confirm_and_abnormal_dirs_are_selected(self) -> None:
        old_dir = self._make_run("20260510_010101", can_reexport=False)
        recent_dir = self._make_run("20260511_010101", can_reexport=False)

        no_delete = cleanup_output(self.root, keep_recent=0, incomplete_only=True, confirm=False)
        self.assertFalse(no_delete["deleted"])
        self.assertTrue(old_dir.exists())

        deleted = cleanup_output(self.root, keep_recent=1, incomplete_only=True, confirm=True)
        self.assertTrue(deleted["deleted"])
        self.assertFalse(old_dir.exists())
        self.assertFalse(recent_dir.exists())

    def test_api_keep_recent_zero_is_preserved(self) -> None:
        self.assertEqual(parse_optional_int(0, 5), 0)
        self.assertEqual(parse_optional_int("0", 5), 0)
        self.assertEqual(parse_optional_int("", 5), 5)

    def test_preview_reports_output_file_integrity_and_default_selection(self) -> None:
        recent = self._make_run("20260512_010101", can_reexport=False)
        (recent / "weekly_report.md").write_text("# ok", encoding="utf-8")
        (recent / "weibo_posts.csv").write_text("a,b", encoding="utf-8")
        (recent / "weibo_posts.xlsx").write_text("xlsx", encoding="utf-8")
        (recent / "weibo_summary.txt").write_text("summary", encoding="utf-8")
        (recent / "manifest.json").write_text(
            '{"status":"completed","files":{"markdown":"weekly_report.md","csv":"weibo_posts.csv","xlsx":"weibo_posts.xlsx","summary":"weibo_summary.txt"}}',
            encoding="utf-8",
        )
        broken = self._make_run("20260511_010101", can_reexport=True)
        (broken / "weekly_report.md").write_text("# ok", encoding="utf-8")
        (broken / "manifest.json").write_text(
            '{"status":"completed","files":{"markdown":"weekly_report.md","csv":"missing.csv"}}',
            encoding="utf-8",
        )

        preview = cleanup_preview(self.root, keep_recent=1)
        rows = {item["run_id"]: item for item in preview["all_items"]}

        self.assertFalse(rows["20260512_010101"]["selected"])
        self.assertEqual(rows["20260512_010101"]["directory_kind"], "cache_incomplete_output_complete")
        self.assertTrue(rows["20260512_010101"]["output_files_complete"])
        self.assertFalse(rows["20260512_010101"]["can_reexport"])
        self.assertTrue(rows["20260511_010101"]["selected"])
        self.assertEqual(rows["20260511_010101"]["directory_kind"], "output_incomplete_recoverable")
        self.assertFalse(rows["20260511_010101"]["output_files_complete"])
        self.assertIn("missing.csv", rows["20260511_010101"]["missing_output_files"])

    def test_complete_normal_dir_is_hidden_until_it_matches_rules(self) -> None:
        complete = self._make_run("20260512_010101", can_reexport=True)
        (complete / "weekly_report.md").write_text("# ok", encoding="utf-8")
        (complete / "weibo_posts.csv").write_text("a,b", encoding="utf-8")
        (complete / "weibo_posts.xlsx").write_text("xlsx", encoding="utf-8")
        (complete / "weibo_summary.txt").write_text("summary", encoding="utf-8")
        (complete / "manifest.json").write_text(
            '{"status":"completed","files":{"markdown":"weekly_report.md","csv":"weibo_posts.csv","xlsx":"weibo_posts.xlsx","summary":"weibo_summary.txt"}}',
            encoding="utf-8",
        )

        protected = cleanup_preview(self.root, keep_recent=1)
        self.assertNotIn("20260512_010101", {item["run_id"] for item in protected["all_items"]})

        unprotected = cleanup_preview(self.root, keep_recent=0)
        rows = {item["run_id"]: item for item in unprotected["all_items"]}
        self.assertTrue(rows["20260512_010101"]["selected"])
        self.assertEqual(rows["20260512_010101"]["directory_kind"], "normal_complete")

    def test_cleanup_uses_selected_run_ids(self) -> None:
        first = self._make_run("20260510_010101", can_reexport=False)
        second = self._make_run("20260511_010101", can_reexport=False)

        cleanup_output(self.root, keep_recent=0, incomplete_only=True, confirm=True, selected_run_ids=["20260511_010101"])

        self.assertTrue(first.exists())
        self.assertFalse(second.exists())

    def _make_run(self, name: str, can_reexport: bool) -> Path:
        run_dir = self.root / name
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text('{"status":"completed","files":{}}', encoding="utf-8")
        cache = run_dir / "cache"
        cache.mkdir()
        (cache / "run_config.json").write_text("{}", encoding="utf-8")
        if can_reexport:
            (cache / "posts_scored.json").write_text('[{"post_id":"1"}]', encoding="utf-8")
            (cache / "selected_posts.json").write_text('[{"post_id":"1"}]', encoding="utf-8")
        return run_dir


if __name__ == "__main__":
    unittest.main()
