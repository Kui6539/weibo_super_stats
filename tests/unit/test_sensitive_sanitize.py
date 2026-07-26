from __future__ import annotations

import json
import unittest

from core.cache import CacheStore, sanitize_for_cache
from export.context import ExportContext
from export.manifest import build_manifest
from modules.cookie_parser import mask_cookie_for_log
from tests.helpers import assert_no_sensitive_fields, make_temp_run_dir


class SensitiveSanitizeTests(unittest.TestCase):
    def test_sanitize_for_cache_removes_nested_sensitive_keys(self) -> None:
        data = {
            "cookie": "SUB=very_secret",
            "normal_text": "正文里出现 token 这个词不应被删除",
            "nested": {
                "Authorization": "Bearer abc",
                "items": [{"refresh_token": "abc"}, {"content": "普通正文"}],
            },
        }
        clean = sanitize_for_cache(data)
        assert_no_sensitive_fields(self, clean)
        self.assertEqual(clean["normal_text"], "正文里出现 token 这个词不应被删除")
        self.assertEqual(clean["nested"]["items"][1]["content"], "普通正文")
        self.assertNotIn("very_secret", json.dumps(clean, ensure_ascii=False))

    def test_run_config_write_filters_sensitive_fields(self) -> None:
        with make_temp_run_dir() as run_dir:
            store = CacheStore(run_dir)
            path = store.write_stage("run_config", {"cookie": "SUB=secret", "super_topic": "100808abc"})
            data = json.loads(path.read_text(encoding="utf-8"))
            assert_no_sensitive_fields(self, data)
            self.assertEqual(data["super_topic"], "100808abc")

    def test_manifest_filters_sensitive_config(self) -> None:
        with make_temp_run_dir() as run_dir:
            ctx = ExportContext(
                run_dir=run_dir,
                selected_posts=[],
                all_posts=[],
                config={"cookie": "SUB=secret", "session": "abc", "super_topic": "100808abc"},
                stats={},
            )
            manifest = build_manifest(ctx, {"markdown": run_dir / "weekly_report.md"})
            assert_no_sensitive_fields(self, manifest)
            self.assertNotIn("SUB=secret", json.dumps(manifest, ensure_ascii=False))

    def test_cookie_masking_does_not_expose_full_value(self) -> None:
        masked = mask_cookie_for_log("SUB=abcdefghijklmnopqrstuvwxyz; SCF=123456789")
        self.assertIn("SUB=abc...xyz", masked)
        self.assertIn("SCF=123...789", masked)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", masked)
        self.assertNotIn("123456789", masked)


if __name__ == "__main__":
    unittest.main()


class CookieValueRedactionTests(unittest.TestCase):
    """Values, not just keys.

    sanitize_event_payload only filtered by key name, so a credential embedded
    in free text -- an exception carrying a request header, most likely --
    reached /api/status untouched, and the front end can save those logs to a
    file. mask_cookie_for_log existed for this but had no production caller.
    """

    def test_login_cookie_values_are_stripped_from_free_text(self) -> None:
        from core.events import redact_cookie_values

        text = "请求失败: Cookie: SUB=_2A25Lsecret; SUBP=0033WrSXsecret; other=keep"
        cleaned = redact_cookie_values(text)

        self.assertNotIn("_2A25Lsecret", cleaned)
        self.assertNotIn("0033WrSXsecret", cleaned)
        self.assertIn("SUB=***", cleaned)
        self.assertIn("other=keep", cleaned, "only credentials are redacted")

    def test_redaction_is_case_insensitive(self) -> None:
        from core.events import redact_cookie_values

        self.assertNotIn("secret", redact_cookie_values("sub=secret-value"))

    def test_ordinary_text_is_untouched(self) -> None:
        from core.events import redact_cookie_values

        for text in ("抓取第 12 页...", "", "subscribe=yes"):
            with self.subTest(text=text):
                self.assertEqual(redact_cookie_values(text), text)

    def test_a_cookie_hidden_in_a_payload_value_is_redacted(self) -> None:
        from core.events import sanitize_event_payload

        cleaned = sanitize_event_payload({"message": "headers: SUB=leaked-token", "count": 3})
        self.assertNotIn("leaked-token", cleaned["message"])
        self.assertEqual(cleaned["count"], 3)

    def test_job_logs_never_carry_a_credential(self) -> None:
        from datetime import datetime
        from pathlib import Path

        from core.crawl_types import CrawlConfig
        from core.job import CrawlJob

        job = CrawlJob(
            CrawlConfig(
                super_topic="https://weibo.com/p/100808abc/super_index",
                cookie="SUB=real-token",
                max_pages=10,
                window_start=datetime(2026, 6, 1),
                window_end=datetime(2026, 6, 8),
            ),
            Path("output"),
        )
        job.add_log("自动读取失败: Cookie: SUB=leaked-token; SUBP=also-leaked")

        dumped = json.dumps(job.snapshot(), ensure_ascii=False, default=str)
        self.assertNotIn("leaked-token", dumped)
        self.assertNotIn("also-leaked", dumped)
