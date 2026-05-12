from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.images.manifest import build_images_manifest, read_images_manifest, write_images_manifest


class ImagesManifestTests(unittest.TestCase):
    def test_write_and_read_images_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest = build_images_manifest(
                [
                    {"ok": True, "post_id": "1", "local_path": "images/a.jpg"},
                    {"ok": False, "post_id": "2", "url": "https://example.com/b.jpg"},
                ]
            )
            write_images_manifest(run_dir, manifest)
            loaded = read_images_manifest(run_dir)
            self.assertEqual(len(loaded["success"]), 1)
            self.assertEqual(len(loaded["failed"]), 1)


if __name__ == "__main__":
    unittest.main()
