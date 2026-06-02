from __future__ import annotations

import re
from datetime import datetime, timedelta

from modules.text_cleaning import normalize_weibo_text, strip_html_text

ISSUE_ONE_SATURDAY = datetime(2026, 4, 25)

PLATFORM_TITLE_SUFFIX_RE = re.compile(
    r"\s*[-_~｜|—–－]+(?:新浪(?:微博)?|微博)(?:超话(?:社区|详情|首页|主页)?|社区)?",
    flags=re.I,
)


def build_report_title(topic_name: str | None = None, super_topic: str | None = None) -> str:
    name = normalize_super_topic_name(topic_name or "")
    if not name:
        name = normalize_super_topic_name(str(super_topic or ""))
    return f"{name or '微博'}超话周报"


def normalize_issue_value(value: object) -> str:
    text = normalize_weibo_text(str(value or ""))
    if text.startswith("第") and text.endswith("期"):
        text = text[1:-1]
    digits = re.sub(r"\D+", "", text)
    return str(int(digits)) if digits else ""


def calculate_weekly_issue(reference: datetime | None = None) -> int:
    ref = reference or datetime.now()
    target_saturday = ref + timedelta(days=(5 - ref.weekday()) % 7)
    weeks = (target_saturday.date() - ISSUE_ONE_SATURDAY.date()).days // 7
    return max(1, weeks + 1)


def format_report_title_with_issue(title: str, issue: object) -> str:
    clean_title = normalize_report_title(title).strip()
    normalized_issue = normalize_issue_value(issue)
    if not clean_title or not normalized_issue:
        return clean_title
    clean_title = re.sub(r"\s*第\d+期\s*$", "", clean_title).strip()
    return f"{clean_title} 第{normalized_issue}期"


def normalize_report_title(value: str | None) -> str:
    raw = normalize_weibo_text(str(value or "")).strip()
    if not raw:
        return ""
    raw = re.sub(r"\s*第\d+期\s*$", "", raw).strip()
    raw = PLATFORM_TITLE_SUFFIX_RE.sub("", raw).strip()
    if raw.endswith("周报"):
        topic_name = normalize_super_topic_name(raw.removesuffix("周报"))
        if topic_name:
            return build_report_title(topic_name)
    return raw


def normalize_super_topic_name(value: str) -> str:
    raw = normalize_weibo_text(str(value or ""))
    if not raw:
        return ""
    raw = raw.strip().strip("#")
    raw = re.sub(r"^https?://\S+$", "", raw, flags=re.I)
    raw = re.sub(r"^100808[0-9a-fA-F]+$", "", raw)
    raw = re.split(r"[,，、]", raw)[0].strip()
    raw = PLATFORM_TITLE_SUFFIX_RE.sub("", raw)
    raw = re.sub(r"\s*[-_~｜|—–－]+.*$", "", raw)
    raw = re.sub(r"(?:微博)?超话(?:社区|详情|首页|主页)?$", "", raw)
    raw = re.sub(r"(?:的)?微博(?:主页)?$", "", raw)
    raw = raw.strip(" #　-—~｜|：:")
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

    topic_match = re.search(r"#?\s*([^#<>{}\"'，。；;~｜|]{1,40}?)\s*超话", html)
    if topic_match:
        candidates.append(topic_match.group(1))

    candidates.append(str(fallback or ""))

    for candidate in candidates:
        name = normalize_super_topic_name(candidate)
        if name:
            return name
    return ""
