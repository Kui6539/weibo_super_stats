from __future__ import annotations

import unittest

from core.recovery import build_recovery_suggestions, classify_error, recovery_suggestions_for_status


class RecoveryTests(unittest.TestCase):
    def test_cookie_error_suggestion(self) -> None:
        self.assertEqual(classify_error("Cookie 失效"), "cookie")
        suggestions = build_recovery_suggestions("Cookie 失效")
        self.assertTrue(any("Cookie" in item["title"] for item in suggestions))

    def test_visitor_network_file_and_cache_suggestions(self) -> None:
        self.assertEqual(classify_error("微博返回访客验证页面"), "visitor")
        self.assertEqual(classify_error("timeout 网络超时"), "network")
        self.assertEqual(classify_error("Word 文件被占用 PermissionError"), "file_locked")
        self.assertEqual(classify_error("cache 缓存缺失"), "cache")

    def test_status_suggestions(self) -> None:
        failed = recovery_suggestions_for_status({"status": "failed", "error": "Excel 文件被占用"})
        self.assertTrue(failed)
        cancelled = recovery_suggestions_for_status({"status": "cancelled"})
        self.assertEqual(cancelled[0]["title"], "任务已取消")


if __name__ == "__main__":
    unittest.main()
