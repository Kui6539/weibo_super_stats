from __future__ import annotations

import unittest

from export.report_helpers import clean_image_report_text, clean_report_text
from modules.text_cleaning import clean_topic_tags, collapse_blank_lines, normalize_weibo_text, strip_html_text


class TextCleaningTests(unittest.TestCase):
    def test_clean_topic_tags(self) -> None:
        self.assertEqual(clean_topic_tags("#warma超话# 正文内容"), "正文内容")
        self.assertEqual(clean_topic_tags("#warma[超话]# 正文内容"), "正文内容")
        self.assertEqual(clean_topic_tags("#Warma【超话】# 正文内容"), "正文内容")

    def test_preserve_newlines(self) -> None:
        text = clean_topic_tags("第一行\n#warma超话#\n第二行", preserve_newlines=True)
        self.assertIn("第一行", text)
        self.assertIn("第二行", text)
        self.assertIn("\n", text)

    def test_strip_html_text(self) -> None:
        self.assertEqual(strip_html_text("<p>你好<br>世界</p>"), "你好 世界")

    def test_no_false_delete_chinese(self) -> None:
        self.assertEqual(normalize_weibo_text("普通 中文  内容"), "普通 中文 内容")

    def test_collapse_blank_lines(self) -> None:
        self.assertEqual(collapse_blank_lines("a\n\n\nb"), "a\n\nb")

    def test_image_report_text_preserves_weibo_emoticon_tokens(self) -> None:
        self.assertEqual(clean_report_text("你好[哈哈]"), "你好(*≧▽≦)")
        self.assertEqual(clean_image_report_text("你好[哈哈]"), "你好[哈哈]")


if __name__ == "__main__":
    unittest.main()


class WeiboEmoticonReplacementTests(unittest.TestCase):
    """Unknown [xxx] tokens are ordinary text, not emoticons."""

    def test_known_emoticons_are_replaced(self) -> None:
        from export.report_helpers import replace_weibo_emoticons

        self.assertNotIn("[doge]", replace_weibo_emoticons("看看这个[doge]"))

    def test_unknown_bracket_text_survives_verbatim(self) -> None:
        from export.report_helpers import replace_weibo_emoticons

        for text in ("请看[公告]内容", "[抽奖规则]如下", "第[3]期"):
            with self.subTest(text=text):
                self.assertEqual(replace_weibo_emoticons(text), text)
