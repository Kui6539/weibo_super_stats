from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def build_comment_leaderboards(posts: Iterable[dict[str, Any]], top_n: int = 3) -> dict[str, Any]:
    rows = list(posts)
    return {
        "comment_count_top3": build_comment_count_ranking(rows, top_n=top_n),
        "comment_quality_top3": build_comment_quality_ranking(rows, top_n=top_n),
        "all_stats": _all_user_stats(rows),
    }


def build_comment_count_ranking(posts: Iterable[dict[str, Any]], top_n: int = 3) -> list[dict[str, Any]]:
    stats = _collect_user_stats(posts)
    sorted_rows = sorted(
        stats.values(),
        key=lambda item: (
            int(item["comment_count"]),
            int(item.get("commented_post_count", 0)),
            int(item["comment_likes_total"]),
            int(item["hot_top3_count"]),
            str(item["user_name"]),
        ),
        reverse=True,
    )
    return _with_rank(sorted_rows, top_n)


def build_comment_quality_ranking(posts: Iterable[dict[str, Any]], top_n: int = 3) -> list[dict[str, Any]]:
    stats = _collect_user_stats(posts)
    sorted_rows = sorted(
        stats.values(),
        key=lambda item: (
            float(item["quality_score"]),
            int(item["comment_likes_total"]),
            int(item["hot_top3_count"]),
            int(item["comment_count"]),
            str(item["user_name"]),
        ),
        reverse=True,
    )
    return _with_rank(sorted_rows, top_n)


def calculate_comment_quality_score(user_comment_stats: dict[str, Any]) -> float:
    like_rate = float(user_comment_stats.get("like_rate") or 0.0)
    hot_rate = float(user_comment_stats.get("hot_rate") or 0.0)
    comment_count = int(user_comment_stats.get("comment_count") or 0)
    stability = min(1.0, float(comment_count) / 8.0)
    return round((0.6 * like_rate + 0.4 * hot_rate) * stability, 4)


def _collect_user_stats(posts: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}

    def ensure_user(name: str) -> dict[str, Any]:
        key = _clean_name(name) or "匿名用户"
        if key not in stats:
            stats[key] = {
                "user_name": key,
                "comment_count": 0,
                "commented_post_count": 0,
                "comment_likes_total": 0,
                "hot_top3_count": 0,
                "like_rate": 0.0,
                "hot_rate": 0.0,
                "quality_score": 0.0,
                "_commented_post_ids": set(),
            }
        return stats[key]

    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = _clean_name(str(post.get("post_id", "") or ""))
        post_key = post_id or f"{_clean_name(str(post.get('post_url', '') or ''))}|{_clean_name(str(post.get('publish_time', '') or ''))}"
        for comment in list(post.get("all_comments_data") or []):
            if not isinstance(comment, dict):
                continue
            item = ensure_user(str(comment.get("user_name", "") or "匿名用户"))
            item["comment_count"] += 1
            item["comment_likes_total"] += int(comment.get("like_counts", 0) or 0)
            item["_commented_post_ids"].add(post_key)

        for comment in list(post.get("top_comments_data") or [])[:3]:
            if not isinstance(comment, dict):
                continue
            item = ensure_user(str(comment.get("user_name", "") or "匿名用户"))
            item["hot_top3_count"] += 1

    if not stats:
        return {}

    max_like_rate = 0.0
    max_hot_rate = 0.0
    for item in stats.values():
        count = max(1, int(item["comment_count"]))
        item["like_rate"] = float(item["comment_likes_total"]) / count
        item["hot_rate"] = float(item["hot_top3_count"]) / count
        item["commented_post_count"] = len(item.get("_commented_post_ids", set()))
        max_like_rate = max(max_like_rate, float(item["like_rate"]))
        max_hot_rate = max(max_hot_rate, float(item["hot_rate"]))

    for item in stats.values():
        normalized = {
            **item,
            "like_rate": (float(item["like_rate"]) / max_like_rate) if max_like_rate > 0 else 0.0,
            "hot_rate": (float(item["hot_rate"]) / max_hot_rate) if max_hot_rate > 0 else 0.0,
        }
        item["quality_score"] = calculate_comment_quality_score(normalized)

    return stats


def _all_user_stats(posts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_strip_internal(item) for item in _collect_user_stats(posts).values()]


def _with_rank(rows: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    result = []
    for idx, item in enumerate(rows[: max(1, top_n)], start=1):
        copied = _strip_internal(item)
        copied["rank"] = idx
        result.append(copied)
    return result


def _strip_internal(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    copied.pop("_commented_post_ids", None)
    return copied


def _clean_name(name: str) -> str:
    return " ".join(str(name or "").split())
