from __future__ import annotations

import unittest

from export.csv_exporter import DEFAULT_EXPORT_COLUMN_MAP, export_posts_csv
from export.markdown_exporter import export_weekly_report_md
from export.summary_exporter import build_summary, write_summary_txt
from tests.helpers import assert_file_exists, build_export_context_from_fixtures, make_temp_run_dir


class ExportBundleTests(unittest.TestCase):
    def test_export_bundle_generates_offline_files(self) -> None:
        with make_temp_run_dir() as run_dir:
            ctx = build_export_context_from_fixtures(run_dir)
            md_path = run_dir / "weekly_report.md"
            csv_path = run_dir / "weibo_posts.csv"
            summary_path = run_dir / "weibo_summary.txt"

            export_weekly_report_md(
                ctx.selected_posts,
                md_path,
                title=str(ctx.config["report_title"]),
                leaderboards=ctx.config.get("leaderboards"),
                preselected=True,
            )
            export_posts_csv(ctx.selected_posts, csv_path)
            summary = build_summary(ctx.selected_posts)
            write_summary_txt(
                summary,
                summary_path,
                leaderboards=ctx.config.get("leaderboards"),
                all_posts_summary=build_summary(ctx.all_posts),
            )

            try:
                from export.docx_exporter import export_docx

                docx_paths = export_docx(ctx, run_dir / "weekly_report.docx")
                self.assertTrue(docx_paths)
                for path in docx_paths:
                    assert_file_exists(self, path)
            except ImportError as err:
                self.skipTest(f"python-docx 不可用：{err}")

            try:
                from export.excel_exporter import export_excel

                xlsx_path = export_excel(ctx, run_dir / "weibo_posts.xlsx")
                assert_file_exists(self, xlsx_path)
            except ImportError as err:
                self.skipTest(f"openpyxl 不可用：{err}")

            assert_file_exists(self, md_path)
            assert_file_exists(self, csv_path)
            assert_file_exists(self, summary_path)
            self.assertGreater(len(md_path.read_text(encoding="utf-8").strip()), 20)
            self.assertIn(DEFAULT_EXPORT_COLUMN_MAP[0][1], csv_path.read_text(encoding="utf-8-sig"))

            summary_text = summary_path.read_text(encoding="utf-8")
            self.assertIn(str(summary["total_posts"]), summary_text)
            self.assertIn(str(summary["sum_engagement"]), summary_text)
            self.assertIn("Top3", summary_text)
            self.assertGreater(len(summary_text), 50)


if __name__ == "__main__":
    unittest.main()
