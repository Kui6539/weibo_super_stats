from __future__ import annotations

import re
from collections.abc import Iterable
from email.utils import parsedate_to_datetime
from typing import Any

from modules.images.url_extract import extract_status_image_urls
from modules.text_cleaning import clean_topic_tags, normalize_weibo_text, strip_html_text
from modules.weibo_url import build_weibo_url

CHAOHUA_API_URL = "https://weibo.com/ajax_proxy/chaohua/page"


def initial_chaohua_params(topic_id: str) -> dict[str, str]:
    return {"flowId": str(topic_id or "").strip()}


def next_chaohua_params(topic_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    params = ((payload.get("moreInfo") or {}).get("params") or {}) if isinstance(payload, dict) else {}
    if not isinstance(params, dict) or not params:
        return None
    out: dict[str, Any] = {"flowId": str(topic_id or "").strip()}
    for key, value in params.items():
        if value is not None:
            out[str(key)] = value
    return out


def extract_chaohua_topic_name(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    header_data = ((payload.get("header") or {}).get("data") or {})
    if not isinstance(header_data, dict):
        return ""
    for key in ("nick", "page_nav_title", "page_title"):
        value = normalize_weibo_text(str(header_data.get(key) or ""))
        if value:
            return value
    return ""


def parse_chaohua_posts_from_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for status in iter_chaohua_statuses(payload):
        post = parse_chaohua_status(status)
        post_id = str(post.get("post_id") or "").strip()
        if not post_id or post_id in seen:
            continue
        seen.add(post_id)
        posts.append(post)
    return posts


def iter_chaohua_statuses(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if not isinstance(payload, dict):
        return
    yield from _walk_items(payload.get("items"))


def parse_chaohua_status(status: dict[str, Any]) -> dict[str, Any]:
    post_id = str(status.get("mid") or status.get("idstr") or status.get("id") or "").strip()
    user = status.get("user") if isinstance(status.get("user"), dict) else {}
    author_id = str(user.get("idstr") or user.get("id") or status.get("user_id") or "").strip()
    user_name = normalize_weibo_text(str(user.get("screen_name") or ""))
    mblog_id = str(status.get("mblogid") or "").strip()
    content_html = str(status.get("text_raw") or status.get("longTextContent_raw") or status.get("text") or "")
    content = clean_topic_tags(strip_html_text(content_html, preserve_newlines=True), preserve_newlines=True)
    original_image_urls = extract_status_image_urls(status)
    reposts = _parse_count(status.get("reposts_count"))
    comments = _parse_count(status.get("comments_count"))
    likes = _parse_count(status.get("attitudes_count"))

    return {
        "post_id": post_id,
        "author_id": author_id,
        "user_name": user_name,
        "publish_time": _format_created_at(status.get("created_at")),
        "post_url": build_weibo_url(mblog_id or post_id, author_id),
        "original_image_urls": " | ".join(original_image_urls),
        "image_count": len(original_image_urls),
        "downloaded_image_count": 0,
        "image_local_paths": "",
        "content": content,
        "has_video": _has_video(status),
        "reposts": reposts,
        "comments": comments,
        "likes": likes,
        "non_author_comments": 0,
        "author_replies": 0,
        "topic_comment_factor": 1.0,
        "score": 0.0,
        "top_comment_1": "",
        "top_comment_2": "",
        "top_comment_3": "",
        "top_comment_count": 0,
        "engagement_total": reposts + comments + likes,
    }


def _walk_items(items: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if item.get("category") == "feed" and isinstance(data, dict):
            yield data
        children = item.get("items")
        if isinstance(children, list):
            yield from _walk_items(children)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            yield from _walk_items(data.get("items"))


def _format_created_at(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", raw):
        return normalize_weibo_text(raw)
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        return normalize_weibo_text(raw)
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    raw = normalize_weibo_text(str(value or "")).replace(",", "")
    if not raw:
        return 0
    if match := re.search(r"(\d+(?:\.\d+)?)\s*(?:\u4ebf|e)", raw, flags=re.I):
        return int(float(match.group(1)) * 100000000)
    if match := re.search(r"(\d+(?:\.\d+)?)\s*(?:\u4e07|w)", raw, flags=re.I):
        return int(float(match.group(1)) * 10000)
    if match := re.search(r"\d+", raw):
        return int(match.group(0))
    return 0


def _has_video(status: dict[str, Any]) -> bool:
    page_info = status.get("page_info")
    if isinstance(page_info, dict):
        page_type = str(page_info.get("type") or page_info.get("object_type") or "").lower()
        if "video" in page_type:
            return True
        if isinstance(page_info.get("media_info"), dict):
            return True
    if isinstance(status.get("mix_media_info"), dict):
        return True
    if isinstance(status.get("page_info"), str) and "video" in status["page_info"].lower():
        return True
    return False
