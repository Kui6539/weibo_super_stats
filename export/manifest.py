from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from core.cache import sanitize_for_cache, write_manifest_json
from crawler import parse_super_topic_id
from export.context import ExportContext


def build_manifest(
    ctx: ExportContext,
    files: dict[str, Any],
    warnings: list[str] | None = None,
    failed_images: int | None = None,
    previous: dict[str, Any] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    run_dir = ctx.run_dir.resolve()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    previous = previous if isinstance(previous, dict) else {}
    run_id = run_dir.name
    config = sanitize_for_cache(ctx.config or {})
    super_topic = str(config.get("super_topic") or "")
    reexport_count = int(previous.get("reexport_count") or 0)
    if ctx.reexport:
        reexport_count += 1

    failed_image_count = int(failed_images or 0)
    failed_image_rows = []
    if isinstance(ctx.images_manifest, dict):
        failed_image_rows = list(ctx.images_manifest.get("failed") or [])
        if not failed_image_count:
            failed_image_count = len(failed_image_rows)

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": str(previous.get("created_at") or now),
        "updated_at": now,
        "tool": "weibo_super_stats",
        "super_topic": super_topic,
        "super_topic_id": str(config.get("super_topic_id") or parse_super_topic_id(super_topic) or ""),
        "window_start": str(config.get("window_start") or ""),
        "window_end": str(config.get("window_end") or ""),
        "selected_count": len(ctx.selected_posts),
        "total_posts": int(ctx.stats.get("total_posts") or len(ctx.all_posts)),
        "candidate_count": int(config.get("candidate_count") or previous.get("candidate_count") or 0),
        "status": status,
        "files": {
            "markdown": _rel(run_dir, files.get("markdown")),
            "docx": [_rel(run_dir, path) for path in files.get("docx", []) or []],
            "docx_sum": _rel(run_dir, files.get("docx_sum")),
            "excel": _rel(run_dir, files.get("xlsx") or files.get("excel")),
            "xlsx": _rel(run_dir, files.get("xlsx") or files.get("excel")),
            "csv": _rel(run_dir, files.get("csv")),
            "summary": _rel(run_dir, files.get("summary")),
            "images_dir": _rel(run_dir, files.get("images") or files.get("images_dir")),
            "images": _rel(run_dir, files.get("images") or files.get("images_dir")),
        },
        "cache": {
            "run_config": "cache/run_config.json",
            "posts_raw": "cache/posts_raw.json",
            "posts_hydrated": "cache/posts_hydrated.json",
            "posts_scored": "cache/posts_scored.json",
            "candidates": "cache/candidates.json",
            "selected_posts": "cache/selected_posts.json",
            "community_stats": "cache/community_stats.json",
            "images_manifest": "cache/images_manifest.json",
            "comments_dir": "cache/comments",
        },
        "warnings": list(warnings or []),
        "failed_image_count": failed_image_count,
        "failed_images": failed_image_rows,
        "reexport_count": reexport_count,
        "last_reexport_at": now if ctx.reexport else previous.get("last_reexport_at"),
        "stats": dict(ctx.stats or {}),
    }
    return sanitize_for_cache(manifest)


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    return write_manifest_json(run_dir, manifest)


def _rel(run_dir: Path, raw_path: Any) -> str | None:
    if raw_path is None:
        return None
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text)
    try:
        if path.is_absolute():
            return str(path.resolve().relative_to(run_dir.resolve())).replace("\\", "/")
    except Exception:
        return text.replace("\\", "/")
    return text.replace("\\", "/")

