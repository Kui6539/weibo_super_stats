from __future__ import annotations

from typing import Any

from modules.weibo_url import normalize_image_url


def collect_post_images(post: dict[str, Any]) -> list[dict[str, Any]]:
    post_id = str(post.get("post_id") or "")
    urls = _split_urls(post.get("original_image_urls") or post.get("image_urls"))
    return [
        {"post_id": post_id, "type": "post_image", "url": normalize_image_url(url), "index": idx}
        for idx, url in enumerate(_dedup(urls), start=1)
    ]


def collect_comment_images(post: dict[str, Any]) -> list[dict[str, Any]]:
    post_id = str(post.get("post_id") or "")
    rows: list[dict[str, Any]] = []
    comments = post.get("top_comments_data") if isinstance(post.get("top_comments_data"), list) else []
    for comment_index, comment in enumerate(comments, start=1):
        if not isinstance(comment, dict):
            continue
        for image_index, url in enumerate(_dedup(_split_urls(comment.get("image_urls"))), start=1):
            rows.append(
                {
                    "post_id": post_id,
                    "comment_index": comment_index,
                    "type": "comment_image",
                    "url": normalize_image_url(url),
                    "index": image_index,
                }
            )
    return rows


def collect_all_images(selected_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, post in enumerate(selected_posts, start=1):
        for item in collect_post_images(post) + collect_comment_images(post):
            item["rank"] = rank
            item["author"] = str(post.get("user_name") or "")
            rows.append(item)
    return rows


def _split_urls(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value]
    else:
        parts = [part.strip() for part in str(value or "").replace("\n", "|").split("|")]
    return [part for part in parts if part]


def _dedup(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
