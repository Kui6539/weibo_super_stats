from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.cache import CacheStore
from crawler import export_posts_csv, export_weekly_report_md
from export.reexport import reexport_from_cache


class ReexportTests(unittest.TestCase):
    def test_reexport_from_cache_updates_manifest_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            store = CacheStore(run_dir)
            post = {
                "post_id": "123",
                "user_name": "作者",
                "publish_time": "2026-05-01 12:00",
                "content": "正文",
                "post_url": "https://weibo.com/123",
                "likes": 1,
                "comments": 0,
                "reposts": 0,
                "score": 1.0,
                "top_comments_data": [],
            }
            store.write_stage(
                "run_config",
                {"super_topic": "100808abc", "report_title": "测试超话周报", "cookie": "SHOULD_NOT_WRITE"},
            )
            store.write_stage("posts_scored", [post])
            store.write_stage("selected_posts", [post])
            (run_dir / "warma_weekly_report.md").write_text("old", encoding="utf-8")
            (run_dir / "warma_weekly_report_01.docx").write_bytes(b"old")
            result = reexport_from_cache(run_dir, export_types=["markdown", "csv", "summary"])
            manifest = result["manifest"]
            self.assertEqual(manifest["reexport_count"], 1)
            self.assertIsNotNone(manifest["last_reexport_at"])
            self.assertTrue((run_dir / "weekly_report.md").exists())
            self.assertFalse((run_dir / "warma_weekly_report.md").exists())
            self.assertFalse((run_dir / "warma_weekly_report_01.docx").exists())
            self.assertTrue((run_dir / "weibo_posts.csv").exists())
            self.assertNotIn("cookie", str(manifest).lower())

    def test_reexport_restores_image_paths_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            image_dir = run_dir / "images" / "01_author_123"
            image_dir.mkdir(parents=True)
            post_image = image_dir / "post_01.jpg"
            comment_image = image_dir / "comment1_01.jpg"
            post_image.write_bytes(b"fake")
            comment_image.write_bytes(b"fake")

            post_without_paths = {
                "post_id": "123",
                "user_name": "author",
                "publish_time": "2026-05-01 12:00",
                "content": "content",
                "post_url": "https://weibo.com/123",
                "likes": 1,
                "comments": 1,
                "reposts": 0,
                "score": 1.0,
                "original_image_urls": "https://img.example/post.jpg",
                "image_local_paths": "",
                "top_comments_data": [
                    {
                        "user_name": "commenter",
                        "text": "comment",
                        "image_urls": ["https://img.example/comment.jpg"],
                    }
                ],
            }
            post_with_paths = dict(post_without_paths)
            post_with_paths["image_local_paths"] = str(post_image)
            post_with_paths["comment_image_local_paths"] = str(comment_image)
            post_with_paths["image_local_paths_all"] = f"{post_image} | {comment_image}"
            post_with_paths["top_comments_data"] = [
                {
                    "user_name": "commenter",
                    "text": "comment",
                    "image_urls": "https://img.example/comment.jpg",
                    "image_local_paths": str(comment_image),
                }
            ]

            expected_md = run_dir / "expected.md"
            expected_csv = run_dir / "expected.csv"
            export_weekly_report_md([post_with_paths], expected_md, title="测试超话周报", preselected=True)
            export_posts_csv([post_with_paths], expected_csv)

            store = CacheStore(run_dir)
            store.write_stage("run_config", {"super_topic": "100808abc", "report_title": "测试超话周报"})
            store.write_stage("posts_scored", [post_without_paths])
            store.write_stage("selected_posts", [post_without_paths])
            store.write_stage(
                "images_manifest",
                {
                    "schema_version": 1,
                    "success": [
                        {
                            "post_id": "123",
                            "type": "post_image",
                            "url": "https://img.example/post.jpg",
                            "local_path": "images/01_author_123/post_01.jpg",
                        },
                        {
                            "post_id": "123",
                            "type": "comment_image",
                            "url": "https://img.example/comment.jpg",
                            "local_path": "images/01_author_123/comment1_01.jpg",
                        },
                    ],
                    "failed": [],
                },
            )

            reexport_from_cache(run_dir, export_types=["markdown", "csv"])

            self.assertEqual(
                expected_md.read_text(encoding="utf-8"),
                (run_dir / "weekly_report.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                expected_csv.read_text(encoding="utf-8-sig"),
                (run_dir / "weibo_posts.csv").read_text(encoding="utf-8-sig"),
            )


if __name__ == "__main__":
    unittest.main()
