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

    def test_an_ordinary_post_with_a_link_is_kept(self) -> None:
        """Weibo prints every external link as the literal text 网页链接.

        Treating that as a roundup marker dropped popular posts that merely
        linked somewhere, and a filtered post never reaches the candidate list
        for the user to rescue.
        """
        for content in (
            "今天塔菲好可爱！大家快看 网页链接",
            "新画的图！求个赞 网页链接",
            "前往观赏这个直播回放",
        ):
            with self.subTest(content=content):
                excluded, _ = should_exclude_post({"content": content})
                self.assertFalse(excluded)

    def test_a_link_plus_roundup_context_is_still_filtered(self) -> None:
        for content in (
            "整理了本周所有投稿 网页链接",
            "本期作品前往观赏",
            "塔菲二创作品合集 网页链接",
        ):
            with self.subTest(content=content):
                excluded, _ = should_exclude_post({"content": content})
                self.assertTrue(excluded)


if __name__ == "__main__":
    unittest.main()

