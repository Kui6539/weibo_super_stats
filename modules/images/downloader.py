from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import requests

from .collect import collect_comment_images, collect_post_images
from .paths import build_image_filename, build_image_folder_name


def download_image(url: str, dest: Path, client: Any = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    if client is not None and hasattr(client, "download_file"):
        return Path(client.download_file(url, dest))
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def download_images_for_post(
    post: dict[str, Any],
    output_dir: Path,
    rank: int = 1,
    client: Any = None,
) -> list[dict[str, Any]]:
    post_id = str(post.get("post_id") or "")
    post_dir = output_dir / build_image_folder_name(rank, str(post.get("user_name") or ""), post_id)
    results: list[dict[str, Any]] = []
    post_paths: list[str] = []
    comment_paths: list[str] = []

    for item in collect_post_images(post):
        result = _download_collected(item, post_dir, client)
        results.append(result)
        if result.get("ok"):
            post_paths.append(str(result["path"]))

    comments = post.get("top_comments_data") if isinstance(post.get("top_comments_data"), list) else []
    for item in collect_comment_images(post):
        item["type"] = "comment_image"
        result = _download_collected(item, post_dir, client)
        results.append(result)
        if result.get("ok"):
            comment_paths.append(str(result["path"]))
            comment_index = int(item.get("comment_index") or 0) - 1
            if 0 <= comment_index < len(comments) and isinstance(comments[comment_index], dict):
                existing = _split_paths(comments[comment_index].get("image_local_paths"))
                comments[comment_index]["image_local_paths"] = " | ".join(existing + [str(result["path"])])

    post["downloaded_image_count"] = len(post_paths)
    post["image_local_paths"] = " | ".join(post_paths)
    post["top_comments_data"] = comments
    post["downloaded_comment_image_count"] = len(comment_paths)
    post["comment_image_local_paths"] = " | ".join(comment_paths)
    post["image_local_paths_all"] = " | ".join(post_paths + comment_paths)
    return results


def download_selected_images(
    selected_posts: list[dict[str, Any]],
    output_dir: Path,
    client: Any = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    total = len(selected_posts)
    for rank, post in enumerate(selected_posts, start=1):
        if progress_callback:
            progress_callback(f"下载图片进度 {rank}/{total}: {post.get('post_id') or '-'}")
        all_results.extend(download_images_for_post(post, output_dir, rank=rank, client=client))
    return all_results


def _download_collected(item: dict[str, Any], post_dir: Path, client: Any = None) -> dict[str, Any]:
    url = str(item.get("url") or "")
    filename = build_image_filename(int(item.get("index") or 1), url, str(item.get("type") or "post"))
    dest = post_dir / filename
    try:
        path = download_image(url, dest, client=client)
        return {**item, "ok": True, "path": str(path), "local_path": str(path)}
    except Exception as err:
        return {**item, "ok": False, "error": f"{type(err).__name__}: {err}"}


def _split_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value]
    else:
        parts = [part.strip() for part in str(value or "").replace("\n", "|").split("|")]
    return [part for part in parts if part]
