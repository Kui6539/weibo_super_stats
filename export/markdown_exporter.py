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
        _format_leaderboard_line,
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
    date_range_text = _format_posts_date_range(rows)

    lines: list[str] = [
        f"# {title}",
        "",
        f"> 帖子选取日期：{date_range_text}",
        "",
        "## 本周社区互动榜",
        "",
        "### 评论数量榜 Top3",
    ]
    count_rows = list(board.get("comment_count_top3") or [])
    lines.extend(
        [
            f"- {_format_leaderboard_line(item, include_hot=False, include_quality=False, include_like_total=False, include_post_span=True)}"
            for item in count_rows
        ]
        or ["- 暂无评论数据"]
    )
    lines.extend(["", "### 评论质量榜 Top3"])
    quality_rows = list(board.get("comment_quality_top3") or [])
    lines.extend(
        [f"- {_format_leaderboard_line(item, include_hot=True, include_quality=False)}" for item in quality_rows]
        or ["- 暂无评论数据"]
    )
    lines.extend(["", "## 本周热帖Top15", ""])

    md_dir = md_path.parent
    for post in rows:
        author = _clean_text(str(post.get("user_name", "") or "未知作者"))
        content = _clean_report_text(str(post.get("content", "") or ""))
        publish_time = _clean_text(str(post.get("publish_time", "") or ""))
        post_url = _clean_text(str(post.get("post_url", "") or ""))

        lines.extend([f"**@{author}**：{content}", "", f"- 发送时间：{publish_time}", ""])

        for img_path in _split_multi_urls(str(post.get("image_local_paths") or ""), sep="|"):
            lines.extend([f"![帖子图片]({_to_rel_path(md_dir, Path(img_path))})", ""])

        comments = _iter_report_comments(post)
        if comments:
            lines.extend(["<sub>热评</sub>", ""])
            for comment in comments:
                comment_text = _clean_report_text(_format_hot_comment_text(comment))
                if comment_text:
                    lines.extend([f"<sub>{comment_text}</sub>", ""])
                for image_path in _split_multi_urls(str(comment.get("image_local_paths") or ""), sep="|"):
                    lines.extend([f"![热评图片]({_to_rel_path(md_dir, Path(image_path))})", ""])

        lines.extend([f"[帖子链接]({post_url})", "", ""])

    md_path.write_text("\n".join(lines), encoding="utf-8")
