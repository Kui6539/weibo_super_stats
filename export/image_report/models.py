from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageReportConfig:
    title: str = ""
    issue: str = ""
    date_range: str = ""
    width: int = 1080
    max_page_height: int = 8500
    jpg_quality: int = 90
    max_pages: int = 9
    max_posts_per_page: int = 5
    render_jpg: bool = True
    render_weibo_emoticons: bool = True
    # Fetch only the emoticons this report actually uses. Defaulting to the
    # whole index pulled hundreds of files over eight threads during the
    # export stage of every first run, for images that would never be
    # rendered, and flooded the warnings list when any of them failed.
    download_all_emoticons: bool = False
    font_path: str = ""
    browser_channel: str = "msedge"

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None = None) -> ImageReportConfig:
        raw = value if isinstance(value, dict) else {}
        cfg = cls()
        for key in (
            "title",
            "issue",
            "date_range",
            "font_path",
            "browser_channel",
        ):
            if key in raw:
                setattr(cfg, key, str(raw.get(key) or "").strip())
        for key in ("width", "max_page_height", "jpg_quality", "max_pages", "max_posts_per_page"):
            if key in raw:
                try:
                    setattr(cfg, key, int(raw.get(key)))
                except (TypeError, ValueError):
                    pass
        for key in ("render_jpg", "render_weibo_emoticons", "download_all_emoticons"):
            if key in raw:
                setattr(cfg, key, _as_bool(raw.get(key)))
        cfg.width = max(720, min(cfg.width, 1600))
        cfg.max_page_height = max(2400, min(cfg.max_page_height, 12000))
        cfg.jpg_quality = max(60, min(cfg.jpg_quality, 95))
        cfg.max_pages = max(1, min(cfg.max_pages, 9))
        cfg.max_posts_per_page = max(1, min(cfg.max_posts_per_page, 5))
        return cfg


@dataclass
class ImageAsset:
    local_path: str = ""
    alt: str = ""
    width: int = 0
    height: int = 0
    exists: bool = False
    note: str = ""


@dataclass
class CommentBlock:
    user_name: str = ""
    text: str = ""
    like_counts: int = 0
    images: list[ImageAsset] = field(default_factory=list)


@dataclass
class PostBlock:
    rank: int
    post_id: str
    author: str
    publish_time: str
    content: str
    post_url: str = ""
    score: float = 0.0
    likes: int = 0
    comments_count: int = 0
    reposts: int = 0
    images: list[ImageAsset] = field(default_factory=list)
    comments: list[CommentBlock] = field(default_factory=list)
    estimated_height: int = 0


@dataclass
class PageBlock:
    number: int
    posts: list[PostBlock]
    estimated_height: int
    actual_height: int = 0
    jpg_path: str = ""


@dataclass
class ImageReportData:
    title: str
    issue: str
    date_range: str
    posts: list[PostBlock]
    emoticons: dict[str, str] = field(default_factory=dict)


@dataclass
class ImageReportResult:
    preview: Path
    pages: list[Path]
    metadata: Path
    warnings: list[str]
    page_count: int


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "是"}
