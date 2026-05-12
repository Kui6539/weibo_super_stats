from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.cache import CacheStore, read_manifest, sanitize_for_cache
from core.config import load_saved_config
from core.errors import ConfigError
from core.paths import is_relative_to, normalize_output_dir

ROOT_DIR = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT_DIR / "weibo_stats_history.json"
HISTORY_VERSION = 1


def load_history(path: Path | None = None) -> dict[str, Any]:
    history_path = path or HISTORY_PATH
    if not history_path.exists():
        return _empty_history()
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("history root is not object")
        return sanitize_history(data)
    except Exception:
        _backup_broken_history(history_path)
        return _empty_history()


def save_history(history: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    history_path = path or HISTORY_PATH
    clean = sanitize_history(history)
    history_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return clean


def add_history_item_from_manifest(report_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    history = load_history()
    item = history_item_from_manifest(report_dir, manifest)
    items = [row for row in history.get("items", []) if row.get("run_id") != item["run_id"]]
    items.append(item)
    history["items"] = _sort_items(items)
    history["updated_at"] = _now()
    return save_history(history)


def scan_output_history(output_dir: str | Path = "output") -> dict[str, Any]:
    import re
    run_dir_re = re.compile(r"^\d{8}_\d{6}$")
    root = _resolve_output_root(output_dir)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    scanned = 0
    seen_dirs: set[Path] = set()
    if root.exists():
        for manifest_path in sorted(root.glob("*/manifest.json")):
            report_dir = manifest_path.parent
            seen_dirs.add(report_dir)
            scanned += 1
            try:
                manifest = read_manifest(report_dir, {})
                if not isinstance(manifest, dict) or not manifest:
                    raise ValueError("manifest is empty")
                items.append(history_item_from_manifest(report_dir, manifest))
            except Exception as err:
                warnings.append(f"{report_dir.name}: manifest 读取失败：{type(err).__name__}")
        for run_dir in sorted(root.iterdir()):
            if not run_dir.is_dir() or not run_dir_re.match(run_dir.name):
                continue
            if run_dir in seen_dirs:
                continue
            scanned += 1
            items.append(_incomplete_history_item(run_dir))
    history = save_history({"version": HISTORY_VERSION, "updated_at": _now(), "items": _sort_items(items)})
    return {"history": history, "items": history["items"], "scanned": scanned, "warnings": warnings}


def remove_history_item(run_id: str) -> dict[str, Any]:
    history = load_history()
    clean_id = str(run_id or "").strip()
    history["items"] = [item for item in history.get("items", []) if item.get("run_id") != clean_id]
    history["updated_at"] = _now()
    return save_history(history)


def get_history_items() -> list[dict[str, Any]]:
    return list(load_history().get("items", []))


def find_history_item(run_id: str) -> dict[str, Any] | None:
    clean_id = str(run_id or "").strip()
    for item in get_history_items():
        if item.get("run_id") == clean_id:
            return item
    return None


def normalize_history_item(item: dict[str, Any]) -> dict[str, Any]:
    report_dir = str(item.get("report_dir") or "").replace("\\", "/")
    manifest_path = str(item.get("manifest_path") or "").replace("\\", "/")
    return sanitize_for_cache(
        {
            "run_id": str(item.get("run_id") or Path(report_dir).name or ""),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
            "super_topic": str(item.get("super_topic") or ""),
            "super_topic_name": str(item.get("super_topic_name") or ""),
            "super_topic_id": str(item.get("super_topic_id") or ""),
            "window_start": str(item.get("window_start") or ""),
            "window_end": str(item.get("window_end") or ""),
            "selected_count": _int(item.get("selected_count")),
            "total_posts": _int(item.get("total_posts")),
            "candidate_count": _int(item.get("candidate_count")),
            "status": str(item.get("status") or "unknown"),
            "report_dir": report_dir,
            "manifest_path": manifest_path,
            "has_cache": bool(item.get("has_cache")),
            "can_reexport": bool(item.get("can_reexport")),
            "files": dict(item.get("files") or {}),
            "warnings_count": _int(item.get("warnings_count")),
            "failed_images_count": _int(item.get("failed_images_count")),
            "reexport_count": _int(item.get("reexport_count")),
            "last_reexport_at": item.get("last_reexport_at") or None,
        }
    )


def history_item_from_manifest(report_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report_dir = report_dir.resolve()
    cache_status = CacheStore(report_dir).get_cache_status()
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    item = {
        "run_id": str(manifest.get("run_id") or report_dir.name),
        "created_at": str(manifest.get("created_at") or ""),
        "updated_at": str(manifest.get("updated_at") or ""),
        "super_topic": str(manifest.get("super_topic") or ""),
        "super_topic_name": str(manifest.get("super_topic_name") or ""),
        "super_topic_id": str(manifest.get("super_topic_id") or ""),
        "window_start": str(manifest.get("window_start") or ""),
        "window_end": str(manifest.get("window_end") or ""),
        "selected_count": _int(manifest.get("selected_count")),
        "total_posts": _int(manifest.get("total_posts")),
        "candidate_count": _int(manifest.get("candidate_count")),
        "status": str(manifest.get("status") or "unknown"),
        "report_dir": _rel_project(report_dir),
        "manifest_path": _rel_project(report_dir / "manifest.json"),
        "has_cache": bool(cache_status.get("has_cache")),
        "can_reexport": bool(cache_status.get("can_reexport")),
        "files": {
            "markdown": _file_exists(report_dir, files.get("markdown")),
            "docx": _docx_exists(report_dir, files.get("docx")),
            "excel": _file_exists(report_dir, files.get("excel") or files.get("xlsx")),
            "csv": _file_exists(report_dir, files.get("csv")),
            "summary": _file_exists(report_dir, files.get("summary")),
            "images": _dir_exists(report_dir, files.get("images") or files.get("images_dir")),
        },
        "warnings_count": len(list(manifest.get("warnings") or [])),
        "failed_images_count": _int(manifest.get("failed_image_count") or len(list(manifest.get("failed_images") or []))),
        "reexport_count": _int(manifest.get("reexport_count")),
        "last_reexport_at": manifest.get("last_reexport_at") or None,
    }
    return normalize_history_item(item)


def sanitize_history(history: dict[str, Any]) -> dict[str, Any]:
    raw_items = history.get("items") if isinstance(history.get("items"), list) else []
    return sanitize_for_cache(
        {
            "version": HISTORY_VERSION,
            "updated_at": str(history.get("updated_at") or _now()),
            "items": _sort_items([normalize_history_item(item) for item in raw_items if isinstance(item, dict)]),
        }
    )


def resolve_history_report_dir(run_id: str) -> Path:
    item = find_history_item(run_id)
    if not item:
        raise ConfigError("历史任务不存在", "请先刷新或扫描 output 后重试。")
    report_dir = _resolve_report_dir(item.get("report_dir"))
    if not report_dir.exists() or not report_dir.is_dir():
        raise ConfigError("历史任务目录不存在", "请检查 output 目录是否被移动或删除。")
    return report_dir


def _empty_history() -> dict[str, Any]:
    return {"version": HISTORY_VERSION, "updated_at": _now(), "items": []}


def _incomplete_history_item(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    cache_status = CacheStore(run_dir).get_cache_status()
    created_at = ""
    try:
        created_at = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    return normalize_history_item({
        "run_id": run_dir.name,
        "created_at": created_at,
        "status": "incomplete",
        "report_dir": _rel_project(run_dir),
        "has_cache": bool(cache_status.get("has_cache")),
        "can_reexport": bool(cache_status.get("can_reexport")),
        "files": {},
    })


def _backup_broken_history(path: Path) -> None:
    try:
        shutil.copy2(path, path.with_name("weibo_stats_history.broken.json"))
    except OSError:
        return


def _resolve_output_root(output_dir: str | Path) -> Path:
    path = Path(output_dir or "output").expanduser()
    path = (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()
    default_output = (ROOT_DIR / "output").resolve()
    configured_output = normalize_output_dir(load_saved_config().get("output_dir") or "output").resolve()
    allowed_roots = {ROOT_DIR.resolve(), default_output, configured_output}
    if not any(is_relative_to(path, root) for root in allowed_roots):
        raise ConfigError("输出目录不在允许范围内", "历史扫描只能读取项目 output 或配置的导出目录。")
    return path


def _resolve_report_dir(value: Any) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ConfigError("历史任务目录为空", "请重新扫描 output。")
    path = Path(text).expanduser()
    path = (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()
    default_output = (ROOT_DIR / "output").resolve()
    if not is_relative_to(path, default_output) and not is_relative_to(path, ROOT_DIR.resolve()):
        raise ConfigError("历史任务目录不在允许范围内", "请重新扫描 output。")
    return path


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("created_at") or item.get("run_id") or ""), reverse=True)


def _file_exists(run_dir: Path, value: Any) -> bool:
    if not value:
        return False
    path = Path(str(value))
    if not path.is_absolute():
        path = run_dir / path
    return path.exists() and path.is_file()


def _docx_exists(run_dir: Path, value: Any) -> bool:
    if isinstance(value, list):
        return any(_file_exists(run_dir, item) for item in value)
    return _file_exists(run_dir, value)


def _dir_exists(run_dir: Path, value: Any) -> bool:
    if not value:
        return False
    path = Path(str(value))
    if not path.is_absolute():
        path = run_dir / path
    return path.exists() and path.is_dir()


def _rel_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
