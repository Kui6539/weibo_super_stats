from __future__ import annotations

import unittest

from modules.post_normalizer import ensure_post_fields, normalize_post_dict, serialize_post_for_frontend


class PostNormalizerTests(unittest.TestCase):
    def test_ensure_post_fields(self) -> None:
        post = ensure_post_fields({"post_id": "1", "likes": "2"})
        self.assertEqual(post["likes"], 2)
        self.assertIn("score_detail", post)

    def test_normalize_post_dict(self) -> None:
        post = normalize_post_dict({"content": " a \n b ", "user_name": "  user  "})
        self.assertEqual(post["content"], "a b")
        self.assertEqual(post["user_name"], "user")

    def test_serialize_frontend_keeps_score_detail(self) -> None:
        row = serialize_post_for_frontend(
            {"post_id": "1", "content": "正文", "score": 1.234, "score_detail": {"base_score": 1}},
            index=2,
        )
        self.assertEqual(row["rank"], 3)
        self.assertEqual(row["score_detail"]["base_score"], 1)


if __name__ == "__main__":
    unittest.main()
