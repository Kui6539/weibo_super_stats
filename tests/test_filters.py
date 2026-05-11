from __future__ import annotations

import unittest

from modules.crawler_filters import should_exclude_post


class FilterTests(unittest.TestCase):
    def test_video_post_filtered(self) -> None:
        excluded, reason = should_exclude_post({"has_video": True, "content": "普通内容"})
        self.assertTrue(excluded)
        self.assertEqual(reason, "视频帖")

    def test_summary_post_filtered(self) -> None:
        excluded, reason = should_exclude_post({"content": "本周精选内容汇总"})
        self.assertTrue(excluded)
        self.assertEqual(reason, "汇总帖")

    def test_navigation_post_filtered(self) -> None:
        excluded, reason = should_exclude_post({"content": "作品导航索引"})
        self.assertTrue(excluded)
        self.assertEqual(reason, "导航帖")

    def test_normal_image_post_not_filtered(self) -> None:
        excluded, reason = should_exclude_post({"content": "今天画了一张图", "original_image_urls": "https://example/a.jpg"})
        self.assertFalse(excluded)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()

