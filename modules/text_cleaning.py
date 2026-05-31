from __future__ import annotations

import re

from bs4 import BeautifulSoup


DEFAULT_TOPIC_TAGS = ("warma", "怒九笑")


def collapse_blank_lines(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = remove_weibo_private_chars(raw)
    raw = re.sub(r"[\t\f\v]+", " ", raw)
    raw = re.sub(r"[ \u3000]{3,}", "  ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def remove_weibo_private_chars(text: str) -> str:
    """Remove icon-font/private-use chars that render as tofu squares."""
    raw = str(text or "")
    raw = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", raw)
    raw = raw.replace("\ufe0f", "")
    raw = raw.replace("\ufffc", "")
    return re.sub(r"[\ue000-\uf8ff]", "", raw)


def normalize_weibo_text(text: str, preserve_newlines: bool = False) -> str:
    raw = collapse_blank_lines(text)
    if preserve_newlines:
        return raw
    return re.sub(r"\s+", " ", raw).strip()


def strip_html_text(text: str, preserve_newlines: bool = False) -> str:
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "lxml")
    except Exception:
        soup = BeautifulSoup(text, "html.parser")
    sep = "\n" if preserve_newlines else " "
    return normalize_weibo_text(soup.get_text(sep, strip=True), preserve_newlines=preserve_newlines)


def clean_topic_tags(
    text: str,
    topic_names: list[str] | tuple[str, ...] | None = None,
    preserve_newlines: bool = False,
) -> str:
    names = tuple(topic_names or DEFAULT_TOPIC_TAGS)
    raw = normalize_weibo_text(text, preserve_newlines=preserve_newlines)
    if not raw:
        return ""
    for name in names:
        clean_name = re.escape(str(name or "").strip())
        if not clean_name:
            continue
        extra_expression = r"(?:\[[^\[\]]{1,24}\]|[（(][^）)]{1,24}[）)])?"
        bracket_topic = r"(?:\[\s*超话\s*\]|【\s*超话\s*】|[（(]\s*超话\s*[）)]|超话)"
        patterns = (
            rf"#\s*{clean_name}\s*{bracket_topic}\s*{extra_expression}\s*#",
            rf"#\s*{clean_name}\s*超话\s*{extra_expression}\s*#",
            rf"{clean_name}\s*{bracket_topic}\s*{extra_expression}",
            rf"{clean_name}\s*超话\s*{extra_expression}",
        )
        for pattern in patterns:
            raw = re.sub(pattern, " ", raw, flags=re.I)
    return normalize_weibo_text(raw, preserve_newlines=preserve_newlines)


def convert_weibo_emoji(text: str) -> str:
    return re.sub(r"\[([^\[\]]{1,24})\]", "(｡･ω･｡)", str(text or ""))
