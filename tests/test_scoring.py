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
