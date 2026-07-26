from __future__ import annotations

import re
from datetime import datetime, timedelta


def parse_weibo_time(text: str, now: datetime | None = None) -> datetime | None:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return None
    ref = now or datetime.now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    if match := re.search(r"(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{1,2}))?", raw):
        return datetime(
            ref.year,
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3) or 0),
            int(match.group(4) or 0),
        )
    if match := re.search(r"今天\s*(\d{1,2}):(\d{1,2})", raw):
        return datetime(ref.year, ref.month, ref.day, int(match.group(1)), int(match.group(2)))
    if match := re.search(r"昨天\s*(\d{1,2}):(\d{1,2})", raw):
        day = ref - timedelta(days=1)
        return datetime(day.year, day.month, day.day, int(match.group(1)), int(match.group(2)))
    if any(token in raw for token in ("分钟前", "秒前", "小时前")):
        return ref
    return None


# The shapes a window bound arrives in: the config file stores seconds, the
# browser's datetime-local input sends the "T" form without them.
CONFIG_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
)


def parse_config_datetime(value: object) -> datetime | None:
    """Parse a stored window bound, returning None rather than raising."""
    text = str(value or "").strip()
    for fmt in CONFIG_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_date_range(start: object, end: object, sep: str = " - ") -> str:
    """Render a "YYYY.MM.DD - YYYY.MM.DD" range, or "" if either end is bad.

    The weibo draft and the long-image report print the same range and are
    published together, so they must agree.
    """
    start_dt = parse_config_datetime(start)
    end_dt = parse_config_datetime(end)
    if not start_dt or not end_dt:
        return ""
    return f"{start_dt.strftime('%Y.%m.%d')}{sep}{end_dt.strftime('%Y.%m.%d')}"


def format_datetime(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return value.strftime(fmt) if value else ""


def is_post_in_range(publish_time: str | datetime | None, start: datetime, end: datetime) -> bool:
    if isinstance(publish_time, datetime):
        dt = publish_time
    else:
        dt = parse_weibo_time(str(publish_time or ""))
    return bool(dt and start <= dt <= end)


def normalize_date(text: str) -> str | None:
    dt = parse_weibo_time(text)
    if dt is not None:
        return dt.strftime("%Y-%m-%d")
    match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", str(text or "").strip())
    return match.group(1) if match else None
