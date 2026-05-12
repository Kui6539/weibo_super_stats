from __future__ import annotations

import unittest

from modules.comments.parser import extract_author_replies, extract_comment_items, extract_hot_comments, parse_comment_response


class CommentsParserTests(unittest.TestCase):
    def test_parse_comment_response_extracts_common_fields(self) -> None:
        data = {
            "data": [
                {
                    "id": "1",
                    "text_raw": "评论",
                    "like_counts": 3,
                    "user": {"id": "u1", "screen_name": "用户A"},
                    "comments": [{"id": "2", "text": "回复", "user": {"id": "u2", "screen_name": "用户B"}}],
                }
            ],
            "hot_data": [{"id": "3", "text": "热评", "user": {"id": "u3", "screen_name": "用户C"}}],
            "max_id": 10,
        }
        parsed = parse_comment_response(data)
        self.assertEqual(parsed["max_id"], 10)
        self.assertEqual(parsed["comments"][0]["user_name"], "用户A")
        self.assertEqual(parsed["comments"][0]["comments"][0]["user_name"], "用户B")
        self.assertEqual(parsed["hot_comments"][0]["text"], "热评")

    def test_extract_helpers_tolerate_empty_input(self) -> None:
        self.assertEqual(extract_comment_items(None), [])
        self.assertEqual(extract_hot_comments({}), [])
        self.assertEqual(extract_author_replies({}), [])


if __name__ == "__main__":
    unittest.main()
