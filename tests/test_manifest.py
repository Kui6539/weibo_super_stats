from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from export.context import ExportContext
from export.manifest import build_manifest, write_manifest


class ManifestTests(unittest.TestCase):
    def test_manifest_contains_expected_file_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            md = run_dir / "report.md"
            md.write_text("# report", encoding="utf-8")
            ctx = ExportContext(run_dir=run_dir, selected_posts=[], all_posts=[], config={}, stats={})
            manifest = build_manifest(
                ctx,
                {
                    "markdown": md,
                    "docx": [run_dir / "a.docx"],
                    "docx_sum": run_dir / "sum.docx",
                    "xlsx": run_dir / "a.xlsx",
                    "csv": run_dir / "a.csv",
                    "summary": run_dir / "summary.txt",
                    "images": run_dir / "images",
                },
            )
            self.assertIn("markdown", manifest["files"])
            self.assertIn("docx", manifest["files"])
            self.assertIn("xlsx", manifest["files"])
            self.assertIn("csv", manifest["files"])
            self.assertIn("summary", manifest["files"])
            self.assertIn("images", manifest["files"])
            self.assertIn("cache", manifest)
            self.assertEqual(manifest["files"]["markdown"], "report.md")

    def test_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(Path(tmp), {"run_dir": tmp, "files": {}})
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["run_dir"], tmp)

    def test_reexport_manifest_fields_and_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            ctx = ExportContext(
                run_dir=run_dir,
                selected_posts=[{"post_id": "1"}],
                all_posts=[{"post_id": "1"}],
                config={"cookie": "secret", "super_topic": "100808abc"},
                stats={"total_posts": 1},
                reexport=True,
            )
            manifest = build_manifest(ctx, {"markdown": run_dir / "report.md"}, previous={"reexport_count": 2})
            self.assertEqual(manifest["reexport_count"], 3)
            self.assertIsNotNone(manifest["last_reexport_at"])
            self.assertNotIn("cookie", str(manifest).lower())


if __name__ == "__main__":
    unittest.main()
