from __future__ import annotations

import json
import unittest

from core.cache import CacheStore, sanitize_for_cache
from export.manifest import build_manifest
from modules.cookie_parser import mask_cookie_for_log
from tests.helpers import assert_no_sensitive_fields, make_temp_run_dir
from export.context import ExportContext


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
