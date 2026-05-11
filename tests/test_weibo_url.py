from __future__ import annotations

import unittest

from modules.weibo_url import build_weibo_url, extract_post_id, normalize_image_url, parse_super_topic_id


class WeiboUrlTests(unittest.TestCase):
    def test_extract_post_id(self) -> None:
        self.assertEqual(extract_post_id("https://weibo.com/detail/1234567890"), "1234567890")
        self.assertEqual(extract_post_id("https://weibo.com/u/abc?id=987654"), "987654")

    def test_build_weibo_url(self) -> None:
        self.assertEqual(build_weibo_url("123"), "https://weibo.com/detail/123")
        self.assertEqual(build_weibo_url("abc", "u1"), "https://weibo.com/u1/abc")

    def test_normalize_image_url(self) -> None:
        self.assertEqual(normalize_image_url("//wx1.sinaimg.cn/mw690/a.jpg"), "https://wx1.sinaimg.cn/large/a.jpg")

    def test_parse_super_topic_id(self) -> None:
        self.assertEqual(parse_super_topic_id("100808abc"), "100808abc")
        self.assertEqual(parse_super_topic_id("https://weibo.com/p/100808abc/super_index"), "100808abc")


if __name__ == "__main__":
    unittest.main()
