from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from export.csv_exporter import export_posts_csv
from export.markdown_exporter import export_weekly_report_md
from export.summary_exporter import build_summary, write_summary_txt


class ExportMarkdownCsvSummaryTests(unittest.TestCase):
    def test_markdown_csv_summary_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            posts = [
                {
                    "post_id": "1",
                    "user_name": "作者",
                    "publish_time": "2026-05-01 12:00",
                    "content": "正文",
                    "post_url": "https://weibo.com/detail/1",
                    "likes": 3,
                    "comments": 2,
                    "reposts": 1,
                    "engagement_total": 6,
                    "score": 1.5,
                    "top_comments_data": [],
                }
            ]
            md_path = run_dir / "weekly_report.md"
            csv_path = run_dir / "weibo_posts.csv"
            summary_path = run_dir / "weibo_summary.txt"

            export_weekly_report_md(posts, md_path, title="测试超话周报", preselected=True)
            export_posts_csv(posts, csv_path, [("post_id", "帖子ID"), ("content", "帖子内容")])
            summary = build_summary(posts)
            write_summary_txt(summary, summary_path)

            self.assertIn("# 测试超话周报", md_path.read_text(encoding="utf-8"))
            self.assertIn("帖子ID", csv_path.read_text(encoding="utf-8-sig"))
            self.assertIn("入选帖子数", summary_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(json.dumps(summary, ensure_ascii=False))["total_posts"], 1)


if __name__ == "__main__":
    unittest.main()
