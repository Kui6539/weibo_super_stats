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
