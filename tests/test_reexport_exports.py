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
