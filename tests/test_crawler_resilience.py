"""Network resilience of the crawl layer.

Page fetches used to be single-shot session.get calls, so one transient
ConnectionError on page 40 failed the whole job -- and, before the export-side
fix, took the crawl's cache with it. The throttle covers the phases that
actually generate load (comments, hydration), not just the page loop.
"""

from __future__ import annotations

import time
import unittest

import requests

from core.crawl_types import CrawlError
from core.errors import CookieInvalidError, RateLimitedError, VisitorSystemError
from crawler import WeiboSuperTopicCrawler


class FakeResponse:
    def __init__(self, text: str = "ok", status_code: int = 200, url: str = "https://weibo.com/x") -> None:
        self.text = text
        self.status_code = status_code
        self.url = url


class ScriptedSession:
    """Replays a scripted list of responses/exceptions, one per request."""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.headers: dict[str, str] = {}
        self.call_count = 0

    def request(self, method: str, url: str, **kwargs):
        self.call_count += 1
        item = self.script.pop(0) if self.script else FakeResponse()
        if isinstance(item, Exception):
            raise item
        return item


def make_crawler(script: list) -> WeiboSuperTopicCrawler:
    crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
    crawler.session = ScriptedSession(script)
    return crawler


class CrawlerRetryTests(unittest.TestCase):
    def test_transient_network_error_is_retried(self) -> None:
        crawler = make_crawler([requests.ConnectionError("reset"), FakeResponse("recovered")])
        response = crawler._request("GET", "https://weibo.com/x")
        self.assertEqual(response.text, "recovered")
        self.assertEqual(crawler.session.call_count, 2)

    def test_retries_are_bounded_and_end_in_a_crawl_error(self) -> None:
        crawler = make_crawler([requests.ConnectionError("reset")] * 5)
        with self.assertRaises(CrawlError):
            crawler._request("GET", "https://weibo.com/x", retries=2)
        self.assertEqual(crawler.session.call_count, 3)

    def test_server_errors_are_retried_but_client_errors_are_typed(self) -> None:
        crawler = make_crawler([FakeResponse(status_code=500), FakeResponse("ok")])
        self.assertEqual(crawler._request("GET", "https://weibo.com/x").text, "ok")

        for status, expected in ((401, CookieInvalidError), (403, CookieInvalidError), (429, RateLimitedError)):
            with self.subTest(status=status):
                crawler = make_crawler([FakeResponse(status_code=status)])
                with self.assertRaises(expected):
                    crawler._request("GET", "https://weibo.com/x")

    def test_visitor_page_raises_a_typed_error_so_recovery_advice_is_accurate(self) -> None:
        """Was a hardcoded <title> match that raised an untyped CrawlError."""
        for body in (
            "<title>Sina Visitor System</title>",
            "请完成访问验证",
            "<html>visitor/genvisitor</html>",
        ):
            with self.subTest(body=body):
                crawler = make_crawler([FakeResponse(text=body)])
                with self.assertRaises(VisitorSystemError):
                    crawler._request("GET", "https://weibo.com/x")


class CrawlerThrottleTests(unittest.TestCase):
    def test_requests_respect_the_shared_minimum_interval(self) -> None:
        crawler = make_crawler([FakeResponse() for _ in range(3)])
        crawler._min_request_interval = 0.05
        started = time.monotonic()
        for _ in range(3):
            crawler._request("GET", "https://weibo.com/x")
        # Three requests means two enforced gaps.
        self.assertGreaterEqual(time.monotonic() - started, 0.1)

    def test_zero_interval_does_not_sleep(self) -> None:
        crawler = make_crawler([FakeResponse() for _ in range(5)])
        crawler._min_request_interval = 0
        started = time.monotonic()
        for _ in range(5):
            crawler._request("GET", "https://weibo.com/x")
        self.assertLess(time.monotonic() - started, 0.5)


class CommentFailureReportingTests(unittest.TestCase):
    def test_a_high_comment_failure_rate_is_surfaced_once(self) -> None:
        """Silent degradation was the worst part: the run still "succeeded"."""
        logs: list[str] = []
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x", progress_callback=logs.append)
        for index in range(10):
            crawler._note_comment_attempt()
            crawler._record_comment_failure(f"post{index}", error=ValueError("bad json"))

        warnings = [line for line in logs if line.startswith("警告：")]
        self.assertEqual(len(warnings), 1, "the threshold warning must not repeat per post")
        self.assertIn("评论分析失败", warnings[0])
        self.assertEqual(crawler.comment_failure_summary(), {"attempts": 10, "failures": 10})

    def test_a_few_failures_stay_quiet(self) -> None:
        logs: list[str] = []
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x", progress_callback=logs.append)
        for _ in range(20):
            crawler._note_comment_attempt()
        crawler._record_comment_failure("post1", error=ValueError("bad json"))

        self.assertEqual([line for line in logs if line.startswith("警告：")], [])


class ThreadSessionTests(unittest.TestCase):
    def test_sessions_are_reused_per_thread_not_per_post(self) -> None:
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
        first = crawler._thread_session()
        second = crawler._thread_session()
        self.assertIs(first, second)
        crawler._close_thread_sessions()
        self.assertIsNot(crawler._thread_session(), first)


if __name__ == "__main__":
    unittest.main()
