"""Deletes the output and cache directories left by a run that did not finish.

Every guard here exists because this code deletes real user data. A run
directory is only removable when it sits directly under the configured output
directory, carries a timestamped name, and has no manifest claiming the run
produced something usable. A cache directory is only removable when it belongs
to that run -- either the legacy ``<run_dir>/cache`` or a directory named after
the run sitting directly under the cache root.

``keep_cache`` is the counterweight: once the selection has been cached, the
run holds everything an offline reexport needs, so a later failure (typically a
locked Word or Excel file) must not throw the crawl away. The run directory is
kept along with it -- without it the history panel has no entry through which
to offer the regeneration.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from core.cache import CacheStore
from core.paths import RUN_DIR_RE, is_relative_to

# A manifest with one of these statuses means the run left something worth
# keeping. export_failed in particular still carries a complete crawl plus
# whichever formats did get written, so it is a reexport candidate.
PRESERVED_MANIFEST_STATUSES = {"completed", "reexported", "export_failed", "partial"}


def cleanup_incomplete_artifacts(
    run_dir: Path | None,
    output_dir: Path,
    cache_store: CacheStore | None = None,
    keep_cache: bool = False,
) -> dict[str, Any]:
    """Remove the artifacts of a run that did not finish.

    Returns a report of what was deleted, skipped and what failed, so the
    caller can tell the user rather than silently discarding directories.
    """
    result: dict[str, Any] = {
        "run_dir": str(run_dir) if run_dir else "",
        "deleted_dirs": [],
        "skipped": [],
        "errors": [],
        "kept_cache": bool(keep_cache),
    }
    if run_dir is None:
        result["skipped"].append("尚未创建运行目录")
        return result

    resolved_run_dir = run_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    result["run_dir"] = str(resolved_run_dir)
    if keep_cache:
        result["skipped"].append(f"已保留可重新生成报告的缓存与目录：{resolved_run_dir}")
        return result
    if not is_run_dir_deletable(resolved_run_dir, resolved_output_dir):
        result["skipped"].append(f"运行目录不符合自动清理规则：{resolved_run_dir}")
        return result

    for cache_dir in candidate_cache_dirs(resolved_run_dir, cache_store):
        if not cache_dir.exists():
            continue
        # Caches inside the run directory go away with it.
        if is_relative_to(cache_dir, resolved_run_dir):
            continue
        if not is_cache_dir_deletable(cache_dir, resolved_run_dir, cache_store):
            result["skipped"].append(f"缓存目录不符合自动清理规则：{cache_dir}")
            continue
        delete_dir(cache_dir, result)

    delete_dir(resolved_run_dir, result)
    return result


def cleanup_cancelled_artifacts(
    run_dir: Path | None,
    output_dir: Path,
    cache_store: CacheStore | None = None,
) -> dict[str, Any]:
    """Cancelling always discards everything -- the user asked for that."""
    return cleanup_incomplete_artifacts(run_dir, output_dir, cache_store)


def is_run_dir_deletable(run_dir: Path, output_dir: Path) -> bool:
    if not RUN_DIR_RE.match(run_dir.name):
        return False
    try:
        if run_dir.parent.resolve() != output_dir.resolve():
            return False
    except OSError:
        return False
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # An unreadable manifest says nothing about the run being worth
        # keeping, so fall through to deleting it.
        manifest = {}
    if not isinstance(manifest, dict):
        return True
    status = str(manifest.get("status") or "").strip().lower()
    return status not in PRESERVED_MANIFEST_STATUSES


def candidate_cache_dirs(run_dir: Path, cache_store: CacheStore | None) -> list[Path]:
    """Every cache location this run might have written to, de-duplicated."""
    store = cache_store or CacheStore(run_dir)
    rows = [store.cache_dir, store.project_cache_dir, store.legacy_cache_dir]
    out: list[Path] = []
    seen: set[str] = set()
    for path in rows:
        resolved = path.resolve()
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def is_cache_dir_deletable(cache_dir: Path, run_dir: Path, cache_store: CacheStore | None) -> bool:
    if cache_dir.name != run_dir.name and cache_dir.name != "cache":
        return False
    if cache_dir.name == "cache":
        return is_relative_to(cache_dir, run_dir)
    cache_root = (cache_store.cache_root if cache_store else CacheStore(run_dir).cache_root).resolve()
    return cache_dir.parent.resolve() == cache_root


def delete_dir(path: Path, result: dict[str, Any]) -> None:
    """Delete one directory, recording the outcome instead of raising."""
    if not path.exists():
        return
    if not path.is_dir():
        result["skipped"].append(f"不是目录：{path}")
        return
    try:
        shutil.rmtree(path, ignore_errors=False)
        result["deleted_dirs"].append(str(path))
    except OSError as err:
        result["errors"].append(f"{path}: {type(err).__name__}: {err}")
