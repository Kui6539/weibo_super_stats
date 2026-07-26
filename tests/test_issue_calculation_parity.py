"""The weibo draft and the long-image report must agree on issue and dates.

Both are published together in a single weibo post, so a mismatch is visible
to readers. The issue anchor, the issue formula, the config date parser and
the "YYYY.MM.DD - YYYY.MM.DD" range were each written three times -- once in
modules/topic (the real owner) and again in both exporters -- so adjusting the
anchor in one place would have shipped two different issue numbers in the same
post.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from export.image_report import adapter
from export.weibo_body_exporter import _issue_reference_date as body_reference
from modules.time_utils import format_date_range, parse_config_datetime
from modules.topic import ISSUE_ONE_SATURDAY, calculate_weekly_issue


class SingleSourceTests(unittest.TestCase):
    def test_the_adapter_forwards_to_the_shared_calculator(self) -> None:
        self.assertIs(adapter.calculate_weekly_issue, calculate_weekly_issue)

    def test_both_exporters_pick_the_same_reference_date(self) -> None:
        config = {"window_start": "2026-06-01 04:00:00", "window_end": "2026-06-08 04:00"}
        self.assertEqual(body_reference(config), adapter._issue_reference_date(config))

    def test_window_end_wins_over_window_start(self) -> None:
        config = {"window_start": "2026-06-01 04:00:00", "window_end": "2026-06-08 04:00:00"}
        self.assertEqual(body_reference(config), datetime(2026, 6, 8, 4, 0, 0))

    def test_window_start_is_the_fallback(self) -> None:
        self.assertEqual(body_reference({"window_start": "2026-06-01 04:00:00"}), datetime(2026, 6, 1, 4, 0, 0))
        self.assertIsNone(body_reference({}))


class IssueFormulaTests(unittest.TestCase):
    def test_the_anchor_saturday_is_issue_one(self) -> None:
        self.assertEqual(calculate_weekly_issue(ISSUE_ONE_SATURDAY), 1)

    def test_weekdays_count_toward_the_upcoming_saturday(self) -> None:
        # 2026-04-20 is the Monday before the anchor Saturday.
        self.assertEqual(calculate_weekly_issue(datetime(2026, 4, 20)), 1)
        self.assertEqual(calculate_weekly_issue(datetime(2026, 4, 26)), 2)

    def test_issues_advance_one_per_week(self) -> None:
        self.assertEqual(calculate_weekly_issue(datetime(2026, 5, 2)), 2)
        self.assertEqual(calculate_weekly_issue(datetime(2026, 5, 9)), 3)

    def test_dates_before_the_anchor_never_go_below_one(self) -> None:
        self.assertEqual(calculate_weekly_issue(datetime(2020, 1, 1)), 1)


class ConfigDateParsingTests(unittest.TestCase):
    def test_every_stored_and_browser_format_parses(self) -> None:
        expected = datetime(2026, 6, 8, 4, 0)
        for text in ("2026-06-08 04:00:00", "2026-06-08 04:00", "2026-06-08T04:00:00", "2026-06-08T04:00"):
            with self.subTest(text=text):
                self.assertEqual(parse_config_datetime(text), expected)

    def test_junk_is_none_rather_than_an_exception(self) -> None:
        for text in ("", None, "not a date", "2026/06/08"):
            with self.subTest(text=text):
                self.assertIsNone(parse_config_datetime(text))


class DateRangeTests(unittest.TestCase):
    def test_the_range_renders_with_dots(self) -> None:
        self.assertEqual(
            format_date_range("2026-06-01 04:00:00", "2026-06-08 04:00:00"), "2026.06.01 - 2026.06.08"
        )

    def test_an_unparsable_end_yields_an_empty_range(self) -> None:
        self.assertEqual(format_date_range("2026-06-01 04:00:00", "junk"), "")
        self.assertEqual(format_date_range(None, None), "")

    def test_both_exporters_render_the_same_range(self) -> None:
        from export.weibo_body_exporter import _date_range

        config = {"window_start": "2026-06-01 04:00:00", "window_end": "2026-06-08 04:00:00"}
        self.assertEqual(_date_range(config), adapter._date_range_from_config(config))


if __name__ == "__main__":
    unittest.main()
