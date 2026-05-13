from __future__ import annotations

import json
import unittest

from modules.crawler_client import WeiboClient


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, url: str = "https://weibo.com/p/100808abc/super_index") -> None:
        self.text = text
        self.status_code = status_code
        self.url = url


class SequenceSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.headers: dict[str, str] = {}

    def request(self, *_args, **_kwargs):
        return self.responses.pop(0)


def super_page(post_count: int, interactions: int = 1) -> str:
    items = []
    for idx in range(post_count):
        items.append(
            f"""
            <div action-type="feed_list_item" mid="post{idx}" tbinfo="ouid=10001">
              <a node-type="feed_list_item_name" usercard="id=10001">测试用户</a>
              <a node-type="feed_list_item_date" href="//weibo.com/10001/post{idx}" title="2026-05-10 12:00">5月10日</a>
              <div node-type="feed_list_content">测试正文 {idx}</div>
              <div class="WB_feed_handle">
                <a action-type="feed_list_forward">转发 {interactions}</a>
                <a action-type="feed_list_comment">评论 {interactions}</a>
                <a action-type="feed_list_like">赞 {interactions}</a>
              </div>
            </div>
            """
        )
    payload = json.dumps({"domid": "Pl_Core_MixedFeed__1", "html": "\n".join(items)}, ensure_ascii=False)
    return f"<html><script>FM.view({payload})</script></html>"


class CookieThreePageCheckTests(unittest.TestCase):
    def make_client(self, responses: list[FakeResponse]) -> WeiboClient:
        client = WeiboClient(cookie="SUB=abc; SCF=def", retry=0)
        client.session = SequenceSession(responses)  # type: ignore[assignment]
        return client

    def test_passes_when_any_of_three_pages_has_posts(self) -> None:
        client = self.make_client([FakeResponse(super_page(0)), FakeResponse(super_page(0)), FakeResponse(super_page(2))])

        result = client.check_cookie("100808abc")

        self.assertEqual(result["login_state"], "valid")
        self.assertEqual(result["checked_pages"], 3)
        self.assertEqual(result["parsed_posts"], 2)
        self.assertEqual([item["parsed_posts"] for item in result["page_results"]], [0, 0, 2])
        self.assertEqual([item["valid_posts"] for item in result["page_results"]], [0, 0, 2])

    def test_fails_when_all_three_pages_have_zero_posts(self) -> None:
        client = self.make_client([FakeResponse(super_page(0)), FakeResponse(super_page(0)), FakeResponse(super_page(0))])

        result = client.check_cookie("100808abc")

        self.assertEqual(result["login_state"], "invalid")
        self.assertEqual(result["checked_pages"], 3)
        self.assertEqual(result["parsed_posts"], 0)
        self.assertIn("连续检测 3 页", result["message"])

    def test_fails_when_posts_have_zero_interaction_data(self) -> None:
        client = self.make_client(
            [
                FakeResponse(super_page(2, interactions=0)),
                FakeResponse(super_page(1, interactions=0)),
                FakeResponse(super_page(3, interactions=0)),
            ]
        )

        result = client.check_cookie("100808abc")

        self.assertEqual(result["login_state"], "invalid")
        self.assertEqual(result["parsed_posts"], 0)
        self.assertEqual([item["parsed_posts"] for item in result["page_results"]], [2, 1, 3])
        self.assertEqual([item["valid_posts"] for item in result["page_results"]], [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
