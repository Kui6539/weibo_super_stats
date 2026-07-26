"""Builds the images manifest recorded for a run.

This module previously held a second, unrelated ``build_images_manifest`` that
took pre-built ``{"ok": ...}`` rows and wrote them to ``run_dir/cache/`` -- the
legacy cache location the project moved away from. Nothing in production ever
called it; the real implementation lived in ``core/job.py``, so anyone who
followed the package layout to find it got the wrong one. The production
implementation now lives here and the misleading pair is gone: persistence goes
through ``CacheStore.write_stage("images_manifest", ...)`` like every other
stage file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.post_normalizer import split_multi_value

SCHEMA_VERSION = 1

POST_IMAGE = "post_image"
COMMENT_IMAGE = "comment_image"


def build_images_manifest(run_dir: Path, posts: list[dict]) -> dict[str, Any]:
    """Record which of a run's images made it to disk and which did not.

    Paths are stored relative to *run_dir* so a moved or shared output
    directory stays readable.
    """
    success: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for post in posts:
        _add_rows(
            success,
            failed,
            run_dir,
            post,
            split_multi_value(post.get("original_image_urls")),
            split_multi_value(post.get("image_local_paths")),
            POST_IMAGE,
        )
        for comment in list(post.get("top_comments_data") or []):
            _add_rows(
                success,
                failed,
                run_dir,
                post,
                split_multi_value(comment.get("image_urls")),
                split_multi_value(comment.get("image_local_paths")),
                COMMENT_IMAGE,
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "success": success,
        "failed": failed,
        "success_count": len(success),
        "failed_count": len(failed),
    }


def _add_rows(
    success: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    run_dir: Path,
    post: dict,
    urls: list[str],
    paths: list[str],
    image_type: str,
) -> None:
    post_id = str(post.get("post_id") or "")
    for index, path_text in enumerate(paths):
        row = {
            "post_id": post_id,
            "type": image_type,
            "url": urls[index] if index < len(urls) else "",
            "local_path": _relative_to_run(run_dir, path_text),
        }
        (success if Path(path_text).exists() else failed).append(row)
    # More URLs than files means the tail never downloaded at all.
    if len(urls) > len(paths):
        failed.extend(
            {"post_id": post_id, "type": image_type, "url": url, "local_path": ""}
            for url in urls[len(paths) :]
        )


def _relative_to_run(run_dir: Path, path_text: str) -> str:
    try:
        return str(Path(path_text).resolve().relative_to(run_dir.resolve())).replace("\\", "/")
    except (ValueError, OSError):
        return str(path_text).replace("\\", "/")
