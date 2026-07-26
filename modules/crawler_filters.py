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


# Phrases that identify a roundup post on their own.
_SUMMARY_PATTERNS = [
    r"二创精选",
    r"本周精选",
    r"周报",
    r"汇总",
    r"合集",
    r"索引",
    r"导航",
    r"文章在该链接",
]

# Too common to be decisive. Weibo renders every external link as the literal
# text "网页链接", so treating it as a roundup marker silently dropped any
# popular post that happened to link somewhere -- and an excluded post never
# reaches the candidate list, so the user cannot rescue it during selection.
_WEAK_SUMMARY_PATTERNS = [
    r"网页链接",
    r"发布在.?b站",
    r"前往观赏",
]

# What turns a weak signal into a roundup: words describing collected content.
_SUMMARY_CONTEXT_PATTERNS = [
    r"整理",
    r"精选",
    r"投稿",
    r"作品",
    r"目录",
    r"名单",
    r"盘点",
]


def _is_summary_post(content: str) -> bool:
    raw = _clean_text(content)
    if not raw:
        return False
    if any(re.search(pattern, raw, flags=re.I) for pattern in _SUMMARY_PATTERNS):
        return True
    has_weak = any(re.search(pattern, raw, flags=re.I) for pattern in _WEAK_SUMMARY_PATTERNS)
    if not has_weak:
        return False
    return any(re.search(pattern, raw, flags=re.I) for pattern in _SUMMARY_CONTEXT_PATTERNS)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
