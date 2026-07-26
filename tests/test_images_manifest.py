"""Tests the images manifest the production run actually writes.

These used to exercise a second implementation in modules/images/manifest.py
that took ``{"ok": ...}`` rows and persisted them under the legacy
``run_dir/cache/`` path. Nothing in production called it, so the coverage was
an illusion -- the real builder lived in core/job.py and was untested. Both are
now the same function and this file tests it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.images.manifest import build_images_manifest


def write_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"jpg")
    return path


class ImagesManifestTests(unittest.TestCase):
    def test_downloaded_images_are_recorded_with_run_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            image = write_file(run_dir / "images" / "post1" / "a.jpg")
            posts = [
                {
                    "post_id": "1",
                    "original_image_urls": "https://example.com/a.jpg",
                    "image_local_paths": str(image),
                }
            ]

            manifest = build_images_manifest(run_dir, posts)

            self.assertEqual(manifest["success_count"], 1)
            self.assertEqual(manifest["failed_count"], 0)
            row = manifest["success"][0]
            self.assertEqual(row["post_id"], "1")
            self.assertEqual(row["type"], "post_image")
            self.assertEqual(row["url"], "https://example.com/a.jpg")
            self.assertEqual(row["local_path"], "images/post1/a.jpg")

    def test_a_path_that_never_landed_counts_as_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            posts = [
                {
                    "post_id": "1",
                    "original_image_urls": "https://example.com/a.jpg",
                    "image_local_paths": str(run_dir / "images" / "missing.jpg"),
                }
            ]

            manifest = build_images_manifest(run_dir, posts)

            self.assertEqual(manifest["success_count"], 0)
            self.assertEqual(manifest["failed_count"], 1)

    def test_urls_with_no_path_at_all_are_reported_as_failures(self) -> None:
        """Downloads that never produced a file leave more URLs than paths."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            image = write_file(run_dir / "images" / "a.jpg")
            posts = [
                {
                    "post_id": "1",
                    "original_image_urls": "https://example.com/a.jpg|https://example.com/b.jpg",
                    "image_local_paths": str(image),
                }
            ]

            manifest = build_images_manifest(run_dir, posts)

            self.assertEqual(manifest["success_count"], 1)
            self.assertEqual(manifest["failed_count"], 1)
            self.assertEqual(manifest["failed"][0]["url"], "https://example.com/b.jpg")
            self.assertEqual(manifest["failed"][0]["local_path"], "")

    def test_comment_images_are_typed_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_image = write_file(run_dir / "images" / "p.jpg")
            comment_image = write_file(run_dir / "images" / "c.jpg")
            posts = [
                {
                    "post_id": "1",
                    "original_image_urls": "https://example.com/p.jpg",
                    "image_local_paths": str(post_image),
                    "top_comments_data": [
                        {
                            "image_urls": "https://example.com/c.jpg",
                            "image_local_paths": str(comment_image),
                        }
                    ],
                }
            ]

            manifest = build_images_manifest(run_dir, posts)

            types = sorted(row["type"] for row in manifest["success"])
            self.assertEqual(types, ["comment_image", "post_image"])

    def test_a_path_outside_the_run_directory_is_kept_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            run_dir = Path(tmp)
            outside = write_file(Path(other) / "x.jpg")
            posts = [{"post_id": "1", "original_image_urls": "u", "image_local_paths": str(outside)}]

            manifest = build_images_manifest(run_dir, posts)

            self.assertEqual(manifest["success"][0]["local_path"], str(outside).replace("\\", "/"))

    def test_a_run_with_no_images_produces_an_empty_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_images_manifest(Path(tmp), [{"post_id": "1"}])
            self.assertEqual(manifest["success"], [])
            self.assertEqual(manifest["failed"], [])
            self.assertEqual(manifest["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
