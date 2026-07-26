from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ScoreDetail:
    likes_score: float
    non_author_comment_score: float
    author_reply_score: float
    repost_score: float
    base_score: float
    time_weight: float
    final_score: float

    def to_dict(self) -> dict[str, float]:
        return {
            "likes_score": self.likes_score,
            "non_author_comment_score": self.non_author_comment_score,
            "author_reply_score": self.author_reply_score,
            "repost_score": self.repost_score,
            "base_score": self.base_score,
            "time_weight": self.time_weight,
            "final_score": self.final_score,
        }


@dataclass(frozen=True, slots=True)
class PreparedScoreConfig:
    topic_comment_factor: float
    likes_weight: float
    comment_weight: float
    author_reply_weight: float
    repost_weight: float
    ref_now: datetime | None


def prepare_score_config(config: dict | Any) -> PreparedScoreConfig:
    if isinstance(config, PreparedScoreConfig):
        return config
    return PreparedScoreConfig(
        topic_comment_factor=max(0.5, _config_float(config, "topic_comment_factor", 1.0)),
        likes_weight=_config_float(config, "likes_weight", 0.3),
        comment_weight=_config_float(config, "comment_weight", 0.5),
        author_reply_weight=_config_float(config, "author_reply_weight", 0.2),
        repost_weight=_config_float(config, "repost_weight", 0.1),
        ref_now=_config_value(config, "window_end", None),
    )


# Default bias strength. The auto-calibration search in crawler.py sweeps this
# from 0.00 to 1.20, so the formula has to stay parameterised -- it used to be
# hardcoded here and duplicated there, which meant adjusting the floor or the
# centre in one place silently desynchronised scoring from calibration.
DEFAULT_TIME_WEIGHT_STRENGTH = 0.06

# Posts older than this carry the full age penalty.
TIME_WEIGHT_WINDOW_HOURS = 7.0 * 24.0

# Floor, so an aggressive strength cannot bury old posts entirely.
TIME_WEIGHT_FLOOR = 0.75
TIME_WEIGHT_CENTRE = 1.01


def time_age_ratio(publish_dt: datetime | None, now: datetime | None = None) -> float | None:
    """How far through the scoring window a post is, clamped to [0, 1]."""
    if publish_dt is None:
        return None
    ref = now or datetime.now()
    age_hours = max(0.0, (ref - publish_dt).total_seconds() / 3600.0)
    return min(1.0, age_hours / TIME_WEIGHT_WINDOW_HOURS)


def time_weight_from_age_ratio(
    age_ratio: float | None,
    strength: float = DEFAULT_TIME_WEIGHT_STRENGTH,
) -> float:
    if age_ratio is None:
        return 1.0
    s = max(0.0, float(strength))
    return max(TIME_WEIGHT_FLOOR, TIME_WEIGHT_CENTRE + s * (0.5 - age_ratio))


def calculate_time_weight(
    publish_dt: datetime | None,
    ref_now: datetime | None = None,
    strength: float = DEFAULT_TIME_WEIGHT_STRENGTH,
) -> float:
    return time_weight_from_age_ratio(time_age_ratio(publish_dt, ref_now), strength)


def calculate_score(post: dict, config: dict | Any) -> ScoreDetail:
    publish_dt = _config_value(post, "publish_dt", None)
    return calculate_score_values(
        likes=post.get("likes"),
        comments=post.get("comments"),
        author_replies=post.get("author_replies"),
        reposts=post.get("reposts"),
        publish_dt=publish_dt if isinstance(publish_dt, datetime) else None,
        config=config,
    )


def calculate_score_values(
    likes: Any,
    comments: Any,
    author_replies: Any,
    reposts: Any,
    publish_dt: datetime | None,
    config: dict | Any,
) -> ScoreDetail:
    score_config = prepare_score_config(config)
    likes = _to_int(likes)
    reposts = _to_int(reposts)
    total_comments = _to_int(comments)
    author_replies = min(_to_int(author_replies), total_comments)
    non_author_comments = max(0, total_comments - author_replies)

    likes_score = likes * score_config.likes_weight
    non_author_comment_score = non_author_comments * score_config.comment_weight * score_config.topic_comment_factor
    author_reply_score = author_replies * score_config.author_reply_weight
    repost_score = reposts * score_config.repost_weight
    base_score = likes_score + non_author_comment_score + author_reply_score + repost_score
    time_weight = calculate_time_weight(publish_dt, score_config.ref_now)
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
