from __future__ import annotations

import re

from modules.text_cleaning import normalize_weibo_text, strip_html_text


def build_report_title(topic_name: str | None = None, super_topic: str | None = None) -> str:
    name = normalize_super_topic_name(topic_name or "")
    if not name:
        name = normalize_super_topic_name(str(super_topic or ""))
    return f"{name or '微博'}超话周报"


def normalize_super_topic_name(value: str) -> str:
    raw = normalize_weibo_text(str(value or ""))
    if not raw:
        return ""
    raw = raw.strip().strip("#")
    raw = re.sub(r"^https?://\S+$", "", raw, flags=re.I)
    raw = re.sub(r"^100808[0-9a-fA-F]+$", "", raw)
    raw = re.sub(r"\s*[-_｜|].*$", "", raw)
    raw = re.sub(r"(?:微博)?超话(?:社区|详情|首页|主页)?$", "", raw)
    raw = re.sub(r"(?:的)?微博(?:主页)?$", "", raw)
    raw = raw.strip(" #　-—_｜|：:")
    if not raw or raw.lower() in {"weibo", "m.weibo.cn", "weibo.com"}:
        return ""
    return raw[:40]


def extract_super_topic_name(page_html: str, fallback: str | None = None) -> str:
    html = str(page_html or "")
    candidates: list[str] = []

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if title_match:
        candidates.append(strip_html_text(title_match.group(1)))

    for pattern in (
        r'<meta[^>]+(?:property|name)=["\'](?:og:title|keywords|description)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:title|keywords|description)["\']',
    ):
        candidates.extend(strip_html_text(match.group(1)) for match in re.finditer(pattern, html, flags=re.I | re.S))

    topic_match = re.search(r"#?\s*([^#<>{}\"'，,。；;｜|]{1,40}?)\s*超话", html)
    if topic_match:
        candidates.append(topic_match.group(1))

    candidates.append(str(fallback or ""))

    for candidate in candidates:
        name = normalize_super_topic_name(candidate)
        if name:
            return name
    return ""
