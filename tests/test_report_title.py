from __future__ import annotations

import unittest

from crawler import build_report_title, extract_super_topic_name, normalize_super_topic_name


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


if __name__ == "__main__":
    unittest.main()
