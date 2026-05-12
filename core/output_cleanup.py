from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.cache import CacheStore, read_manifest, sanitize_for_cache
from core.errors import ConfigError
from core.history import ROOT_DIR
from core.paths import is_relative_to

RUN_DIR_RE = re.compile(r"^\d{8}_\d{6}$")


def output_summary(output_dir: str | Path = "output") -> dict[str, Any]:
    root = resolve_output_root(output_dir)
    run_dirs = list_run_dirs(root)
    total_size = sum(_dir_size(path) for path in run_dirs)
    rows = [_summarize_run_dir(path) for path in run_dirs]
    return sanitize_for_cache(
        {
            "output_dir": _rel_project(root),
            "run_count": len(run_dirs),
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "can_reexport_count": sum(1 for row in rows if row.get("can_reexport")),
            "warning_count": sum(1 for row in rows if row.get("warnings_count")),
            "failed_count": sum(1 for row in rows if row.get("status") in {"failed", "cancelled", "partial"}),
            "items": rows,
        }
    )


def cleanup_preview(
    output_dir: str | Path = "output",
    older_than_days: int | None = None,
    keep_recent: int = 5,
    incomplete_only: bool = False,
    include_warnings: bool = False,
    include_failed: bool = False,
) -> dict[str, Any]:
    root = resolve_output_root(output_dir)
    run_dirs = list_run_dirs(root)
    keep_recent = max(0, int(keep_recent or 0))
    older_limit = datetime.now() - timedelta(days=max(0, int(older_than_days or 0))) if older_than_days else None

    complete_dirs = [d for d in run_dirs if _summarize_run_dir(d).get("can_reexport")]
    protected = set(complete_dirs[:keep_recent])
    delete_rows: list[dict[str, Any]] = []

    for run_dir in run_dirs:
        summary = _summarize_run_dir(run_dir)
        cache_incomplete = not summary.get("can_reexport")
        if cache_incomplete:
            delete_rows.append(summary)
            continue
        if run_dir in protected:
            continue
        if older_limit and _run_time(run_dir) and _run_time(run_dir) > older_limit:
            continue
        if incomplete_only:
            continue
        if summary.get("warnings_count") and not include_warnings:
            continue
        if summary.get("status") in {"failed", "cancelled", "partial"} and not include_failed:
            continue
        delete_rows.append(summary)

    total_size = sum(int(row.get("size") or 0) for row in delete_rows)
    return sanitize_for_cache(
        {
            "output_dir": _rel_project(root),
            "delete_count": len(delete_rows),
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "items": delete_rows,
        }
    )


def cleanup_output(
    output_dir: str | Path = "output",
    confirm: bool = False,
    **rules: Any,
) -> dict[str, Any]:
    preview = cleanup_preview(output_dir=output_dir, **rules)
    if not confirm:
        return {**preview, "deleted": False, "message": "未确认删除，仅返回预览。"}
    root = resolve_output_root(output_dir)
    deleted: list[str] = []
    for item in list(preview.get("items") or []):
        run_dir = (ROOT_DIR / str(item.get("report_dir") or "")).resolve()
        if not is_relative_to(run_dir, root) or not RUN_DIR_RE.match(run_dir.name):
            continue
        shutil.rmtree(run_dir, ignore_errors=False)
        deleted.append(_rel_project(run_dir))
    return {**preview, "deleted": True, "deleted_dirs": deleted, "message": f"已删除 {len(deleted)} 个运行目录。"}


def list_run_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    rows = [path for path in root.iterdir() if path.is_dir() and RUN_DIR_RE.match(path.name)]
    return sorted(rows, key=lambda path: path.name, reverse=True)


def resolve_output_root(output_dir: str | Path) -> Path:
    path = Path(output_dir or "output").expanduser()
    path = (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()
    default_output = (ROOT_DIR / "output").resolve()
    if not is_relative_to(path, default_output) and path != default_output:
        raise ConfigError("输出目录不在允许范围内", "输出清理只能处理项目 output 目录下的运行目录。")
    return path


def _summarize_run_dir(run_dir: Path) -> dict[str, Any]:
    manifest = read_manifest(run_dir, {}) or {}
    cache_status = CacheStore(run_dir).get_cache_status()
    warnings = manifest.get("warnings") if isinstance(manifest, dict) else []
    return {
        "run_id": run_dir.name,
        "report_dir": _rel_project(run_dir),
        "status": str(manifest.get("status") or "unknown") if isinstance(manifest, dict) else "unknown",
        "created_at": str(manifest.get("created_at") or _run_time_text(run_dir)) if isinstance(manifest, dict) else _run_time_text(run_dir),
        "updated_at": str(manifest.get("updated_at") or "") if isinstance(manifest, dict) else "",
        "size": _dir_size(run_dir),
        "size_mb": round(_dir_size(run_dir) / 1024 / 1024, 2),
        "has_cache": bool(cache_status.get("has_cache")),
        "can_reexport": bool(cache_status.get("can_reexport")),
        "warnings_count": len(list(warnings or [])),
        "failed_images_count": int((manifest or {}).get("failed_image_count") or 0) if isinstance(manifest, dict) else 0,
    }


def _dir_size(path: Path) -> int:
    total = 0
    for file in path.rglob("*"):
        if file.is_file():
            try:
                total += file.stat().st_size
            except OSError:
                continue
    return total


def _run_time(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _run_time_text(path: Path) -> str:
    value = _run_time(path)
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _rel_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")
