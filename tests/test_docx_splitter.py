from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from export.docx_splitter import build_docx_filename, cleanup_old_generated_docx, split_posts_for_docx


class DocxSplitterTests(unittest.TestCase):
    def test_filename_and_cleanup(self) -> None:
        self.assertEqual(build_docx_filename(2), "weekly_report_02.docx")
        self.assertEqual(len(split_posts_for_docx([{"post_id": "1"}])), 1)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            generated = run_dir / "weekly_report_01.docx"
            manual = run_dir / "manual.docx"
            generated.write_bytes(b"x")
            manual.write_bytes(b"x")
            cleanup_old_generated_docx(run_dir)
            self.assertFalse(generated.exists())
            self.assertTrue(manual.exists())


if __name__ == "__main__":
    unittest.main()
