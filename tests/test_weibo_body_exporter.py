from __future__ import annotations

import unittest

from export.weibo_body_exporter import build_weibo_body_text, export_weibo_body
from tests.helpers import build_export_context_from_fixtures, make_temp_run_dir


class WeiboBodyExporterTests(unittest.TestCase):
    def test_build_weibo_body_contains_leaderboards_and_clickable_links(self) -> None:
        with make_temp_run_dir() as run_dir:
            ctx = build_export_context_from_fixtures(run_dir)
            text = build_weibo_body_text(ctx)

            self.assertIn("评论数量榜", text)
            self.assertIn("评论质量榜", text)
            self.assertIn("Top15 原帖", text)
            self.assertIn("@", text)
            self.assertIn("https://weibo.com/", text)
            self.assertNotIn("](", text)

    def test_export_weibo_body_writes_txt(self) -> None:
        with make_temp_run_dir() as run_dir:
            ctx = build_export_context_from_fixtures(run_dir)
            path = export_weibo_body(ctx)

            self.assertEqual(path.name, "weibo_body.txt")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
