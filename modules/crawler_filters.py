from __future__ import annotations

import re
from typing import Any


def should_exclude_post(post: dict, _config: dict | None = None) -> tuple[bool, str]:
    if _is_video_post(post):
        return True, "视频帖"
    content = _clean_text(str(post.get("content") or ""))
    if _is_summary_post(content):
        if re.search(r"导航|索引", content, flags=re.I):
            return True, "导航帖"
        return True, "汇总帖"
    return False, ""


def _is_video_post(post: dict) -> bool:
    if bool(post.get("has_video")):
        return True
    text = _clean_text(str(post.get("content") or "")).lower()
    post_url = _clean_text(str(post.get("post_url") or "")).lower()
    hit_keyword = any(k in text for k in ("视频", "vid", "播放量"))
    has_video_link = any(k in text or k in post_url for k in ("video.weibo.com", "weibo.com/tv", "/tv/"))
    return hit_keyword and has_video_link


def _is_summary_post(content: str) -> bool:
    raw = _clean_text(content)
    if not raw:
        return False
    patterns = [
        r"二创精选",
        r"本周精选",
        r"周报",
        r"汇总",
        r"合集",
        r"索引",
        r"导航",
        r"整理了",
        r"发布在.?b站",
        r"前往观赏",
        r"网页链接",
        r"文章在该链接",
    ]
    return any(re.search(pattern, raw, flags=re.I) for pattern in patterns)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
