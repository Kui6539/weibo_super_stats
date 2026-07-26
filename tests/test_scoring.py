from __future__ import annotations

import unittest
from datetime import datetime

from modules.crawler_scoring import ScoreDetail, calculate_score, prepare_score_config


class ScoringTests(unittest.TestCase):
    def test_basic_score_detail(self) -> None:
        detail = calculate_score(
            {"likes": 10, "comments": 8, "author_replies": 3, "reposts": 2, "publish_dt": datetime(2026, 5, 1)},
            {"topic_comment_factor": 1.0, "window_end": datetime(2026, 5, 8)},
        )
        self.assertIsInstance(detail, ScoreDetail)
        self.assertGreater(detail.final_score, 0)
        self.assertEqual(set(detail.to_dict()), {
            "likes_score",
            "non_author_comment_score",
            "author_reply_score",
            "repost_score",
            "base_score",
            "time_weight",
            "final_score",
        })

    def test_topic_comment_factor_floor(self) -> None:
        low = calculate_score({"comments": 10}, {"topic_comment_factor": 0.1})
        floor = calculate_score({"comments": 10}, {"topic_comment_factor": 0.5})
        self.assertEqual(low.non_author_comment_score, floor.non_author_comment_score)

    def test_prepared_score_config_matches_raw_config(self) -> None:
        post = {
            "likes": 12,
            "comments": 5,
            "author_replies": 2,
            "reposts": 3,
            "publish_dt": datetime(2026, 5, 3, 12, 0),
        }
        config = {
            "topic_comment_factor": 1.2,
            "likes_weight": 0.3,
            "comment_weight": 0.5,
            "author_reply_weight": 0.2,
            "repost_weight": 0.1,
            "window_end": datetime(2026, 5, 8, 12, 0),
        }
        self.assertEqual(
            calculate_score(post, prepare_score_config(config)).to_dict(),
            calculate_score(post, config).to_dict(),
        )


if __name__ == "__main__":
    unittest.main()


class TimeWeightSingleSourceTests(unittest.TestCase):
    """The formula lives in one place now; crawler.py only forwards to it.

    It used to exist twice -- parameterised in crawler.py for the calibration
    sweep, hardcoded at strength 0.06 in modules/crawler_scoring. Adjusting the
    0.75 floor or the 1.01 centre in one copy would have silently desynced
    scoring from calibration.
    """

    def test_crawler_names_forward_to_the_shared_implementation(self) -> None:
        import crawler
        from modules.crawler_scoring import (
            calculate_time_weight,
            time_age_ratio,
            time_weight_from_age_ratio,
        )

        self.assertIs(crawler._calc_time_weight, calculate_time_weight)
        self.assertIs(crawler._time_age_ratio, time_age_ratio)
        self.assertIs(crawler._time_weight_from_age_ratio, time_weight_from_age_ratio)

    def test_default_strength_reproduces_the_original_values(self) -> None:
        from datetime import datetime, timedelta

        from modules.crawler_scoring import calculate_time_weight

        now = datetime(2026, 7, 26, 12, 0, 0)
        for days, expected in ((0, 1.04), (3.5, 1.01), (7, 0.98)):
            with self.subTest(days=days):
                self.assertAlmostEqual(calculate_time_weight(now - timedelta(days=days), now), expected, places=6)
        self.assertEqual(calculate_time_weight(None, now), 1.0)

    def test_the_floor_holds_at_aggressive_strengths(self) -> None:
        from datetime import datetime, timedelta

        from modules.crawler_scoring import calculate_time_weight

        now = datetime(2026, 7, 26, 12, 0, 0)
        self.assertEqual(calculate_time_weight(now - timedelta(days=7), now, strength=1.2), 0.75)
