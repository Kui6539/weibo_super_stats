from __future__ import annotations

import re

SUPER_TOPIC_ID_PATTERN = re.compile(r"/p/([0-9a-fA-F]+)")


def parse_super_topic_id(input_text: str) -> str | None:
    raw = str(input_text or "").strip()
    if raw.startswith("100808") and "/" not in raw:
        return raw
    match = SUPER_TOPIC_ID_PATTERN.search(raw)
    return match.group(1) if match else None


def extract_post_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{6,}", raw):
        return raw
    patterns = (
        r"/detail/(\d+)",
        r"/(\d{6,})(?:\?|$|/)",
        r"[?&](?:id|mid)=(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return match.group(1)
    return ""


def build_weibo_url(post_id: str, user_id: str | None = None) -> str:
    clean_id = str(post_id or "").strip()
    if not clean_id:
        return ""
    clean_user = str(user_id or "").strip()
    if clean_user:
        return f"https://weibo.com/{clean_user}/{clean_id}"
    return f"https://weibo.com/detail/{clean_id}"


def to_absolute_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("/"):
        return "https://weibo.com" + raw
    return raw


def normalize_image_url(url: str) -> str:
    raw = to_absolute_url(url)
    for segment in ("/orj360/", "/mw690/", "/thumb150/", "/square/", "/bmiddle/"):
        raw = raw.replace(segment, "/large/")
    return raw
