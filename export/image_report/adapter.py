from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from export.context import ExportContext
from export.image_report.models import CommentBlock, ImageAsset, ImageReportConfig, ImageReportData, PostBlock
from export.report_helpers import clean_image_report_text, format_posts_date_range, iter_report_comments, split_multi_values
from modules.text_cleaning import normalize_weibo_text
from modules.topic import build_report_title

ISSUE_ONE_SATURDAY = datetime(2026, 4, 25)


def build_image_report_data(ctx: ExportContext, config: ImageReportConfig | None = None) -> ImageReportData:
    cfg = config or ImageReportConfig()
    run_config = ctx.config if isinstance(ctx.config, dict) else {}
    title = cfg.title or str(
        run_config.get("image_report_title")
        or run_config.get("report_title")
        or build_report_title(run_config.get("super_topic_name"), run_config.get("super_topic"))
    )
    issue = cfg.issue or str(run_config.get("issue") or run_config.get("week_issue") or "").strip()
    if not issue:
        issue = str(calculate_weekly_issue(_issue_reference_date(run_config)))
    date_range = cfg.date_range or _date_range_from_config(run_config) or _format_posts_range(ctx.selected_posts)
    posts = [_build_post(ctx.run_dir, post, index) for index, post in enumerate(ctx.selected_posts, start=1)]
    return ImageReportData(title=title, issue=issue, date_range=date_range, posts=posts)


def _build_post(run_dir: Path, post: dict[str, Any], rank: int) -> PostBlock:
    top_comments = post.get("top_comments_data") if isinstance(post.get("top_comments_data"), list) else []
    comments: list[CommentBlock] = []
    for index, item in enumerate(iter_report_comments(post)):
        raw = top_comments[index] if index < len(top_comments) and isinstance(top_comments[index], dict) else {}
        comments.append(
            CommentBlock(
                user_name=normalize_weibo_text(str(item.get("user_name") or raw.get("user_name") or "")),
                text=clean_image_report_text(str(item.get("text") or "")),
                like_counts=_to_int(raw.get("like_counts") or raw.get("likes") or raw.get("like_count")),
                images=_image_assets(
                    run_dir,
                    split_multi_values(str(item.get("image_local_paths") or raw.get("image_local_paths") or ""), sep="|"),
                    f"热评配图 {rank}",
                ),
            )
        )

    images = _image_assets(
        run_dir,
        split_multi_values(str(post.get("image_local_paths") or ""), sep="|"),
        f"帖子配图 {rank}",
    )
    if not images and split_multi_values(str(post.get("original_image_urls") or ""), sep="|"):
        images.append(ImageAsset(alt=f"帖子配图 {rank}", note="图片未下载或本地路径缺失"))

    return PostBlock(
        rank=rank,
        post_id=str(post.get("post_id") or ""),
        author=normalize_weibo_text(str(post.get("user_name") or "未知作者")),
        publish_time=normalize_weibo_text(str(post.get("publish_time") or "")),
        content=clean_image_report_text(str(post.get("content") or "")),
        post_url=normalize_weibo_text(str(post.get("post_url") or "")),
        score=_to_float(post.get("score")),
        likes=_to_int(post.get("likes")),
        comments_count=_to_int(post.get("comments")),
        reposts=_to_int(post.get("reposts")),
        images=images,
        comments=comments,
    )


def _image_assets(run_dir: Path, paths: list[str], alt_prefix: str) -> list[ImageAsset]:
    assets: list[ImageAsset] = []
    for index, raw in enumerate(paths, start=1):
        path = Path(raw)
        if not path.is_absolute():
            path = run_dir / raw
        width, height = _image_size(path)
        exists = path.exists() and path.is_file()
        assets.append(
            ImageAsset(
                local_path=str(path),
                alt=f"{alt_prefix}-{index}",
                width=width,
                height=height,
                exists=exists,
                note="" if exists else "图片文件不存在",
            )
        )
    return assets


def _image_size(path: Path) -> tuple[int, int]:
    if not path.exists() or not path.is_file():
        return 0, 0
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def _date_range_from_config(config: dict[str, Any]) -> str:
    start = _parse_date(config.get("window_start"))
    end = _parse_date(config.get("window_end"))
    if not start or not end:
        return ""
    return f"{start.strftime('%Y.%m.%d')} - {end.strftime('%Y.%m.%d')}"


def calculate_weekly_issue(reference: datetime | None = None) -> int:
    """Issue 1 is anchored to Saturday 2026-04-25; weekdays count toward the upcoming Saturday."""
    ref = reference or datetime.now()
    target_saturday = ref + timedelta(days=(5 - ref.weekday()) % 7)
    weeks = (target_saturday.date() - ISSUE_ONE_SATURDAY.date()).days // 7
    return max(1, weeks + 1)


def _issue_reference_date(config: dict[str, Any]) -> datetime | None:
    return _parse_date(config.get("window_end")) or _parse_date(config.get("window_start"))


def _format_posts_range(posts: list[dict[str, Any]]) -> str:
    text = format_posts_date_range(posts)
    parts = [part.strip() for part in text.split(" 至 ", 1)]
    if len(parts) != 2:
        parts = [part.strip() for part in text.split(" - ", 1)]
    if len(parts) != 2:
        return text
    return f"{parts[0].replace('-', '.')} - {parts[1].replace('-', '.')}"


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
