from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class ScoreDetail:
    likes_score: float
    non_author_comment_score: float
    author_reply_score: float
    repost_score: float
    base_score: float
    time_weight: float
    final_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def calculate_time_weight(publish_dt: datetime | None, ref_now: datetime | None = None) -> float:
    if publish_dt is None:
        return 1.0
    now = ref_now or datetime.now()
    age_hours = max(0.0, (now - publish_dt).total_seconds() / 3600)
    age_ratio = min(1.0, age_hours / (7.0 * 24.0))
    return max(0.75, 1.01 + 0.06 * (0.5 - age_ratio))


def calculate_score(post: dict, config: dict | Any) -> ScoreDetail:
    likes = _to_int(post.get("likes"))
    reposts = _to_int(post.get("reposts"))
    total_comments = _to_int(post.get("comments"))
    author_replies = min(_to_int(post.get("author_replies")), total_comments)
    non_author_comments = max(0, total_comments - author_replies)
    comment_factor = max(0.5, _config_float(config, "topic_comment_factor", 1.0))
    likes_weight = _config_float(config, "likes_weight", 0.3)
    comment_weight = _config_float(config, "comment_weight", 0.5)
    author_reply_weight = _config_float(config, "author_reply_weight", 0.2)
    repost_weight = _config_float(config, "repost_weight", 0.1)
    ref_now = _config_value(config, "window_end", None)
    publish_dt = _config_value(post, "publish_dt", None)

    likes_score = likes * likes_weight
    non_author_comment_score = non_author_comments * comment_weight * comment_factor
    author_reply_score = author_replies * author_reply_weight
    repost_score = reposts * repost_weight
    base_score = likes_score + non_author_comment_score + author_reply_score + repost_score
    time_weight = calculate_time_weight(publish_dt if isinstance(publish_dt, datetime) else None, ref_now)
    final_score = base_score * time_weight
    return ScoreDetail(
        likes_score=round(likes_score, 4),
        non_author_comment_score=round(non_author_comment_score, 4),
        author_reply_score=round(author_reply_score, 4),
        repost_score=round(repost_score, 4),
        base_score=round(base_score, 4),
        time_weight=round(time_weight, 4),
        final_score=round(final_score, 4),
    )


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _config_float(config: dict | Any, key: str, default: float) -> float:
    try:
        return float(_config_value(config, key, default))
    except (TypeError, ValueError):
        return default


def _config_value(config: dict | Any, key: str, default: Any) -> Any:
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)
