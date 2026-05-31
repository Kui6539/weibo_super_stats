from __future__ import annotations

import unittest
from datetime import datetime

from core.crawl_types import CrawlConfig
from crawler import WeiboSuperTopicCrawler
from modules.weibo_chaohua_api import next_chaohua_params, parse_chaohua_posts_from_json


class FakeResponse:
    def __init__(self, text: str = "", json_data: dict | None = None, status_code: int = 200) -> None:
        self.text = text
        self._json_data = json_data
        self.status_code = status_code
        self.url = "https://weibo.com/fake"

    def json(self) -> dict:
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class FakeSession:
    def __init__(self, api_payload: dict | list[dict]) -> None:
        self.headers: dict[str, str] = {}
        self.api_payloads = api_payload if isinstance(api_payload, list) else [api_payload]
        self.api_index = 0
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        if "ajax_proxy/chaohua/page" in url:
            payload = self.api_payloads[min(self.api_index, len(self.api_payloads) - 1)]
            self.api_index += 1
            return FakeResponse(json_data=payload)
        return FakeResponse("<!doctype html><html><title>Weibo</title><div id='app'></div></html>")


class NoopCrawler(WeiboSuperTopicCrawler):
    def hydrate_full_text_posts(self, posts, max_workers=1):
        return None

    def enrich_score_fields(self, posts, config):
        return None

    def _recalibrate_time_weight(self, posts, config):
        return None

    def _ensure_candidate_comment_analysis(self, posts, config):
        return False


def chaohua_payload() -> dict:
    return {
        "header": {"data": {"nick": "warma"}},
        "items": [
            {
                "category": "feed",
                "data": {
                    "mid": "5302250743532814",
                    "idstr": "5302250743532814",
                    "mblogid": "R0WyeeP2S",
                    "created_at": "Mon May 25 00:02:31 +0800 2026",
                    "text": "hello from chaohua",
                    "reposts_count": 1,
                    "comments_count": 2,
                    "attitudes_count": 3,
                    "pic_infos": {
                        "abc": {
                            "large": {"url": "https://wx1.sinaimg.cn/large/abc.jpg"},
                        }
                    },
                    "user": {"id": 10001, "screen_name": "tester"},
                },
            }
        ],
        "moreInfo": {"params": {"since_id": '{"max_id":1}', "count": 15}},
    }


def chaohua_payload_for_statuses(statuses: list[dict], has_more: bool = True) -> dict:
    payload = {
        "header": {"data": {"nick": "warma"}},
        "items": [{"category": "feed", "data": status} for status in statuses],
    }
    if has_more:
        payload["moreInfo"] = {"params": {"since_id": '{"max_id":1}', "count": 15}}
    return payload


def chaohua_status(post_id: str, created_at: str, text: str = "hello") -> dict:
    return {
        "mid": post_id,
        "idstr": post_id,
        "mblogid": f"R{post_id}",
        "created_at": created_at,
        "text": text,
        "reposts_count": 1,
        "comments_count": 2,
        "attitudes_count": 3,
        "user": {"id": 10001, "screen_name": "tester"},
    }


class ChaohuaApiFallbackTests(unittest.TestCase):
    def test_parse_chaohua_json_posts(self) -> None:
        posts = parse_chaohua_posts_from_json(chaohua_payload())

        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post["post_id"], "5302250743532814")
        self.assertEqual(post["author_id"], "10001")
        self.assertEqual(post["user_name"], "tester")
        self.assertEqual(post["publish_time"], "2026-05-25 00:02")
        self.assertEqual(post["post_url"], "https://weibo.com/10001/R0WyeeP2S")
        self.assertEqual(post["engagement_total"], 6)
        self.assertIn("abc.jpg", post["original_image_urls"])

    def test_next_params_keep_flow_id(self) -> None:
        params = next_chaohua_params("100808abc", chaohua_payload())

        self.assertEqual(params["flowId"], "100808abc")
        self.assertEqual(params["count"], 15)

    def test_crawl_falls_back_to_chaohua_api_when_fm_view_missing(self) -> None:
        crawler = NoopCrawler(cookie="SUB=abc")
        fake_session = FakeSession(chaohua_payload())
        crawler.session = fake_session  # type: ignore[assignment]
        config = CrawlConfig(
            super_topic="https://weibo.com/p/100808abc/super_index",
            cookie="SUB=abc",
            max_pages=1,
            pause_seconds=0,
            window_start=datetime(2026, 5, 24),
            window_end=datetime(2026, 5, 26),
        )

        posts = crawler.crawl(config)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_id"], "5302250743532814")
        self.assertTrue(any("ajax_proxy/chaohua/page" in url for url, _params in fake_session.calls))

    def test_crawl_deduplicates_repeated_pages_without_early_stop(self) -> None:
        payload = chaohua_payload_for_statuses(
            [chaohua_status("5302250743532814", "Mon May 25 00:02:31 +0800 2026")]
        )
        crawler = NoopCrawler(cookie="SUB=abc")
        fake_session = FakeSession([payload])
        crawler.session = fake_session  # type: ignore[assignment]
        config = CrawlConfig(
            super_topic="https://weibo.com/p/100808abc/super_index",
            cookie="SUB=abc",
            max_pages=3,
            pause_seconds=0,
            window_start=datetime(2026, 5, 24),
            window_end=datetime(2026, 5, 26),
        )

        posts = crawler.crawl(config)

        self.assertEqual(len(posts), 1)
        self.assertEqual(fake_session.api_index, 3)

    def test_crawl_stops_after_five_duplicate_window_pages(self) -> None:
        payload = chaohua_payload_for_statuses(
            [chaohua_status("5302250743532814", "Mon May 25 00:02:31 +0800 2026")]
        )
        crawler = NoopCrawler(cookie="SUB=abc")
        fake_session = FakeSession([payload])
        crawler.session = fake_session  # type: ignore[assignment]
        config = CrawlConfig(
            super_topic="https://weibo.com/p/100808abc/super_index",
            cookie="SUB=abc",
            max_pages=80,
            pause_seconds=0,
            window_start=datetime(2026, 5, 24),
            window_end=datetime(2026, 5, 26),
        )

        posts = crawler.crawl(config)

        self.assertEqual(len(posts), 1)
        self.assertEqual(fake_session.api_index, 6)

    def test_crawl_keeps_low_hit_pages_until_max_pages(self) -> None:
        payloads = []
        for page in range(1, 30):
            statuses = [
                chaohua_status(f"{page}001", "Mon May 25 00:02:31 +0800 2026"),
                chaohua_status(f"{page}002", "Mon May 25 00:03:31 +0800 2026"),
            ]
            statuses.extend(
                chaohua_status(f"{page}{index:03d}", "Wed May 27 00:02:31 +0800 2026")
                for index in range(3, 16)
            )
            payloads.append(chaohua_payload_for_statuses(statuses))
        crawler = NoopCrawler(cookie="SUB=abc")
        fake_session = FakeSession(payloads)
        crawler.session = fake_session  # type: ignore[assignment]
        config = CrawlConfig(
            super_topic="https://weibo.com/p/100808abc/super_index",
            cookie="SUB=abc",
            max_pages=12,
            pause_seconds=0,
            window_start=datetime(2026, 5, 24),
            window_end=datetime(2026, 5, 26),
        )

        posts = crawler.crawl(config)

        self.assertEqual(fake_session.api_index, 12)
        self.assertEqual(len(posts), 24)

    def test_crawl_stops_after_five_pages_without_window_hits(self) -> None:
        payloads = [chaohua_payload_for_statuses([chaohua_status("1001", "Mon May 25 00:02:31 +0800 2026")])]
        for page in range(2, 7):
            payloads.append(
                chaohua_payload_for_statuses(
                    [chaohua_status(f"{page}{index:03d}", "Mon May 18 00:02:31 +0800 2026") for index in range(15)]
                )
            )
        crawler = NoopCrawler(cookie="SUB=abc")
        fake_session = FakeSession(payloads)
        crawler.session = fake_session  # type: ignore[assignment]
        config = CrawlConfig(
            super_topic="https://weibo.com/p/100808abc/super_index",
            cookie="SUB=abc",
            max_pages=80,
            pause_seconds=0,
            window_start=datetime(2026, 5, 24),
            window_end=datetime(2026, 5, 26),
        )

        posts = crawler.crawl(config)

        self.assertEqual(fake_session.api_index, 6)
        self.assertEqual(len(posts), 1)


if __name__ == "__main__":
    unittest.main()
