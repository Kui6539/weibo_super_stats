from __future__ import annotations

import json
import unittest
from pathlib import Path

from modules.images.collect import collect_all_images, collect_comment_images, collect_post_images


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class ImagesCollectTests(unittest.TestCase):
    def test_collects_post_and_comment_images(self) -> None:
        posts = json.loads((FIXTURE_DIR / "sample_selected_posts.json").read_text(encoding="utf-8"))
        post = posts[0]
        self.assertEqual(len(collect_post_images(post)), 1)
        self.assertEqual(len(collect_comment_images(post)), 1)
        all_images = collect_all_images(posts)
        self.assertEqual(len(all_images), 2)
        self.assertEqual(all_images[0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
