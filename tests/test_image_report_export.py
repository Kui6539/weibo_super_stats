from __future__ import annotations

import json
import unittest
from datetime import datetime

from export.image_report import ImageReportConfig, export_image_report
from export.image_report.adapter import calculate_weekly_issue
from export.image_report.models import ImageReportData, PageBlock, PostBlock
from export.image_report.paginator import paginate_posts
from export.image_report.renderer import render_preview_html
from export.reexport import reexport_from_cache
from tests.helpers import build_export_context_from_fixtures, make_temp_run_dir, write_cache_fixture


class ImageReportExportTests(unittest.TestCase):
    def test_export_image_report_writes_preview_and_metadata_without_jpg(self) -> None:
        with make_temp_run_dir() as run_dir:
            ctx = build_export_context_from_fixtures(run_dir)
            result = export_image_report(ctx, config={"render_jpg": False})

            self.assertTrue(result.preview.exists())
            self.assertTrue(result.metadata.exists())
            self.assertEqual(result.pages, [])
            html = result.preview.read_text(encoding="utf-8")
            self.assertIn("report-page", html)
            self.assertIn("测试超话周报 第3期", html)
            self.assertIn("热评", html)
            self.assertNotIn("打开原帖", html)

            metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
            self.assertGreaterEqual(metadata["page_count"], 1)
            self.assertLessEqual(metadata["page_count"], 9)
            for page in metadata["pages"]:
                self.assertLessEqual(page["post_count"], 5)

    def test_issue_calculator_uses_upcoming_saturday(self) -> None:
        self.assertEqual(calculate_weekly_issue(datetime(2026, 5, 28, 12, 0)), 6)
        self.assertEqual(calculate_weekly_issue(datetime(2026, 5, 30, 12, 0)), 6)

    def test_renderer_turns_weibo_emoticon_tokens_into_inline_images(self) -> None:
        with make_temp_run_dir() as run_dir:
            post = PostBlock(
                rank=1,
                post_id="1",
                author="作者",
                publish_time="2026-05-01 12:00",
                content="你好[哈哈]",
            )
            data = ImageReportData(
                title="Warma超话周报",
                issue="1",
                date_range="2026.05.01 - 2026.05.08",
                posts=[post],
                emoticons={"哈哈": "emoticons/d_haha.png"},
            )
            html = render_preview_html(
                data,
                [PageBlock(number=1, posts=[post], estimated_height=1200)],
                ImageReportConfig(render_jpg=False),
                run_dir,
            )

            self.assertIn('class="weibo-emoticon"', html)
            self.assertIn("emoticons/d_haha.png", html)

    def test_paginator_prefers_balanced_social_page_counts(self) -> None:
        posts = [
            PostBlock(
                rank=index,
                post_id=str(index),
                author=f"作者{index}",
                publish_time="2026-05-01 12:00",
                content="这是一条用于分页估算的测试正文。" * (6 + index % 3),
            )
            for index in range(1, 16)
        ]
        pages = paginate_posts(posts, ImageReportConfig(max_page_height=3200))

        self.assertIn(len(pages), {3, 4, 6, 9})
        self.assertEqual(sum(len(page.posts) for page in pages), 15)
        self.assertTrue(all(len(page.posts) <= 5 for page in pages))

    def test_reexport_can_generate_image_report_preview_from_cache(self) -> None:
        with make_temp_run_dir() as run_dir:
            write_cache_fixture(run_dir)
            result = reexport_from_cache(run_dir, export_types=["long_images"])
            manifest = result["manifest"]
            preview_rel = manifest["files"]["image_report_preview"]
            metadata_rel = manifest["files"]["image_report_metadata"]

            self.assertTrue((run_dir / preview_rel).exists())
            self.assertTrue((run_dir / metadata_rel).exists())
            self.assertIn("image_report_pages", manifest["files"])


if __name__ == "__main__":
    unittest.main()
