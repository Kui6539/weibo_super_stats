from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image

from core.cache import CacheStore
from core.job import serialize_candidate
from modules.images.candidate_thumbnails import THUMBNAIL_DIR_NAME, build_candidate_thumbnails


class CandidateThumbnailTests(unittest.TestCase):
    def test_build_candidate_thumbnails_stores_jpegs_in_project_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_dir = base / "output" / "20260602_030303"
            cache_root = base / "cache"
            run_dir.mkdir(parents=True)
            store = CacheStore(run_dir, cache_root=cache_root)
            posts = [
                {
                    "post_id": "1001",
                    "user_name": "作者A",
                    "original_image_urls": "https://img.example.com/a.jpg | https://img.example.com/b.jpg",
                },
                {"post_id": "1002", "original_image_urls": ""},
            ]
            events = []

            summary = build_candidate_thumbnails(
                posts,
                store,
                max_per_post=2,
                max_workers=1,
                fetch_bytes=lambda _url, _headers: _sample_image_bytes(),
                progress_callback=events.append,
            )

            thumbnail_dir = cache_root / run_dir.name / THUMBNAIL_DIR_NAME
            self.assertEqual(summary["success"], 2)
            self.assertEqual(summary["downloaded"], 2)
            self.assertEqual(summary["cache_hits"], 0)
            self.assertTrue(thumbnail_dir.is_dir())
            self.assertEqual(len(list(thumbnail_dir.glob("*.jpg"))), 2)
            self.assertEqual(posts[0]["candidate_thumbnail_count"], 2)
            self.assertEqual(posts[1]["candidate_thumbnail_count"], 0)
            self.assertTrue(posts[0]["candidate_thumbnail_urls"][0].startswith("/api/candidate-thumbnail?"))
            self.assertTrue(any("开始下载预选帖缩略图" in item["message"] for item in events))
            self.assertTrue(any("预选帖缩略图 1/2" in item["message"] for item in events))
            self.assertTrue(any("预选帖缩略图缓存完成" in item["message"] for item in events))

            parsed = urlparse(posts[0]["candidate_thumbnail_urls"][0])
            query = parse_qs(parsed.query)
            self.assertEqual(query["run_id"][0], run_dir.name)
            rel_path = unquote(query["path"][0])
            self.assertTrue(rel_path.startswith(f"{THUMBNAIL_DIR_NAME}/"))
            self.assertTrue((cache_root / run_dir.name / rel_path).exists())

            cache_hit_events = []
            cache_fetch_calls = []
            cached_posts = [{"post_id": "1001", "original_image_urls": posts[0]["original_image_urls"]}]
            cached_summary = build_candidate_thumbnails(
                cached_posts,
                store,
                max_per_post=2,
                max_workers=1,
                fetch_bytes=lambda _url, _headers: cache_fetch_calls.append(_url) or _sample_image_bytes(),
                progress_callback=cache_hit_events.append,
            )
            self.assertEqual(cached_summary["cache_hits"], 2)
            self.assertEqual(cache_fetch_calls, [])
            self.assertTrue(any("缓存命中" in item["message"] for item in cache_hit_events))

    def test_serialize_candidate_uses_cached_thumbnail_urls(self) -> None:
        post = {
            "user_name": "作者",
            "original_image_urls": "https://img.example.com/a.jpg",
            "candidate_thumbnail_urls": ["/api/candidate-thumbnail?run_id=1&path=candidate_thumbnails/a.jpg"],
        }

        row = serialize_candidate(post, 0)

        self.assertEqual(row["image_count"], 1)
        self.assertEqual(row["image_preview_paths"], post["candidate_thumbnail_urls"])


def _sample_image_bytes() -> bytes:
    image = Image.new("RGB", (320, 180), color=(120, 80, 200))
    out = BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


if __name__ == "__main__":
    unittest.main()
