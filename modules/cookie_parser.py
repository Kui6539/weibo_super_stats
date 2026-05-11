from __future__ import annotations

import re


def extract_cookie_from_plain_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if _looks_like_cookie(raw):
        return normalize_cookie(raw)
    return ""


def extract_cookie_from_headers(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    match = re.search(r"(?im)^\s*cookie\s*:\s*(.+?)\s*$", raw)
    if not match:
        match = re.search(r'(?i)"cookie"\s*:\s*"(.+?)"', raw)
    return normalize_cookie(match.group(1)) if match else ""


def extract_cookie_from_curl(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    patterns = (
        r"-H\s+['\"]cookie:\s*(.+?)['\"]",
        r"(?:-b|--cookie)\s+['\"](.+?)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return normalize_cookie(match.group(1))
    return ""


def extract_cookie_from_text(text: str) -> str:
    return (
        extract_cookie_from_headers(text)
        or extract_cookie_from_curl(text)
        or extract_cookie_from_plain_text(text)
    )


def normalize_cookie(cookie: str) -> str:
    raw = str(cookie or "").strip().strip("'\"")
    raw = raw.replace("\r", "\n")
    raw = re.sub(r"\n+", "; ", raw)
    parts: list[str] = []
    seen: set[str] = set()
    for part in raw.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def mask_cookie_for_log(cookie: str) -> str:
    normalized = normalize_cookie(cookie)
    if not normalized:
        return ""
    masked: list[str] = []
    for part in normalized.split(";"):
        item = part.strip()
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        if len(value) <= 6:
            shown = "***"
        else:
            shown = f"{value[:3]}...{value[-3:]}"
        masked.append(f"{name}={shown}")
    return "; ".join(masked)


def _looks_like_cookie(text: str) -> bool:
    if ":" in text.split(";", 1)[0]:
        return False
    pairs = [part.strip() for part in text.split(";") if part.strip()]
    return any(re.match(r"^[A-Za-z0-9_.-]+\s*=", part) for part in pairs)
