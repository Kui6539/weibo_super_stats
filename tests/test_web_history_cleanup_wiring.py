from __future__ import annotations

import unittest
from pathlib import Path


class WebHistoryCleanupWiringTests(unittest.TestCase):
    def test_main_passes_history_and_cleanup_controllers_to_events(self) -> None:
        main_js = Path("web/js/main.js").read_text(encoding="utf-8")
        bind_block = main_js.split("window.WeiboEvents.bind({", 1)[1].split("});", 1)[0]
        self.assertIn("historyController", bind_block)
        self.assertIn("outputCleanupController", bind_block)
        self.assertIn("presetController", bind_block)

    def test_history_and_cleanup_scripts_keep_readable_labels(self) -> None:
        history_js = Path("web/js/history.js").read_text(encoding="utf-8")
        cleanup_js = Path("web/js/output_cleanup.js").read_text(encoding="utf-8")
        self.assertIn("扫描完成", history_js)
        self.assertIn("重新生成完成", history_js)
        self.assertIn("预览中", cleanup_js)
        self.assertIn("确认删除", cleanup_js)

    def test_history_dropdown_is_wired_from_topbar(self) -> None:
        index_html = Path("web/index.html").read_text(encoding="utf-8")
        main_js = Path("web/js/main.js").read_text(encoding="utf-8")
        events_js = Path("web/js/events.js").read_text(encoding="utf-8")
        history_js = Path("web/js/history.js").read_text(encoding="utf-8")
        self.assertIn('id="historyTopbar"', index_html)
        self.assertIn('id="historySearch"', index_html)
        self.assertIn("搜索历史任务，点击展开", index_html)
        self.assertIn('id="historyDropdown"', index_html)
        self.assertNotIn('id="historyPanel"', index_html)
        self.assertIn("historySearch", main_js)
        self.assertIn("openDropdown", events_js)
        self.assertIn("handleDocumentClick", history_js)


if __name__ == "__main__":
    unittest.main()
