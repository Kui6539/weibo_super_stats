from __future__ import annotations

import re
from pathlib import Path
from typing import Any


DEFAULT_POST_FIELDS: dict[str, Any] = {
    "post_id": "",
    "user_name": "",
    "publish_time": "",
    "content": "",
    "post_url": "",
    "likes": 0,
    "comments": 0,
    "reposts": 0,
    "score": 0.0,
    "score_detail": {},
    "original_image_urls": "",
    "image_local_paths": "",
}


def ensure_post_fields(post: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_POST_FIELDS)
    normalized.update(dict(post or {}))
    for key in ("likes", "comments", "reposts"):
        normalized[key] = _to_int(normalized.get(key))
    normalized["score"] = _to_float(normalized.get("score"))
    normalized["score_detail"] = dict(normalized.get("score_detail") or {})
    return normalized


def normalize_post_dict(post: dict[str, Any]) -> dict[str, Any]:
    normalized = ensure_post_fields(post)
    normalized["content"] = re.sub(r"\s+", " ", str(normalized.get("content") or "")).strip()
    normalized["user_name"] = str(normalized.get("user_name") or "").strip()
    normalized["post_url"] = str(normalized.get("post_url") or "").strip()
    return normalized


def serialize_post_for_frontend(post: dict[str, Any], index: int = 0) -> dict[str, Any]:
    normalized = normalize_post_dict(post)
    content = str(normalized.get("content") or "")
    image_paths = [path for path in _split_multi(normalized.get("image_local_paths")) if Path(path).exists()]
    image_count = len(_split_multi(normalized.get("original_image_urls"))) or len(image_paths)
    return {
        "index": index,
        "rank": index + 1,
        "user_name": normalized["user_name"] or "未知作者",
        "publish_time": normalized["publish_time"],
        "content": _compact(content, 420),
        "content_excerpt": _compact(content, 160),
        "content_full": content,
        "score": round(float(normalized["score"]), 2),
        "score_detail": dict(normalized.get("score_detail") or {}),
        "likes": normalized["likes"],
        "comments": normalized["comments"],
        "reposts": normalized["reposts"],
        "post_url": normalized["post_url"],
        "image_count": image_count,
        "image_preview_paths": image_paths[:3],
    }


def _split_multi(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value]
    else:
        parts = [part.strip() for part in re.split(r"\s*\|\s*|\n+", str(value or ""))]
    return [part for part in parts if part]


def _compact(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_chars] + "..." if len(text) > max_chars else text


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
