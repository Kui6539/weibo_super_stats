from __future__ import annotations

import unittest
from datetime import datetime

from modules.time_utils import format_datetime, is_post_in_range, parse_weibo_time


class TimeUtilsTests(unittest.TestCase):
    def test_parse_standard_time(self) -> None:
        self.assertEqual(parse_weibo_time("2026-05-01 12:30"), datetime(2026, 5, 1, 12, 30))

    def test_parse_relative_date_text(self) -> None:
        now = datetime(2026, 5, 11, 10, 0)
        self.assertEqual(parse_weibo_time("昨天 09:30", now=now), datetime(2026, 5, 10, 9, 30))

    def test_is_post_in_range(self) -> None:
        self.assertTrue(
            is_post_in_range("2026-05-01 12:30", datetime(2026, 5, 1), datetime(2026, 5, 2))
        )
        self.assertFalse(
            is_post_in_range("2026-05-03 12:30", datetime(2026, 5, 1), datetime(2026, 5, 2))
        )

    def test_format_datetime(self) -> None:
        self.assertEqual(format_datetime(datetime(2026, 5, 1, 12, 30)), "2026-05-01 12:30")


if __name__ == "__main__":
    unittest.main()
