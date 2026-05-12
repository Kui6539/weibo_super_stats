from __future__ import annotations

from typing import Any


def parse_comment_response(data: Any) -> dict[str, Any]:
    items = extract_comment_items(data)
    return {
        "comments": items,
        "hot_comments": extract_hot_comments(data),
        "max_id": _get_first(data, "max_id", "max_id_str"),
        "total_number": _get_first(data, "total_number", "total"),
    }


def extract_comment_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = (
            data.get("data")
            or data.get("comments")
            or data.get("root_comments")
            or data.get("list")
            or []
        )
    else:
        rows = []
    return [_normalize_comment(row) for row in rows if isinstance(row, dict)]


def extract_hot_comments(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = data.get("hot_data") or data.get("hot_comments") or data.get("top_comments") or []
    return [_normalize_comment(row) for row in rows if isinstance(row, dict)]


def extract_author_replies(data: Any) -> list[dict[str, Any]]:
    return [row for row in extract_comment_items(data) if bool(row.get("is_author_reply"))]


def _normalize_comment(row: dict[str, Any]) -> dict[str, Any]:
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    user_id = row.get("user_id") or row.get("uid") or user.get("id") or user.get("idstr")
    user_name = row.get("user_name") or row.get("screen_name") or user.get("screen_name") or ""
    text = row.get("text_raw") or row.get("text") or row.get("content") or ""
    replies = row.get("comments") if isinstance(row.get("comments"), list) else []
    return {
        **row,
        "id": str(row.get("id") or row.get("idstr") or ""),
        "user_id": str(user_id or ""),
        "user_name": str(user_name or ""),
        "text": str(text or ""),
        "like_counts": int(row.get("like_counts") or row.get("like_count") or 0),
        "created_at": str(row.get("created_at") or ""),
        "comments": [_normalize_comment(reply) for reply in replies if isinstance(reply, dict)],
    }


def _get_first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return None
