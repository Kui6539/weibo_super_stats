from __future__ import annotations

from typing import Any

EXCEL_COLUMNS: list[tuple[str, str]] = [
    ("user_name", "作者昵称"),
    ("publish_time", "帖子发送时间"),
    ("post_url", "帖子链接"),
    ("original_image_urls", "原图链接"),
    ("image_local_paths", "图片本地路径"),
    ("content", "帖子内容"),
    ("reposts", "转发数"),
    ("comments", "评论总数"),
    ("likes", "点赞数"),
    ("non_author_comments", "非楼主评论数"),
    ("author_replies", "楼主回复数"),
    ("topic_comment_factor", "话题评论系数"),
    ("score", "帖子分数"),
    ("engagement_total", "互动总量"),
    ("top_comment_1", "热评1(按点赞)"),
    ("top_comment_2", "热评2(按点赞)"),
    ("top_comment_3", "热评3(按点赞)"),
]


def build_excel_rows(
    posts: list[dict[str, Any]],
    column_map: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    columns = column_map or EXCEL_COLUMNS
    return [{cn: format_cell_value(post.get(en, "")) for en, cn in columns} for post in posts]


def format_cell_value(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return ""
    return str(value)
