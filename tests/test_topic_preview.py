from __future__ import annotations

import unittest

from server.handlers import resolve_topic_preview


class TopicPreviewTests(unittest.TestCase):
    def test_topic_preview_resolves_name_and_issue(self) -> None:
        class FakeClient:
            def __init__(self, **_kwargs) -> None:
                pass

            def get_json(self, *_args, **_kwargs):
                return {"header": {"data": {"nick": "原神超话——新浪超话"}}}

        data = resolve_topic_preview(
            {
                "super_topic": "https://weibo.com/p/100808abc/super_index",
                "cookie": "SUB=secret",
                "window_end": "2026-05-30T04:00",
                "issue": "6",
            },
            client_factory=FakeClient,
        )

        self.assertEqual(data["super_topic_id"], "100808abc")
        self.assertEqual(data["topic_name"], "原神")
        self.assertEqual(data["issue"], "6")
        self.assertEqual(data["title_with_issue"], "原神超话周报 第6期")

    def test_topic_preview_rejects_bad_topic_without_network(self) -> None:
        class FailingClient:
            def __init__(self, **_kwargs) -> None:
                raise AssertionError("network should not be used")

        data = resolve_topic_preview({"super_topic": "not-a-topic", "issue": "7"}, client_factory=FailingClient)

        self.assertEqual(data["super_topic_id"], "")
        self.assertEqual(data["issue"], "7")
        self.assertEqual(data["source"], "empty")
        self.assertIn("无法解析", data["message"])


if __name__ == "__main__":
    unittest.main()
