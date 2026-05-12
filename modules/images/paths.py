from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


def build_image_folder_name(rank: int, author: str, post_id: str) -> str:
    safe_author = sanitize_image_path_part(author) or "未知作者"
    safe_post_id = sanitize_image_path_part(post_id)
    suffix = f"_{safe_post_id}" if safe_post_id else ""
    return f"{max(1, int(rank)):02d}_{safe_author}{suffix}"


def build_image_filename(index: int, url: str, image_type: str = "post") -> str:
    prefix = "comment" if image_type == "comment_image" else "post"
    digest = hashlib.md5(str(url or "").encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{max(1, int(index)):02d}_{digest}{_guess_ext(url)}"


def sanitize_image_path_part(value: str) -> str:
    raw = " ".join(str(value or "").split())
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("._ ")
    return (raw or "item")[:48]


def _guess_ext(url: str) -> str:
    path = urlparse(str(url or "")).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"
