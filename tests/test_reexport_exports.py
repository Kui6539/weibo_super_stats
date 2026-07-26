from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore
from export.reexport import reexport_from_cache

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class ReexportExportsTests(unittest.TestCase):
    def test_reexport_generates_all_report_files_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            store = CacheStore(run_dir)
            posts = json.loads((FIXTURE_DIR / "sample_posts_scored.json").read_text(encoding="utf-8"))
            selected = json.loads((FIXTURE_DIR / "sample_selected_posts.json").read_text(encoding="utf-8"))
            community_stats = json.loads((FIXTURE_DIR / "sample_community_stats.json").read_text(encoding="utf-8"))
            images_manifest = json.loads((FIXTURE_DIR / "sample_images_manifest.json").read_text(encoding="utf-8"))
            store.write_stage("run_config", {"super_topic": "100808abc", "report_title": "测试超话周报"})
            store.write_stage("posts_scored", posts)
            store.write_stage("selected_posts", selected)
            store.write_stage("community_stats", community_stats)
            store.write_stage("images_manifest", images_manifest)

            result = reexport_from_cache(run_dir, export_types=["markdown", "csv", "summary", "docx", "excel"])

            self.assertTrue((run_dir / "weekly_report.md").exists())
            self.assertTrue((run_dir / "weibo_posts.csv").exists())
            self.assertTrue((run_dir / "weibo_summary.txt").exists())
            self.assertTrue((run_dir / "weibo_posts.xlsx").exists())
            self.assertTrue((run_dir / "weekly_report_sum.docx").exists())
            self.assertTrue(list(run_dir.glob("weekly_report_*.docx")))
            self.assertIn("manifest", result)


if __name__ == "__main__":
    unittest.main()


class LeaderboardFormattingParityTests(unittest.TestCase):
    """Reexport must format leaderboards exactly like the initial export.

    They used separate formatters, so regenerating a report silently dropped
    the rank, the @ prefix, the like totals and the hot-comment counts.
    """

    def test_summary_exporter_defaults_to_the_shared_formatter(self) -> None:
        from export.report_helpers import format_leaderboard_line
        from export.summary_exporter import _append_leaderboards

        rows = {
            "comment_count_top3": [
                {"rank": 1, "user_name": "甲", "comment_count": 2, "commented_post_count": 1},
            ],
            "comment_quality_top3": [
                {"rank": 1, "user_name": "甲", "comment_count": 2, "comment_likes_total": 5, "hot_top3_count": 2},
            ],
        }
        default_lines: list[str] = []
        explicit_lines: list[str] = []
        _append_leaderboards(default_lines, rows, None)
        _append_leaderboards(explicit_lines, rows, format_leaderboard_line)

        self.assertEqual(default_lines, explicit_lines)
        joined = "\n".join(default_lines)
        self.assertIn("1. @甲", joined)
        self.assertIn("本周评论获赞 5", joined)
        self.assertIn("热评前三 2 次", joined)

    def test_the_crawler_shim_points_at_the_shared_implementation(self) -> None:
        import crawler
        from export.report_helpers import format_leaderboard_line

        self.assertIs(crawler._format_leaderboard_line, format_leaderboard_line)
