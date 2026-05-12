from __future__ import annotations

import unittest

from modules.comments.analyzer import analyze_post_comments, build_comment_summary, count_author_replies, count_non_author_comments


class CommentsAnalyzerTests(unittest.TestCase):
    def test_counts_author_and_non_author_comments(self) -> None:
        comments = [
            {"id": "1", "user_id": "u1", "user_name": "作者", "text": "楼主回复", "like_counts": 1},
            {"id": "2", "user_id": "u2", "user_name": "读者", "text": "普通评论", "like_counts": 5},
        ]
        self.assertEqual(count_author_replies(comments, author_id="u1", author_name="作者"), 1)
        self.assertEqual(count_non_author_comments(comments, author_id="u1", author_name="作者"), 1)

    def test_analyze_post_comments_builds_summary(self) -> None:
        post = {"user_id": "u1", "user_name": "作者"}
        data = {"data": [{"id": "1", "text": "A", "like_counts": 2, "user": {"id": "u2", "screen_name": "读者"}}]}
        result = analyze_post_comments(post, data)
        self.assertEqual(result["author_replies"], 0)
        self.assertEqual(result["non_author_comments"], 1)
        self.assertEqual(result["top_comments"][0]["like_counts"], 2)

    def test_empty_summary(self) -> None:
        self.assertEqual(build_comment_summary([])["comment_count"], 0)


if __name__ == "__main__":
    unittest.main()
