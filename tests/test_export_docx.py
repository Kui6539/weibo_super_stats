from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from docx import Document
except ImportError:  # pragma: no cover
    Document = None

from export.context import ExportContext
from export.docx_exporter import export_docx


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@unittest.skipIf(Document is None, "python-docx 未安装，跳过 DOCX 导出测试")
class ExportDocxTests(unittest.TestCase):
    def test_export_docx_from_context_with_missing_image_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            posts = json.loads((FIXTURE_DIR / "sample_selected_posts.json").read_text(encoding="utf-8"))
            posts[0]["image_local_paths"] = str(run_dir / "missing.jpg")
            ctx = ExportContext(
                run_dir=run_dir,
                selected_posts=posts,
                all_posts=posts,
                config={"report_title": "测试超话周报"},
                stats={},
            )
            paths = export_docx(ctx)
            self.assertTrue(paths)
            self.assertTrue(paths[0].exists())
            self.assertTrue(any("图片缺失" in item for item in ctx.warnings))


if __name__ == "__main__":
    unittest.main()
