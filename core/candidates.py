"""Turns scored posts into the candidate payload the selection UI renders.

The shape returned by ``serialize_candidate`` is part of the ``/api/status``
contract: web/js/candidates.js reads every key here, and ``/api/select``
answers with the ``index`` field rather than a post id. Renaming or dropping a
key breaks the selection step silently, so treat this as an interface.

The image counters live alongside it because both derive the same "how many
images should this post have" answer from the same fields, and the job uses
their difference to report how many downloads failed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from modules.post_normalizer import split_multi_value
from modules.text_cleaning import remove_weibo_private_chars

# Longest body text sent to the card; the UI shows an excerpt and expands to
# content_full on demand.
CARD_CONTENT_CHARS = 420
CARD_EXCERPT_CHARS = 160

# Thumbnails shown per candidate card.
MAX_PREVIEW_IMAGES = 3


def compact_content(value: Any, max_chars: int = CARD_CONTENT_CHARS) -> str:
    content = remove_weibo_private_chars(str(value or ""))
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) > max_chars:
        return content[:max_chars] + "..."
    return content


def to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def serialize_candidate(post: dict, index: int) -> dict[str, Any]:
    """Build one candidate card. ``index`` is what /api/select expects back."""
    content = remove_weibo_private_chars(str(post.get("content", "") or "")).strip()
    image_count = to_int(post.get("image_count"))
    if image_count <= 0:
        image_count = len(split_multi_value(post.get("original_image_urls")))
    return {
        "index": index,
        "rank": index + 1,
        "user_name": str(post.get("user_name", "未知作者") or "未知作者"),
        "publish_time": str(post.get("publish_time", "") or ""),
        "content": compact_content(content),
        "content_excerpt": compact_content(content, max_chars=CARD_EXCERPT_CHARS),
        "content_full": content,
        "score": round(to_float(post.get("score")), 2),
        "score_detail": dict(post.get("score_detail") or {}),
        "likes": to_int(post.get("likes")),
        "comments": to_int(post.get("comments")),
        "reposts": to_int(post.get("reposts")),
        "post_url": str(post.get("post_url", "") or ""),
        "image_count": image_count,
        "image_preview_paths": _preview_paths(post),
    }


def _preview_paths(post: dict) -> list[str]:
    """Thumbnail URLs if the thumbnail stage produced them, else real images.

    The thumbnail stage writes small JPGs and hands back URLs the browser can
    fetch. When it has not run (or produced nothing), fall back to downloaded
    full-size images, skipping paths that never landed on disk.
    """
    thumbnail_urls = post.get("candidate_thumbnail_urls")
    if isinstance(thumbnail_urls, list):
        urls = [str(path) for path in thumbnail_urls if str(path or "").strip()]
        if urls:
            return urls[:MAX_PREVIEW_IMAGES]
    else:
        cached = split_multi_value(post.get("candidate_thumbnail_paths"))
        if cached:
            return cached[:MAX_PREVIEW_IMAGES]
    return [
        path
        for path in split_multi_value(post.get("image_local_paths"))
        if Path(path).is_file()
    ][:MAX_PREVIEW_IMAGES]


def count_expected_images(posts: list[dict]) -> int:
    """How many images the selected posts should yield, from their URLs."""
    total = 0
    for post in posts:
        total += len(split_multi_value(post.get("original_image_urls")))
        for comment in list(post.get("top_comments_data") or []):
            total += len(split_multi_value(comment.get("image_urls")))
    return total


def count_downloaded_images(posts: list[dict]) -> int:
    """How many of those images actually exist on disk."""
    total = 0
    for post in posts:
        paths = split_multi_value(post.get("image_local_paths_all"))
        if not paths:
            paths = split_multi_value(post.get("image_local_paths")) + split_multi_value(
                post.get("comment_image_local_paths")
            )
        total += sum(1 for path in paths if Path(path).exists())
    return total
