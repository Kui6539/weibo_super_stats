from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from export.context import ExportContext
from export.excel_exporter import export_excel


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class ExportExcelTests(unittest.TestCase):
    def test_export_excel_from_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            posts = json.loads((FIXTURE_DIR / "sample_selected_posts.json").read_text(encoding="utf-8"))
            posts[0]["image_local_paths"] = str(run_dir / "missing.jpg")
            ctx = ExportContext(run_dir=run_dir, selected_posts=posts, all_posts=posts, config={}, stats={})
            path = export_excel(ctx)
            self.assertTrue(path.exists())
            workbook = load_workbook(path)
            headers = [cell.value for cell in workbook.active[1]]
            self.assertIn("作者昵称", headers)
            self.assertIn("帖子内容", headers)


if __name__ == "__main__":
    unittest.main()
