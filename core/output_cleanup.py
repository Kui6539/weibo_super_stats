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
    output_status = _output_files_status(run_dir, manifest if isinstance(manifest, dict) else {})
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

    for key in ("markdown", "excel", "xlsx", "csv", "summary", "docx_sum", "images_dir", "images"):
        add(files.get(key))
    docx = files.get("docx")
    if isinstance(docx, list):
        for item in docx:
            add(item)
    else:
        add(docx)
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
