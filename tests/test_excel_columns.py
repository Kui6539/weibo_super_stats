from __future__ import annotations

import unittest

from export.excel_columns import EXCEL_COLUMNS, build_excel_rows, format_cell_value


class ExcelColumnsTests(unittest.TestCase):
    def test_build_excel_rows_uses_chinese_headers(self) -> None:
        rows = build_excel_rows([{"user_name": "作者", "content": "正文"}], EXCEL_COLUMNS)
        self.assertEqual(rows[0]["作者昵称"], "作者")
        self.assertEqual(rows[0]["帖子内容"], "正文")

    def test_format_cell_value(self) -> None:
        self.assertEqual(format_cell_value(None), "")
        self.assertEqual(format_cell_value(1), 1)


if __name__ == "__main__":
    unittest.main()
