from __future__ import annotations

import json
import unittest
from pathlib import Path

from modules.comments.ranking import build_comment_count_ranking, build_comment_leaderboards, build_comment_quality_ranking


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class CommentsRankingTests(unittest.TestCase):
    def test_build_comment_rankings_from_fixture(self) -> None:
        posts = json.loads((FIXTURE_DIR / "sample_posts_scored.json").read_text(encoding="utf-8"))
        count_rows = build_comment_count_ranking(posts)
        quality_rows = build_comment_quality_ranking(posts)
        self.assertEqual(count_rows[0]["user_name"], "评论者A")
        self.assertGreaterEqual(quality_rows[0]["quality_score"], 0)
        boards = build_comment_leaderboards(posts)
        self.assertIn("comment_count_top3", boards)
        self.assertIn("comment_quality_top3", boards)

    def test_empty_posts(self) -> None:
        self.assertEqual(build_comment_leaderboards([])["comment_count_top3"], [])


if __name__ == "__main__":
    unittest.main()
