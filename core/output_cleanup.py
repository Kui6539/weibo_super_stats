from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.cache import CacheStore, read_manifest, sanitize_for_cache
from core.errors import ConfigError
from core.history import ROOT_DIR
from core.paths import RUN_DIR_RE, is_relative_to


def output_summary(output_dir: str | Path = "output") -> dict[str, Any]:
    root = resolve_output_root(output_dir)
    run_dirs = list_run_dirs(root)
    rows = [_summarize_run_dir(path) for path in run_dirs]
    total_size = sum(int(row.get("size") or 0) for row in rows)
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
    selected_run_ids: list[str] | None = None,
) -> dict[str, Any]:
    root = resolve_output_root(output_dir)
    run_dirs = list_run_dirs(root)
    keep_recent = max(0, int(keep_recent or 0))
    older_limit = datetime.now() - timedelta(days=max(0, int(older_than_days or 0))) if older_than_days else None

    protected = set(run_dirs[:keep_recent])
    selected_override = set(str(item) for item in selected_run_ids) if selected_run_ids is not None else None
    all_rows: list[dict[str, Any]] = []

    for run_dir in run_dirs:
        summary = _summarize_run_dir(run_dir)
        meets_rules = _matches_cleanup_rules(
            run_dir,
            summary,
            protected=protected,
            older_limit=older_limit,
            incomplete_only=incomplete_only,
            include_warnings=include_warnings,
            include_failed=include_failed,
        )
        cache_incomplete = not summary.get("can_reexport")
        output_complete = bool(summary.get("output_files_complete"))
        output_incomplete = not output_complete
        abnormal_dir = cache_incomplete and output_incomplete
        always_visible_normal = cache_incomplete and output_complete
        should_display = abnormal_dir or always_visible_normal or meets_rules
        if not should_display:
            continue
        default_selected = _default_cleanup_selected(
            cache_incomplete=cache_incomplete,
            abnormal_dir=abnormal_dir,
            output_incomplete=output_incomplete,
            output_complete=output_complete,
            meets_rules=meets_rules,
        )
        selected = (summary["run_id"] in selected_override) if selected_override is not None else default_selected
        summary = {
            **summary,
            "directory_kind": _directory_kind(cache_incomplete, output_complete),
            "cleanup_eligible": meets_rules,
            "selected": selected,
            "selected_by_default": default_selected,
            "cleanup_reason": _cleanup_reason(cache_incomplete, output_incomplete, meets_rules),
        }
        all_rows.append(summary)

    delete_rows = [row for row in all_rows if row.get("selected")]
    total_size = sum(int(row.get("size") or 0) for row in delete_rows)
    return sanitize_for_cache(
        {
            "output_dir": _rel_project(root),
            "delete_count": len(delete_rows),
            "scanned_count": len(all_rows),
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "items": delete_rows,
            "all_items": all_rows,
        }
    )


def _matches_cleanup_rules(
    run_dir: Path,
    summary: dict[str, Any],
    *,
    protected: set[Path],
    older_limit: datetime | None,
    incomplete_only: bool,
    include_warnings: bool,
    include_failed: bool,
) -> bool:
    if run_dir in protected:
        return False
    if older_limit and _run_time(run_dir) and _run_time(run_dir) > older_limit:
        return False
    if incomplete_only and summary.get("can_reexport"):
        return False
    if summary.get("warnings_count") and not include_warnings:
        return False
    if summary.get("status") in {"failed", "cancelled", "partial"} and not include_failed:
        return False
    return True


def _default_cleanup_selected(
    *,
    cache_incomplete: bool,
    abnormal_dir: bool,
    output_incomplete: bool,
    output_complete: bool,
    meets_rules: bool,
) -> bool:
    if abnormal_dir:
        return True
    if cache_incomplete and output_complete:
        return meets_rules
    if output_incomplete:
        return meets_rules
    if output_complete:
        return meets_rules
    return False


def _directory_kind(cache_incomplete: bool, output_complete: bool) -> str:
    if cache_incomplete and not output_complete:
        return "abnormal"
    if cache_incomplete and output_complete:
        return "cache_incomplete_output_complete"
    if not cache_incomplete and output_complete:
        return "normal_complete"
    return "output_incomplete_recoverable"


def _cleanup_reason(
    cache_incomplete: bool,
    output_incomplete: bool,
    meets_rules: bool,
) -> str:
    reasons: list[str] = []
    if output_incomplete:
        reasons.append("输出文件不完整")
    if cache_incomplete:
        reasons.append("缓存不完整")
    if meets_rules:
        reasons.append("符合清理规则")
    if not reasons:
        reasons.append("不符合当前清理规则")
    return "，".join(reasons)


def cleanup_output(
    output_dir: str | Path = "output",
    confirm: bool = False,
    selected_run_ids: list[str] | None = None,
    **rules: Any,
) -> dict[str, Any]:
    preview = cleanup_preview(output_dir=output_dir, selected_run_ids=selected_run_ids, **rules)
    if not confirm:
        return {**preview, "deleted": False, "message": "未确认删除，仅返回预览。"}
    root = resolve_output_root(output_dir)
    deleted: list[str] = []
    deleted_caches: list[str] = []
    errors: list[str] = []
    for item in list(preview.get("items") or []):
        run_dir = (ROOT_DIR / str(item.get("report_dir") or "")).resolve()
        if not is_relative_to(run_dir, root) or not RUN_DIR_RE.match(run_dir.name):
            continue
        # A locked file in one run directory must not abort the whole batch:
        # earlier entries are already gone and the caller would otherwise get a
        # single opaque error with no idea what was removed.
        try:
            shutil.rmtree(run_dir, ignore_errors=False)
        except OSError as err:
            errors.append(f"{_rel_project(run_dir)}: {type(err).__name__}")
            continue
        deleted.append(_rel_project(run_dir))
        cache_dir = _project_cache_dir_for(run_dir)
        if not cache_dir:
            continue
        try:
            shutil.rmtree(cache_dir, ignore_errors=False)
        except OSError as err:
            errors.append(f"{_rel_project(cache_dir)}: {type(err).__name__}")
            continue
        deleted_caches.append(_rel_project(cache_dir))
    message = f"已删除 {len(deleted)} 个运行目录。"
    if deleted_caches:
        message += f"同时清理了 {len(deleted_caches)} 个缓存目录。"
    if errors:
        message += f"{len(errors)} 项删除失败（文件可能正被打开）。"
    return {
        **preview,
        "deleted": True,
        "deleted_dirs": deleted,
        "deleted_cache_dirs": deleted_caches,
        "errors": errors,
        "message": message,
    }


def _project_cache_dir_for(run_dir: Path) -> Path | None:
    """The project-root cache directory belonging to *run_dir*, if safe to drop.

    Deleting an output directory used to orphan its cache: tens of megabytes of
    comment JSON and thumbnails with no UI left to reach them. Guarded the same
    way as the output side — must sit directly under the cache root and carry a
    run-directory name.
    """
    store = CacheStore(run_dir)
    cache_dir = store.project_cache_dir.resolve()
    if not cache_dir.exists() or not cache_dir.is_dir():
        return None
    if cache_dir.name != run_dir.name or not RUN_DIR_RE.match(cache_dir.name):
        return None
    if cache_dir.parent != store.cache_root.resolve():
        return None
    return cache_dir


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
    store = CacheStore(run_dir)
    cache_status = store.get_cache_status()
    warnings = manifest.get("warnings") if isinstance(manifest, dict) else []
    output_status = _output_files_status(run_dir, manifest if isinstance(manifest, dict) else {})
    # rglob is the expensive part here; walk each tree once and reuse the total.
    output_size = _dir_size(run_dir)
    cache_dir = store.project_cache_dir
    cache_size = _dir_size(cache_dir) if cache_dir.exists() and cache_dir != run_dir else 0
    size = output_size + cache_size
    return {
        "run_id": run_dir.name,
        "report_dir": _rel_project(run_dir),
        "status": str(manifest.get("status") or "unknown") if isinstance(manifest, dict) else "unknown",
        "created_at": str(manifest.get("created_at") or _run_time_text(run_dir)) if isinstance(manifest, dict) else _run_time_text(run_dir),
        "updated_at": str(manifest.get("updated_at") or "") if isinstance(manifest, dict) else "",
        "size": size,
        "size_mb": round(size / 1024 / 1024, 2),
        "output_size": output_size,
        "cache_size": cache_size,
        "has_cache": bool(cache_status.get("has_cache")),
        "can_reexport": bool(cache_status.get("can_reexport")),
        "output_files_known": bool(output_status.get("known")),
        "output_files_complete": bool(output_status.get("complete")),
        "missing_output_files": list(output_status.get("missing") or []),
        "existing_output_files": list(output_status.get("existing") or []),
        "expected_output_files": list(output_status.get("expected") or []),
        "warnings_count": len(list(warnings or [])),
        "failed_images_count": int((manifest or {}).get("failed_image_count") or 0) if isinstance(manifest, dict) else 0,
    }


def _output_files_status(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    expected = _manifest_output_paths(files)
    if not expected:
        expected = _fallback_output_paths(run_dir)
    known = bool(expected)
    existing: list[str] = []
    missing: list[str] = []
    for rel_path in expected:
        target = (run_dir / rel_path).resolve()
        if not is_relative_to(target, run_dir.resolve()):
            missing.append(rel_path)
            continue
        if target.exists():
            existing.append(rel_path)
        else:
            missing.append(rel_path)
    return {
        "complete": bool(expected) and not missing,
        "known": known,
        "expected": expected,
        "existing": existing,
        "missing": missing,
    }


def _manifest_output_paths(files: dict[str, Any]) -> list[str]:
    rows: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip().replace("\\", "/")
        if text and text not in rows:
            rows.append(text)

    for key in (
        "markdown",
        "excel",
        "xlsx",
        "csv",
        "summary",
        "weibo_body",
        "docx_sum",
        "images_dir",
        "images",
        "image_report_preview",
        "image_report_metadata",
    ):
        add(files.get(key))
    for list_key in ("docx", "image_report_pages"):
        value = files.get(list_key)
        if isinstance(value, list):
            for item in value:
                add(item)
        else:
            add(value)
    return rows


def _fallback_output_paths(run_dir: Path) -> list[str]:
    core_names = ("weekly_report.md", "weibo_posts.xlsx", "weibo_posts.csv", "weibo_summary.txt")
    docx_files = sorted(path.name for path in run_dir.glob("weekly_report*.docx"))
    has_known_output = any((run_dir / name).exists() for name in core_names) or bool(docx_files) or (run_dir / "images").exists()
    if not has_known_output:
        return []
    expected = list(core_names)
    expected.extend(docx_files)
    if (run_dir / "images").exists():
        expected.append("images")
    return expected


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
