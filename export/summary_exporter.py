from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from modules.time_utils import normalize_date, parse_weibo_time


def build_summary(posts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(posts)
    if not rows:
        return {
            "total_posts": 0,
            "sum_reposts": 0,
            "sum_comments": 0,
            "sum_likes": 0,
            "sum_engagement": 0,
            "sum_score": 0.0,
            "avg_engagement_per_post": 0.0,
            "avg_score_per_post": 0.0,
            "posts_by_date": {},
        }

    sum_reposts = 0
    sum_comments = 0
    sum_likes = 0
    sum_engagement = 0
    sum_score_raw = 0.0
    daily_counter: Counter[str] = Counter()
    for row in rows:
        sum_reposts += int(row.get("reposts", 0) or 0)
        sum_comments += int(row.get("comments", 0) or 0)
        sum_likes += int(row.get("likes", 0) or 0)
        sum_engagement += int(row.get("engagement_total", 0) or 0)
        sum_score_raw += float(row.get("score", 0.0) or 0.0)
        daily_counter[normalize_date(str(row.get("publish_time", "")).strip()) or "未知日期"] += 1

    sum_score = round(sum_score_raw, 4)
    return {
        "total_posts": len(rows),
        "sum_reposts": sum_reposts,
        "sum_comments": sum_comments,
        "sum_likes": sum_likes,
        "sum_engagement": sum_engagement,
        "sum_score": sum_score,
        "avg_engagement_per_post": round(sum_engagement / len(rows), 2),
        "avg_score_per_post": round(sum_score / len(rows), 4),
        "posts_by_date": dict(sorted(daily_counter.items())),
    }


def analyze_active_period(posts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(posts)
    hour_counts = [0] * 24
    valid = 0
    for row in rows:
        dt = parse_weibo_time(str(row.get("publish_time", "") or ""))
        if not dt:
            continue
        hour_counts[dt.hour] += 1
        valid += 1

    if valid == 0:
        return {
            "valid_posts": 0,
            "hour_counts": hour_counts,
            "top_hour": None,
            "top_hour_count": 0,
            "top_two_hour_start": None,
            "top_two_hour_count": 0,
            "low_hour": None,
            "low_hour_count": 0,
            "low_two_hour_start": None,
            "low_two_hour_count": 0,
            "recommended_anchor_hour": 20,
        }

    top_hour = max(range(24), key=lambda hour: hour_counts[hour])
    low_hour = min(range(24), key=lambda hour: hour_counts[hour])
    two_hour_scores = [hour_counts[hour] + hour_counts[(hour + 1) % 24] for hour in range(24)]
    top_two_start = max(range(24), key=lambda hour: two_hour_scores[hour])
    low_two_start = min(range(24), key=lambda hour: two_hour_scores[hour])

    return {
        "valid_posts": valid,
        "hour_counts": hour_counts,
        "top_hour": top_hour,
        "top_hour_count": hour_counts[top_hour],
        "top_two_hour_start": top_two_start,
        "top_two_hour_count": two_hour_scores[top_two_start],
        "low_hour": low_hour,
        "low_hour_count": hour_counts[low_hour],
        "low_two_hour_start": low_two_start,
        "low_two_hour_count": two_hour_scores[low_two_start],
        "recommended_anchor_hour": top_two_start,
    }

def write_summary_txt(
    summary: dict[str, Any],
    txt_path: Path,
    leaderboards: dict[str, Any] | None = None,
    active_period: dict[str, Any] | None = None,
    all_posts_summary: dict[str, Any] | None = None,
    carryover_hours: int = 0,
    format_leaderboard_line: Callable[..., str] | None = None,
) -> None:
    lines = [
        f"入选帖子数(导出): {summary['total_posts']}",
        f"入选总转发: {summary['sum_reposts']}",
        f"入选总评论: {summary['sum_comments']}",
        f"入选总点赞: {summary['sum_likes']}",
        f"入选总互动量: {summary['sum_engagement']}",
        f"入选总分数: {summary['sum_score']}",
        f"入选平均每帖互动量: {summary['avg_engagement_per_post']}",
        f"入选平均每帖分数: {summary['avg_score_per_post']}",
    ]
    carryover = max(0, int(carryover_hours or 0))
    if carryover > 0:
        lines.append(f"统计保险窗口: 截止前{carryover}小时发帖顺延到下一期")

    _append_distribution(lines, summary, all_posts_summary)
    _append_active_period(lines, active_period)
    _append_leaderboards(lines, leaderboards, format_leaderboard_line)

    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("\n".join(lines), encoding="utf-8")


def calc_date_distribution_fit(all_dist: dict[str, int], selected_dist: dict[str, int]) -> dict[str, float]:
    dates = sorted(set(all_dist.keys()) | set(selected_dist.keys()))
    if not dates:
        return {"cosine_similarity": 0.0, "js_similarity": 0.0, "fit_score": 0.0}

    all_total = sum(max(0, int(all_dist.get(day, 0) or 0)) for day in dates)
    selected_total = sum(max(0, int(selected_dist.get(day, 0) or 0)) for day in dates)
    if all_total <= 0 or selected_total <= 0:
        return {"cosine_similarity": 0.0, "js_similarity": 0.0, "fit_score": 0.0}

    p = [max(0.0, float(all_dist.get(day, 0) or 0)) / float(all_total) for day in dates]
    q = [max(0.0, float(selected_dist.get(day, 0) or 0)) / float(selected_total) for day in dates]
    dot = sum(pi * qi for pi, qi in zip(p, q, strict=True))
    norm_p = math.sqrt(sum(pi * pi for pi in p))
    norm_q = math.sqrt(sum(qi * qi for qi in q))
    cosine = dot / (norm_p * norm_q) if norm_p > 0 and norm_q > 0 else 0.0
    m = [(pi + qi) / 2.0 for pi, qi in zip(p, q, strict=True)]
    js_div = 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
    js_similarity = max(0.0, 1.0 - (js_div / math.log(2.0)))
    fit_score = max(0.0, min(1.0, 0.5 * cosine + 0.5 * js_similarity))
    return {
        "cosine_similarity": max(0.0, min(1.0, cosine)),
        "js_similarity": max(0.0, min(1.0, js_similarity)),
        "fit_score": fit_score,
    }


def _append_distribution(lines: list[str], summary: dict[str, Any], all_posts_summary: dict[str, Any] | None) -> None:
    if all_posts_summary is None:
        lines.append("")
        lines.append("按日期发帖数:")
        for day, count in dict(summary.get("posts_by_date") or {}).items():
            lines.append(f"- {day}: {count}")
        return

    lines.append(f"当周全部帖子数: {int(all_posts_summary.get('total_posts', 0) or 0)}")
    all_dist = dict(all_posts_summary.get("posts_by_date") or {})
    selected_dist = dict(summary.get("posts_by_date") or {})
    fit_info = calc_date_distribution_fit(all_dist, selected_dist)
    lines.extend(["", "按日期发帖数（当周全部帖子）:"])
    lines.extend([f"- {day}: {count}" for day, count in all_dist.items()] or ["- 无数据"])
    lines.extend(["", "当周入选帖子（Top15）按日期发帖数:"])
    lines.extend([f"- {day}: {count}" for day, count in selected_dist.items()] or ["- 无数据"])
    lines.extend(
        [
            "",
            "日期分布拟合程度:",
            f"- 综合拟合度: {fit_info['fit_score'] * 100:.2f}% "
            f"(余弦相似度 {fit_info['cosine_similarity'] * 100:.2f}%, "
            f"JS相似度 {fit_info['js_similarity'] * 100:.2f}%)",
            "- 说明: 将两组日期计数先归一化为占比后比较分布形状。",
        ]
    )


def _append_active_period(lines: list[str], active_period: dict[str, Any] | None) -> None:
    if active_period is None:
        return
    lines.extend(["", "活跃时段分析:"])
    if int(active_period.get("valid_posts", 0) or 0) <= 0:
        lines.append("- 样本不足，无法统计。")
        return
    top_hour = int(active_period.get("top_hour", 0) or 0)
    top_hour_count = int(active_period.get("top_hour_count", 0) or 0)
    start = int(active_period.get("top_two_hour_start", 0) or 0)
    two_count = int(active_period.get("top_two_hour_count", 0) or 0)
    low_hour = int(active_period.get("low_hour", 0) or 0)
    low_hour_count = int(active_period.get("low_hour_count", 0) or 0)
    low_start = int(active_period.get("low_two_hour_start", 0) or 0)
    low_two_count = int(active_period.get("low_two_hour_count", 0) or 0)
    rec = int(active_period.get("recommended_anchor_hour", start) or start)
    lines.append(f"- 单小时高峰: {top_hour:02d}:00-{top_hour:02d}:59，共 {top_hour_count} 帖")
    lines.append(f"- 两小时高峰: {start:02d}:00-{(start + 2) % 24:02d}:00，共 {two_count} 帖")
    lines.append(f"- 单小时低谷: {low_hour:02d}:00-{low_hour:02d}:59，共 {low_hour_count} 帖")
    lines.append(f"- 两小时低谷: {low_start:02d}:00-{(low_start + 2) % 24:02d}:00，共 {low_two_count} 帖")
    lines.append(f"- 建议固定周统计时间: 每周 {rec:02d}:00")


def _append_leaderboards(
    lines: list[str],
    leaderboards: dict[str, Any] | None,
    format_line: Callable[..., str] | None,
) -> None:
    if leaderboards is None:
        return
    formatter = format_line or _fallback_leaderboard_line
    lines.extend(["", "评论数量榜 Top3:"])
    count_rows = list(leaderboards.get("comment_count_top3") or [])
    lines.extend(
        [
            f"- {formatter(item, include_hot=False, include_quality=False, include_like_total=False, include_post_span=True)}"
            for item in count_rows
        ]
        or ["- 暂无评论数据"]
    )
    lines.extend(["", "评论质量榜 Top3:"])
    quality_rows = list(leaderboards.get("comment_quality_top3") or [])
    lines.extend(
        [f"- {formatter(item, include_hot=True, include_quality=False)}" for item in quality_rows]
        or ["- 暂无评论数据"]
    )


def _fallback_leaderboard_line(item: dict[str, Any], **_: Any) -> str:
    user = str(item.get("user_name") or "匿名用户")
    return f"{user}，评论 {int(item.get('comment_count', 0) or 0)} 条"


def _kl(a: list[float], b: list[float]) -> float:
    return sum(ai * math.log(ai / bi) for ai, bi in zip(a, b, strict=True) if ai > 0 and bi > 0)
