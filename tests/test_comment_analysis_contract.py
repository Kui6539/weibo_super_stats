"""Pins the comment-analysis semantics the production crawl path actually uses.

modules/comments/ was built to own this logic but nothing in production calls
it -- crawler._analyze_comments has its own hand-written implementation, and
the two disagree in ways that change published numbers:

    aspect                     crawler (live)          modules/comments
    -------------------------  ----------------------  ---------------------
    author match               user.id only            id OR display name
    replies counted per thread capped at 3             uncapped
    author's top-level comment  not counted            counted
    top_comments tiebreak      likes, then created_at  likes only
    all_comments shape         flat, de-duplicated     nested

author_replies feeds the score through author_reply_weight, so any of the
first three differences would reorder candidates and change which posts make
the weekly report. all_comments is persisted to
cache/<run_id>/comments/post_<id>.json, so its shape is a cache format that
reexport reads back.

These tests describe today's behaviour, not an endorsement of it. Anything
that unifies the two implementations has to keep them passing or make a
deliberate, documented decision to change the numbers.
"""

from __future__ import annotations

import unittest

from crawler import WeiboSuperTopicCrawler

AUTHOR_ID = "author-1"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = "{}"
        self.url = "https://weibo.com/ajax/statuses/buildComments"

    def json(self) -> dict:
        return self._payload


class FakePagedSession:
    """Serves a scripted list of comment API pages."""

    def __init__(self, pages: list[dict]) -> None:
        self.pages = list(pages)
        self.headers: dict[str, str] = {}
        self.requests_made = 0

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requests_made += 1
        page = self.pages.pop(0) if self.pages else {"ok": 1, "data": [], "max_id": "0"}
        return FakeResponse(page)


def comment(cid: str, user_id: str, name: str, likes: int = 0, created: str = "", replies=None) -> dict:
    return {
        "id": cid,
        "user": {"id": user_id, "screen_name": name},
        "like_counts": likes,
        "created_at": created,
        "text_raw": f"comment {cid}",
        "comments": replies or [],
    }


def page(data: list[dict], max_id: str = "0") -> dict:
    return {"ok": 1, "data": data, "max_id": max_id}


def analyze(pages: list[dict], page_limit: int = 5) -> dict:
    crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
    session = FakePagedSession(pages)
    return crawler._analyze_comments(
        post_id="p1", author_id=AUTHOR_ID, page_limit=page_limit, session=session
    )


class AuthorReplyCountingTests(unittest.TestCase):
    def test_only_nested_replies_count_not_top_level_comments(self) -> None:
        """A top-level comment by the author is not an "author reply" here."""
        result = analyze([page([comment("c1", AUTHOR_ID, "作者")])])
        self.assertEqual(result["author_replies"], 0)

    def test_nested_replies_by_the_author_count(self) -> None:
        root = comment("c1", "u2", "路人", replies=[comment("r1", AUTHOR_ID, "作者")])
        result = analyze([page([root])])
        self.assertEqual(result["author_replies"], 1)

    def test_replies_are_capped_at_three_per_thread(self) -> None:
        replies = [comment(f"r{i}", AUTHOR_ID, "作者") for i in range(7)]
        root = comment("c1", "u2", "路人", replies=replies)
        result = analyze([page([root])])
        self.assertEqual(result["author_replies"], 3, "per-thread cap of 3 is load-bearing")

    def test_the_cap_is_per_thread_so_threads_accumulate(self) -> None:
        roots = [
            comment(f"c{t}", "u2", "路人", replies=[comment(f"r{t}{i}", AUTHOR_ID, "作者") for i in range(5)])
            for t in range(2)
        ]
        result = analyze([page(roots)])
        self.assertEqual(result["author_replies"], 6)

    def test_matching_is_by_user_id_only_never_by_display_name(self) -> None:
        """An impostor using the author's display name must not count."""
        root = comment("c1", "u2", "路人", replies=[comment("r1", "impostor", "作者")])
        result = analyze([page([root])])
        self.assertEqual(result["author_replies"], 0)


class CommentCollectionTests(unittest.TestCase):
    def test_roots_and_replies_are_collected_flat_and_deduplicated(self) -> None:
        root = comment("c1", "u2", "路人", replies=[comment("r1", "u3", "另一位")])
        result = analyze([page([root], max_id="2"), page([root])])

        ids = [row.get("user_name") for row in result["all_comments"]]
        self.assertEqual(len(result["all_comments"]), 2, "a repeated comment id must not be collected twice")
        self.assertEqual(sorted(ids), ["另一位", "路人"])
        for row in result["all_comments"]:
            self.assertNotIn("comments", row, "collection is flat, not nested")

    def test_top_comments_rank_by_likes_then_created_at(self) -> None:
        rows = [
            comment("c1", "u1", "甲", likes=5, created="2026-06-01"),
            comment("c2", "u2", "乙", likes=9, created="2026-06-02"),
            comment("c3", "u3", "丙", likes=5, created="2026-06-03"),
            comment("c4", "u4", "丁", likes=1, created="2026-06-04"),
        ]
        result = analyze([page(rows)])
        self.assertEqual([row["user_name"] for row in result["top_comments"]], ["乙", "丙", "甲"])

    def test_text_raw_is_preferred_over_text(self) -> None:
        row = {"id": "c1", "user": {"id": "u1", "screen_name": "甲"}, "text_raw": "原文", "text": "带标签"}
        result = analyze([page([row])])
        self.assertEqual(result["all_comments"][0]["text"], "原文")


class PaginationTests(unittest.TestCase):
    def test_pagination_stops_at_page_limit(self) -> None:
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
        session = FakePagedSession([page([comment(f"c{i}", "u1", "甲")], max_id=str(i + 1)) for i in range(10)])
        crawler._analyze_comments(post_id="p1", author_id=AUTHOR_ID, page_limit=3, session=session)
        self.assertEqual(session.requests_made, 3)

    def test_pagination_stops_when_max_id_is_zero(self) -> None:
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
        session = FakePagedSession([page([comment("c1", "u1", "甲")], max_id="0"), page([])])
        crawler._analyze_comments(post_id="p1", author_id=AUTHOR_ID, page_limit=5, session=session)
        self.assertEqual(session.requests_made, 1)

    def test_pagination_stops_on_an_empty_page(self) -> None:
        crawler = WeiboSuperTopicCrawler(cookie="SUB=x")
        session = FakePagedSession([page([], max_id="5"), page([comment("c1", "u1", "甲")])])
        result = crawler._analyze_comments(post_id="p1", author_id=AUTHOR_ID, page_limit=5, session=session)
        self.assertEqual(session.requests_made, 1)
        self.assertEqual(result["all_comments"], [])


class DivergenceFromModulesCommentsTests(unittest.TestCase):
    """Documents the gap, so unifying the two cannot happen by accident."""

    def test_modules_comments_would_report_a_different_author_reply_count(self) -> None:
        from modules.comments.analyzer import analyze_post_comments

        replies = [comment(f"r{i}", AUTHOR_ID, "作者") for i in range(7)]
        root = comment("c1", "u2", "路人", replies=replies)

        live = analyze([page([root])])["author_replies"]
        alternative = analyze_post_comments(
            {"author_id": AUTHOR_ID, "user_name": "作者"}, {"data": [root]}
        )["author_replies"]

        self.assertEqual(live, 3)
        self.assertEqual(alternative, 7)
        self.assertNotEqual(
            live,
            alternative,
            "these must stay knowingly different until someone decides which is correct",
        )


if __name__ == "__main__":
    unittest.main()
