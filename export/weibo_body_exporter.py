from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from export.context import ExportContext
from export.report_helpers import clean_report_text
from modules.text_cleaning import normalize_weibo_text
from modules.time_utils import format_date_range, parse_config_datetime
from modules.topic import (
    build_report_title,
    calculate_weekly_issue,
    format_report_title_with_issue,
    normalize_report_title,
)


def _issue_reference_date(config: dict[str, Any]) -> datetime | None:
    return parse_config_datetime(config.get("window_end")) or parse_config_datetime(config.get("window_start"))


def export_weibo_body(ctx: ExportContext, output_path: Path | None = None) -> Path:
    target = output_path or ctx.run_dir / "weibo_body.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_weibo_body_text(ctx), encoding="utf-8")
    return target


def build_weibo_body_text(ctx: ExportContext) -> str:
    config = ctx.config if isinstance(ctx.config, dict) else {}
    title = _display_title(config)
    date_range = _date_range(config)
    leaderboards = config.get("leaderboards") if isinstance(config.get("leaderboards"), dict) else {}

    lines = [title]
    if date_range:
        lines.append(date_range)
    lines.extend(["", "评论数量榜"])
    lines.extend(_leaderboard_lines(leaderboards.get("comment_count_top3"), mode="count"))
    lines.extend(["", "评论质量榜"])
    lines.extend(_leaderboard_lines(leaderboards.get("comment_quality_top3"), mode="quality"))
    lines.extend(["", "Top15 原帖"])
    lines.extend(_post_link_lines(ctx.selected_posts[:15]))
    return "\n".join(lines).strip() + "\n"


def _leaderboard_lines(rows: Any, mode: str) -> list[str]:
    items = [item for item in (rows or []) if isinstance(item, dict)]
    if not items:
        return ["暂无评论数据"]
    result: list[str] = []
    for index, item in enumerate(items, start=1):
        rank = int(item.get("rank") or index)
        user = _at_name(item.get("user_name") or "匿名用户")
        count = int(item.get("comment_count") or 0)
        hot = int(item.get("hot_top3_count") or 0)
        if mode == "quality":
            likes = int(item.get("comment_likes_total") or 0)
            score = _format_score(item.get("quality_score"))
            result.append(f"{rank}. {user} 评论{count}条，获赞{likes}，热评前三{hot}次，质量分{score}")
        else:
            posts = int(item.get("commented_post_count") or 0)
            result.append(f"{rank}. {user} 评论{count}条，覆盖{posts}帖，热评前三{hot}次")
    return result


def _post_link_lines(posts: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, post in enumerate(posts, start=1):
        author = _at_name(post.get("user_name") or "未知作者")
        url = normalize_weibo_text(str(post.get("post_url") or ""))
        if url:
            lines.append(f"{index}. {author} {url}")
        else:
            lines.append(f"{index}. {author} 原帖链接缺失")
    return lines or ["暂无入选帖子"]


def _display_title(config: dict[str, Any]) -> str:
    explicit = normalize_report_title(str(config.get("image_report_title") or config.get("report_title") or ""))
    title = normalize_weibo_text(explicit or build_report_title(config.get("super_topic_name"), config.get("super_topic")))
    issue = normalize_weibo_text(str(config.get("issue") or config.get("week_issue") or ""))
    if not issue:
        issue = str(calculate_weekly_issue(_issue_reference_date(config)))
    return format_report_title_with_issue(title, issue)


def _date_range(config: dict[str, Any]) -> str:
    return format_date_range(config.get("window_start"), config.get("window_end"))


def _at_name(value: Any) -> str:
    name = clean_report_text(str(value or "")).replace("@", "")
    name = normalize_weibo_text(name) or "匿名用户"
    return f"@{name}"


def _format_score(value: Any) -> str:
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


