from __future__ import annotations

import unittest

from core.errors import ConfigError, to_error_response
from core.events import clamp_percent, make_event, normalize_stage, sanitize_event_payload


class EventsErrorsTests(unittest.TestCase):
    def test_event_payload_removes_cookie_like_fields(self) -> None:
        event = make_event(
            "progress",
            "crawl",
            "处理中",
            percent=150,
            payload={"cookie": "SUB=secret", "safe": {"value": 1}, "rows": [{"SCF": "secret"}]},
        )
        data = event.to_dict()
        self.assertEqual(data["percent"], 100.0)
        self.assertNotIn("cookie", data["payload"])
        self.assertNotIn("SCF", str(data["payload"]))
        self.assertEqual(data["payload"]["safe"]["value"], 1)

    def test_stage_and_percent_normalization(self) -> None:
        self.assertEqual(normalize_stage("crawl"), "crawl")
        self.assertEqual(normalize_stage("unknown"), "idle")
        self.assertEqual(clamp_percent(-1), 0.0)
        self.assertEqual(clamp_percent(101), 100.0)

    def test_error_response_shape(self) -> None:
        payload = to_error_response(ConfigError("配置读取失败", "请检查配置文件权限"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "CONFIG_ERROR")
        self.assertIn("message", payload["error"])
        self.assertIn("suggestion", payload["error"])

    def test_sanitize_event_payload_direct_call(self) -> None:
        clean = sanitize_event_payload({"SUB": "secret", "ok": [{"cookie": "x", "name": "row"}]})
        self.assertNotIn("SUB", clean)
        self.assertEqual(clean["ok"][0]["name"], "row")
        self.assertNotIn("cookie", clean["ok"][0])


if __name__ == "__main__":
    unittest.main()
