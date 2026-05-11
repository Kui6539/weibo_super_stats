from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any


def export_weekly_report_md(
    posts: Iterable[dict[str, Any]],
    md_path: Path,
    title: str = "微博超话周报",
    leaderboards: dict[str, Any] | None = None,
    preselected: bool = False,
) -> None:
    from crawler import (
        _clean_report_text,
        _clean_text,
        _format_hot_comment_text,
        _format_posts_date_range,
        _iter_report_comments,
        _select_weekly_posts,
        _split_multi_urls,
        _to_rel_path,
        build_comment_leaderboards,
    )

    all_posts = list(posts)
    rows = all_posts[:15] if preselected else _select_weekly_posts(all_posts, limit=15)
    board = leaderboards or build_comment_leaderboards(all_posts, top_n=3)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    md_dir = md_path.parent
    date_range_text = _format_posts_date_range(rows)
    overview = _build_overview(rows)

    lines: list[str] = [
        f"# {title}",
        "",
        f"> **统计周期**：{date_range_text}",
        f"> **入选帖子**：{len(rows)} 条",
        "",
        "## 1. 本周概览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 入选帖子数 | {overview['post_count']} |",
        f"| 点赞总数 | {overview['likes_total']} |",
        f"| 评论总数 | {overview['comments_total']} |",
        f"| 转发总数 | {overview['reposts_total']} |",
        f"| 互动总数 | {overview['engagement_total']} |",
        "",
        "## 2. 社区互动榜",
        "",
    ]

    lines.extend(_render_count_leaderboard(board.get("comment_count_top3") or []))
    lines.extend(["", ""])
    lines.extend(_render_quality_leaderboard(board.get("comment_quality_top3") or []))
    lines.extend(["", "", "## 3. 本周热帖 Top15", ""])

    if not rows:
        lines.extend(["> 暂无入选帖子。", ""])

    for index, post in enumerate(rows, start=1):
        author = _clean_text(str(post.get("user_name", "") or "未知作者"))
        content = _clean_report_text(str(post.get("content", "") or ""))
        publish_time = _clean_text(str(post.get("publish_time", "") or ""))
        post_url = _clean_text(str(post.get("post_url", "") or ""))
        post_images = _split_multi_urls(str(post.get("image_local_paths") or ""), sep="|")
        comments = _iter_report_comments(post)

        lines.extend(
            [
                f"### No. {index:02d} · @{author}",
                "",
                "| 项目 | 数据 |",
                "| --- | --- |",
                f"| 发布时间 | {_table_cell(publish_time or '未知')} |",
                f"| 综合分 | {_table_cell(_format_number(post.get('score'), digits=2, default='-'))} |",
                f"| 点赞 | {_table_cell(_format_int(post.get('likes')))} |",
                f"| 评论 | {_table_cell(_format_int(post.get('comments')))} |",
                f"| 转发 | {_table_cell(_format_int(post.get('reposts')))} |",
                f"| 原帖 | {_post_link(post_url)} |",
                "",
                "#### 正文",
                "",
                _quote_block(content),
                "",
            ]
        )

        if post_images:
            lines.extend(["#### 配图", ""])
            for img_index, img_path in enumerate(post_images, start=1):
                rel_path = _to_rel_path(md_dir, Path(img_path))
                lines.extend([f"![帖子配图 {index:02d}-{img_index}]({rel_path})", ""])

        if comments:
            lines.extend(["#### 热评", ""])
            for comment_index, comment in enumerate(comments, start=1):
                comment_text = _clean_report_text(_format_hot_comment_text(comment))
                if comment_text:
                    lines.extend([f"{comment_index}. {comment_text}", ""])
                for image_index, image_path in enumerate(
                    _split_multi_urls(str(comment.get("image_local_paths") or ""), sep="|"),
                    start=1,
                ):
                    rel_path = _to_rel_path(md_dir, Path(image_path))
                    lines.extend([f"   ![热评配图 {index:02d}-{comment_index}-{image_index}]({rel_path})", ""])

        lines.extend(["---", ""])

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _build_overview(posts: list[dict[str, Any]]) -> dict[str, int]:
    likes_total = sum(_to_int(post.get("likes")) for post in posts)
    comments_total = sum(_to_int(post.get("comments")) for post in posts)
    reposts_total = sum(_to_int(post.get("reposts")) for post in posts)
    return {
        "post_count": len(posts),
        "likes_total": likes_total,
        "comments_total": comments_total,
        "reposts_total": reposts_total,
        "engagement_total": likes_total + comments_total + reposts_total,
    }


def _render_count_leaderboard(rows: Iterable[dict[str, Any]]) -> list[str]:
    items = list(rows)
    lines = [
        "### 2.1 评论数量榜 Top3",
        "",
        "| 排名 | 用户 | 评论数 | 覆盖帖子 | 热评前三 |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    if not items:
        return lines + ["| - | 暂无数据 | 0 | 0 | 0 |"]
    for item in items:
        lines.append(
            "| {rank} | @{user} | {count} | {post_span} | {hot_count} |".format(
                rank=_to_int(item.get("rank")),
                user=_table_cell(item.get("user_name") or "匿名用户"),
                count=_to_int(item.get("comment_count")),
                post_span=_to_int(item.get("commented_post_count")),
                hot_count=_to_int(item.get("hot_top3_count")),
            )
        )
    return lines


def _render_quality_leaderboard(rows: Iterable[dict[str, Any]]) -> list[str]:
    items = list(rows)
    lines = [
        "### 2.2 评论质量榜 Top3",
        "",
        "| 排名 | 用户 | 评论获赞 | 热评前三 | 质量分 |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    if not items:
        return lines + ["| - | 暂无数据 | 0 | 0 | 0 |"]
    for item in items:
        lines.append(
            "| {rank} | @{user} | {likes} | {hot_count} | {quality} |".format(
                rank=_to_int(item.get("rank")),
                user=_table_cell(item.get("user_name") or "匿名用户"),
                likes=_to_int(item.get("comment_likes_total")),
                hot_count=_to_int(item.get("hot_top3_count")),
                quality=_format_number(item.get("quality_score"), digits=2, default="0"),
            )
        )
    return lines


def _quote_block(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return "> （无正文）"
    return "\n".join(f"> {line}" if line.strip() else ">" for line in clean.splitlines())


def _post_link(url: str) -> str:
    clean = str(url or "").strip()
    if not clean:
        return "无链接"
    escaped = clean.replace(")", "%29").replace(" ", "%20")
    return f"[打开微博]({escaped})"


def _table_cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("\r\n", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|") or "-"


def _format_int(value: Any) -> str:
    return str(_to_int(value))


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _format_number(value: Any, digits: int = 2, default: str = "0") -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return default
