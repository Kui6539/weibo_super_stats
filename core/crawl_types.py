from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class CrawlError(Exception):
    pass


@dataclass
class CrawlConfig:
    super_topic: str
    cookie: str
    max_pages: int = 30
    pause_seconds: float = 1.0
    days_window: int = 7
    topic_comment_factor: float = 1.0
    likes_weight: float = 0.3
    comment_weight: float = 0.5
    author_reply_weight: float = 0.2
    repost_weight: float = 0.1
    comment_page_limit: int = 8
    text_workers: int = 6
    comment_workers: int = 6
    window_start: datetime | None = None
    window_end: datetime | None = None
    carryover_hours: int = 0
