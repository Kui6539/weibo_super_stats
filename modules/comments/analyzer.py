from __future__ import annotations

from typing import Any

from .parser import extract_comment_items


def analyze_post_comments(post: dict[str, Any], comments_data: Any) -> dict[str, Any]:
    comments = extract_comment_items(comments_data)
    author_id = str(post.get("user_id") or post.get("author_id") or "")
    author_name = str(post.get("user_name") or "")
    rows = _walk_comments(comments)
    author_replies = 0
    non_author_comments = 0
    comment_likes_total = 0
    for row in rows:
        if _is_author(row, author_id, author_name):
            author_replies += 1
        else:
            non_author_comments += 1
        comment_likes_total += int(row.get("like_counts") or 0)
    top_comments = sorted(rows, key=lambda row: int(row.get("like_counts") or 0), reverse=True)[:3]
    return {
        "author_replies": author_replies,
        "non_author_comments": non_author_comments,
        "top_comments": top_comments,
        "all_comments": comments,
        "comment_count": len(rows),
        "comment_likes_total": comment_likes_total,
    }


def count_author_replies(
    comments: list[dict[str, Any]],
    author_id: str | None = None,
    author_name: str | None = None,
) -> int:
    author_id = str(author_id or "")
    author_name = str(author_name or "")
    return sum(1 for row in _walk_comments(comments) if _is_author(row, author_id, author_name))


def count_non_author_comments(
    comments: list[dict[str, Any]],
    author_id: str | None = None,
    author_name: str | None = None,
) -> int:
    author_id = str(author_id or "")
    author_name = str(author_name or "")
    return sum(1 for row in _walk_comments(comments) if not _is_author(row, author_id, author_name))


def build_comment_summary(comments: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _walk_comments(comments)
    top_comments = sorted(rows, key=lambda row: int(row.get("like_counts") or 0), reverse=True)[:3]
    return {
        "comment_count": len(rows),
        "comment_likes_total": sum(int(row.get("like_counts") or 0) for row in rows),
        "top_comments": top_comments,
    }


def _walk_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending = list(reversed(comments))
    while pending:
        comment = pending.pop()
        if not isinstance(comment, dict):
            continue
        rows.append(comment)
        replies = comment.get("comments")
        if isinstance(replies, list):
            pending.extend(reply for reply in reversed(replies) if isinstance(reply, dict))
    return rows


def _is_author(row: dict[str, Any], author_id: str, author_name: str) -> bool:
    user_id = str(row.get("user_id") or "")
    user_name = str(row.get("user_name") or "")
    return bool((author_id and user_id == author_id) or (author_name and user_name == author_name))
