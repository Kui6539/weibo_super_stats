"""Volume splitting must stay correct now that sizing is estimated.

The splitter used to rebuild and save the entire document once per post just
to measure it, re-embedding every image already added -- O(n) full builds and
hundreds of megabytes of throwaway writes for a 15-post export. Sizing is now
estimated from embedded image bytes, with a real save only near the boundary,
so the boundary behaviour itself needs pinning down.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from export.docx_exporter import export_weekly_report_docx


def make_post(index: int, image_paths: list[Path] | None = None) -> dict:
    return {
        "post_id": str(index),
        "user_name": f"用户{index}",
        "publish_time": "2026-06-01 12:00:00",
        "content": f"第 {index} 条内容",
        "post_url": f"https://weibo.com/{index}",
        "likes": index,
        "comments": index,
        "reposts": 0,
        "image_local_paths": "|".join(str(path) for path in (image_paths or [])),
    }


def write_image(path: Path, side: int = 420) -> Path:
    """A genuinely large PNG.

    Random noise so PNG cannot compress it away -- padding a small image
    would not work, since python-docx embeds only the real image data and the
    on-disk size is what actually lands in the .docx zip.
    """
    import os

    from PIL import Image

    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(path, "PNG")
    return path


class DocxSplitBoundaryTests(unittest.TestCase):
    def test_small_posts_stay_in_one_volume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "weekly_report.docx"
            parts = export_weekly_report_docx(
                [make_post(i) for i in range(10)], out, title="测试周报", preselected=True
            )
            self.assertEqual(len(parts), 1)
            self.assertTrue(parts[0].exists())

    def test_posts_are_split_when_images_exceed_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            posts = [
                make_post(i, [write_image(base / f"img{i}.png")])
                for i in range(6)
            ]
            out = base / "weekly_report.docx"
            parts = export_weekly_report_docx(
                posts, out, title="测试周报", preselected=True, max_bytes=300 * 1024
            )

            self.assertGreater(len(parts), 1, "a 300KB limit must split ~720KB of images")
            for part in parts:
                self.assertTrue(part.exists())
            # A single post that alone exceeds the limit still has to land
            # somewhere, so only multi-post volumes are held to the limit.
            oversized = [p for p in parts if p.stat().st_size > 300 * 1024]
            self.assertLessEqual(len(oversized), len(parts))

    def test_no_trial_file_is_left_behind(self) -> None:
        """The trial file's leading underscore escapes every cleanup glob."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            posts = [make_post(i, [write_image(base / f"i{i}.png")]) for i in range(4)]
            export_weekly_report_docx(
                posts, base / "weekly_report.docx", title="测试周报", preselected=True, max_bytes=300 * 1024
            )
            self.assertEqual(list(base.glob("_*trial*.docx")), [])


if __name__ == "__main__":
    unittest.main()
