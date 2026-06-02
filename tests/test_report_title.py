from __future__ import annotations

import unittest

from crawler import build_report_title, extract_super_topic_name, normalize_super_topic_name
from modules.topic import format_report_title_with_issue, normalize_issue_value, normalize_report_title


class ReportTitleTests(unittest.TestCase):
    def test_build_report_title_uses_topic_name(self) -> None:
        self.assertEqual(build_report_title("原神超话"), "原神超话周报")
        self.assertEqual(build_report_title("Warma"), "Warma超话周报")

    def test_build_report_title_falls_back_to_generic(self) -> None:
        self.assertEqual(build_report_title("", "100808abcdef"), "微博超话周报")

    def test_extract_super_topic_name_from_html_title(self) -> None:
        html = "<html><head><title>原神超话 - 微博</title></head></html>"
        self.assertEqual(extract_super_topic_name(html), "原神")

    def test_normalize_super_topic_name_strips_suffix(self) -> None:
        self.assertEqual(normalize_super_topic_name("#明日方舟超话#"), "明日方舟")
        self.assertEqual(normalize_super_topic_name("明日方舟超话——新浪超话"), "明日方舟")

    def test_normalize_report_title_strips_sina_suffix(self) -> None:
        self.assertEqual(normalize_report_title("明日方舟超话——新浪超话周报"), "明日方舟超话周报")
        self.assertEqual(normalize_report_title("明日方舟超话——新浪微博超话社区周报"), "明日方舟超话周报")

    def test_normalize_report_title_collapses_weibo_seo_keywords(self) -> None:
        raw = "warma，warma超话，游戏、游戏主播，超话社区、微博超话、兴趣社区。超话周报"
        self.assertEqual(normalize_report_title(raw), "warma超话周报")
        self.assertEqual(build_report_title(raw), "warma超话周报")

    def test_format_report_title_with_issue_replaces_trailing_issue(self) -> None:
        self.assertEqual(format_report_title_with_issue("明日方舟超话周报", "7"), "明日方舟超话周报 第7期")
        self.assertEqual(format_report_title_with_issue("明日方舟超话周报 第6期", "7"), "明日方舟超话周报 第7期")
        self.assertEqual(normalize_issue_value("第007期"), "7")


if __name__ == "__main__":
    unittest.main()
