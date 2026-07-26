from __future__ import annotations

import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from core.cache import CacheStore
from core.errors import JobCancelled
from modules.images.url_extract import dedup_image_urls, split_multi_urls

THUMBNAIL_DIR_NAME = "candidate_thumbnails"
DEFAULT_MAX_PER_POST = 3
DEFAULT_MAX_WORKERS = 4
THUMBNAIL_SIZE = (220, 220)


FetchBytes = Callable[[str, dict[str, str]], bytes | None]
CancelChecker = Callable[[], None]
ProgressCallback = Callable[[dict[str, Any]], None]


def build_candidate_thumbnails(
    posts: list[dict[str, Any]],
    cache_store: CacheStore,
    *,
    cookie: str = "",
    max_per_post: int = DEFAULT_MAX_PER_POST,
    max_workers: int = DEFAULT_MAX_WORKERS,
    fetch_bytes: FetchBytes | None = None,
    cancel_checker: CancelChecker | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Download lightweight thumbnails for candidate cards into the run cache."""
    thumbnail_dir = cache_store.cache_dir / THUMBNAIL_DIR_NAME
    tasks, post_image_counts = _thumbnail_tasks(posts, thumbnail_dir, max_per_post=max_per_post)
    for post in posts:
        post["candidate_thumbnail_urls"] = []
        post["candidate_thumbnail_count"] = 0
    _emit_progress(
        progress_callback,
        "start",
        "开始下载预选帖缩略图："
        f"候选 {len(posts)} 条，带图 {sum(1 for count in post_image_counts if count > 0)} 条，"
        f"计划缓存 {len(tasks)} 张（每帖最多 {max(1, int(max_per_post or DEFAULT_MAX_PER_POST))} 张）。",
        current=0,
        total=max(1, len(tasks)),
        payload={
            "candidate_count": len(posts),
            "image_post_count": sum(1 for count in post_image_counts if count > 0),
            "thumbnail_total": len(tasks),
        },
    )
    if not tasks:
        _emit_progress(progress_callback, "skip", "预选帖没有图片，跳过缩略图下载。", level="warning", current=1, total=1)
        return {"total": 0, "success": 0, "failed": 0, "dir": str(thumbnail_dir)}

    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    headers = _request_headers(cookie)
    workers = max(1, min(int(max_workers or DEFAULT_MAX_WORKERS), len(tasks)))
    success = 0
    failed = 0

    if workers == 1:
        results = []
        for task in tasks:
            result = _build_one_thumbnail(task, headers, fetch_bytes, cancel_checker, progress_callback)
            results.append(result)
            _emit_result_progress(progress_callback, result, len(results), len(tasks))
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="candidate-thumb") as executor:
            futures = [
                executor.submit(_build_one_thumbnail, task, headers, fetch_bytes, cancel_checker, progress_callback)
                for task in tasks
            ]
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                _emit_result_progress(progress_callback, result, len(results), len(tasks))

    results.sort(key=lambda item: (int(item.get("post_index") or 0), int(item.get("image_index") or 0)))
    for result in results:
        post_index = int(result.get("post_index") or 0)
        if result.get("ok"):
            success += 1
            if 0 <= post_index < len(posts):
                urls = posts[post_index].setdefault("candidate_thumbnail_urls", [])
                if isinstance(urls, list):
                    urls.append(_thumbnail_asset_url(cache_store.run_dir.name, str(result.get("rel_path") or "")))
        else:
            failed += 1

    for post in posts:
        urls = post.get("candidate_thumbnail_urls")
        if not isinstance(urls, list):
            urls = []
        post["candidate_thumbnail_urls"] = urls
        post["candidate_thumbnail_count"] = len(urls)
        post["candidate_thumbnail_paths"] = " | ".join(urls)

    cache_hits = sum(1 for item in results if item.get("source") == "cache")
    downloaded = sum(1 for item in results if item.get("source") == "download")
    _emit_progress(
        progress_callback,
        "done",
        "预选帖缩略图缓存完成："
        f"成功 {success}/{len(tasks)} 张，新下载 {downloaded} 张，缓存命中 {cache_hits} 张，失败 {failed} 张。",
        level="success" if success else "warning",
        current=len(tasks),
        total=max(1, len(tasks)),
        payload={"success": success, "failed": failed, "cache_hits": cache_hits, "downloaded": downloaded},
    )
    return {
        "total": len(tasks),
        "success": success,
        "failed": failed,
        "cache_hits": cache_hits,
        "downloaded": downloaded,
        "dir": str(thumbnail_dir),
    }


def _thumbnail_tasks(
    posts: list[dict[str, Any]],
    thumbnail_dir: Path,
    *,
    max_per_post: int,
) -> tuple[list[dict[str, Any]], list[int]]:
    tasks: list[dict[str, Any]] = []
    post_image_counts: list[int] = []
    limit = max(1, int(max_per_post or DEFAULT_MAX_PER_POST))
    for post_index, post in enumerate(posts):
        all_urls = dedup_image_urls(split_multi_urls(str(post.get("original_image_urls") or ""), sep="|"))
        post_image_counts.append(len(all_urls))
        for image_index, url in enumerate(all_urls[:limit], start=1):
            digest = hashlib.md5(url.encode("utf-8")).hexdigest()
            filename = f"candidate_{post_index + 1:02d}_{image_index}_{digest[:12]}.jpg"
            tasks.append(
                {
                    "post_index": post_index,
                    "post_rank": post_index + 1,
                    "image_index": image_index,
                    "post_image_count": len(all_urls),
                    "post_id": str(post.get("post_id") or ""),
                    "user_name": str(post.get("user_name") or "未知作者"),
                    "url": url,
                    "path": thumbnail_dir / filename,
                    "rel_path": f"{THUMBNAIL_DIR_NAME}/{filename}",
                }
            )
    return tasks, post_image_counts


def _build_one_thumbnail(
    task: dict[str, Any],
    headers: dict[str, str],
    fetch_bytes: FetchBytes | None,
    cancel_checker: CancelChecker | None,
    progress_callback: ProgressCallback | None,
) -> dict[str, Any]:
    if cancel_checker:
        cancel_checker()
    _emit_task_start_progress(progress_callback, task)
    path = Path(task["path"])
    if path.exists() and path.is_file():
        return {**task, "ok": True, "source": "cache"}
    try:
        raw = fetch_bytes(str(task["url"]), headers) if fetch_bytes else _fetch_bytes(str(task["url"]), headers)
        if not raw:
            return {**task, "ok": False, "error": "empty image response"}
        _save_thumbnail(raw, path)
        return {**task, "ok": True, "source": "download"}
    except JobCancelled:
        raise
    except (OSError, requests.RequestException, UnidentifiedImageError) as err:
        return {**task, "ok": False, "error": f"{type(err).__name__}: {err}"}
    except Exception as err:
        return {**task, "ok": False, "error": f"{type(err).__name__}: {err}"}


def _fetch_bytes(url: str, headers: dict[str, str]) -> bytes | None:
    response = requests.get(url, headers=headers, timeout=(5, 15))
    if response.status_code != 200:
        return None
    return response.content


def _save_thumbnail(raw: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(path, format="JPEG", quality=82, optimize=True)


def _request_headers(cookie: str) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://weibo.com/",
    }
    clean_cookie = str(cookie or "").strip()
    if clean_cookie:
        headers["Cookie"] = clean_cookie
    return headers


def _emit_result_progress(
    progress_callback: ProgressCallback | None,
    result: dict[str, Any],
    current: int,
    total: int,
) -> None:
    source = "缓存命中" if result.get("source") == "cache" else "下载完成"
    level = "success"
    if not result.get("ok"):
        source = f"下载失败：{result.get('error') or '未知错误'}"
        level = "warning"
    user_name = str(result.get("user_name") or "未知作者")
    post_rank = int(result.get("post_rank") or int(result.get("post_index") or 0) + 1)
    image_index = int(result.get("image_index") or 1)
    image_total = int(result.get("post_image_count") or image_index)
    post_id = str(result.get("post_id") or "-")
    _emit_progress(
        progress_callback,
        "item",
        f"预选帖缩略图 {current}/{total}：#{post_rank} {user_name}，图 {image_index}/{image_total}，{source}（post_id: {post_id}）。",
        level=level,
        current=current,
        total=total,
        payload={
            "post_rank": post_rank,
            "post_id": post_id,
            "image_index": image_index,
            "image_total": image_total,
            "ok": bool(result.get("ok")),
            "source": str(result.get("source") or ""),
            "path": str(result.get("path") or ""),
        },
    )


def _emit_task_start_progress(progress_callback: ProgressCallback | None, task: dict[str, Any]) -> None:
    user_name = str(task.get("user_name") or "未知作者")
    post_rank = int(task.get("post_rank") or int(task.get("post_index") or 0) + 1)
    image_index = int(task.get("image_index") or 1)
    image_total = int(task.get("post_image_count") or image_index)
    post_id = str(task.get("post_id") or "-")
    _emit_progress(
        progress_callback,
        "item_start",
        f"准备处理预选帖缩略图：#{post_rank} {user_name}，图 {image_index}/{image_total}，检查缓存并下载（post_id: {post_id}）。",
        level="info",
        payload={
            "post_rank": post_rank,
            "post_id": post_id,
            "image_index": image_index,
            "image_total": image_total,
        },
    )


def _emit_progress(
    progress_callback: ProgressCallback | None,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    current: int | None = None,
    total: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if progress_callback:
        progress_callback(
            {
                "type": event_type,
                "message": message,
                "level": level,
                "current": current,
                "total": total,
                "payload": payload or {},
            }
        )


def _thumbnail_asset_url(run_id: str, rel_path: str) -> str:
    clean_rel_path = str(rel_path or "").replace("\\", "/")
    return (
        "/api/candidate-thumbnail?"
        f"run_id={quote(str(run_id or ''), safe='')}&path={quote(clean_rel_path, safe='/')}"
    )
