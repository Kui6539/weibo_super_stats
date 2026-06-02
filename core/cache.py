from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from core.errors import CacheError

ROOT_DIR = Path(__file__).resolve().parents[1]
CACHE_ROOT_ENV = "WEIBO_STATS_CACHE_ROOT"
LEGACY_CACHE_DIR_NAME = "cache"

SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "session",
    "password",
    "passwd",
    "secret",
}

STAGE_FILES = {
    "run_config": "run_config.json",
    "posts_raw": "posts_raw.json",
    "posts_hydrated": "posts_hydrated.json",
    "posts_scored": "posts_scored.json",
    "candidates": "candidates.json",
    "selected_posts": "selected_posts.json",
    "community_stats": "community_stats.json",
    "images_manifest": "images_manifest.json",
}

REEXPORT_REQUIRED = ("run_config", "selected_posts")


def sanitize_for_cache(data: Any) -> Any:
    if isinstance(data, dict):
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if _is_sensitive_key(key):
                continue
            clean[key] = sanitize_for_cache(value)
        return clean
    if isinstance(data, list):
        return [sanitize_for_cache(item) for item in data]
    if isinstance(data, tuple):
        return [sanitize_for_cache(item) for item in data]
    return data


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").strip().lower()
    return lowered in SENSITIVE_KEYS or any(part in lowered for part in ("cookie", "authorization", "password"))


class CacheStore:
    def __init__(self, run_dir: Path, cache_root: Path | None = None):
        self.run_dir = run_dir.resolve()
        self.legacy_cache_dir = self.run_dir / LEGACY_CACHE_DIR_NAME
        root = cache_root.resolve() if cache_root is not None else default_cache_root()
        self.cache_root = root
        self.project_cache_dir = self.cache_root / self.run_dir.name
        self.cache_dir = self._resolve_cache_dir()
        self.comments_dir = self.cache_dir / "comments"
        self.cache_location = "run_dir_legacy" if self.cache_dir == self.legacy_cache_dir else "project_root"

    def _resolve_cache_dir(self) -> Path:
        manifest_cache_dir = self._cache_dir_from_manifest()
        if manifest_cache_dir and manifest_cache_dir.exists():
            return manifest_cache_dir
        if self.legacy_cache_dir.exists():
            return self.legacy_cache_dir
        if self.project_cache_dir.exists():
            return self.project_cache_dir
        return self.project_cache_dir

    def init(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.comments_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, data: Any) -> Path:
        self.init()
        target = self.cache_dir / _safe_cache_filename(name)
        return _atomic_write_json(target, sanitize_for_cache(data))

    def read_json(self, name: str, default: Any = None) -> Any:
        target = self.cache_dir / _safe_cache_filename(name)
        if not target.exists():
            return default
        return _read_json_file(target)

    def write_stage(self, stage: str, data: Any) -> Path:
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        return self.write_json(filename, data)

    def read_stage(self, stage: str) -> Any:
        filename = STAGE_FILES.get(stage, f"{stage}.json")
        return self.read_json(filename)

    def write_comment_cache(self, post_id: str, data: Any) -> Path:
        self.init()
        filename = _comment_filename(post_id)
        return _atomic_write_json(self.comments_dir / filename, sanitize_for_cache(data))

    def read_comment_cache(self, post_id: str) -> Any | None:
        path = self.comments_dir / _comment_filename(post_id)
        if not path.exists():
            return None
        data = _read_json_file(path)
        if not isinstance(data, dict):
            raise CacheError("评论缓存格式无效", "请删除损坏的评论缓存后重试。")
        return data

    def has_required_for_reexport(self) -> tuple[bool, list[str]]:
        missing = [STAGE_FILES[name] for name in REEXPORT_REQUIRED if not (self.cache_dir / STAGE_FILES[name]).exists()]
        if not (self.cache_dir / STAGE_FILES["posts_scored"]).exists() and not (self.cache_dir / STAGE_FILES["posts_hydrated"]).exists():
            missing.append("posts_scored.json 或 posts_hydrated.json")
        return not missing, missing

    def get_cache_status(self) -> dict[str, Any]:
        has_cache = self.cache_dir.exists() and self.cache_dir.is_dir()
        files = {
            key: (self.cache_dir / filename).exists()
            for key, filename in STAGE_FILES.items()
        }
        comments_count = 0
        if self.comments_dir.exists():
            comments_count = len(list(self.comments_dir.glob("*.json")))
        can_reexport, missing = self.has_required_for_reexport() if has_cache else (False, ["cache/"])
        manifest = None
        manifest_path = self.run_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = sanitize_for_cache(_read_json_file(manifest_path))
            except CacheError:
                manifest = None
        return {
            "run_dir": str(self.run_dir),
            "cache_dir": str(self.cache_dir),
            "cache_root": str(self.cache_root),
            "cache_location": self.cache_location,
            "legacy_cache_dir": str(self.legacy_cache_dir),
            "has_cache": has_cache,
            "can_reexport": can_reexport,
            "missing": missing,
            "files": files,
            "comments_count": comments_count,
            "manifest": manifest,
        }

    def manifest_paths(self) -> dict[str, str]:
        base = self._display_path(self.cache_dir)
        return {
            "cache_dir": base,
            "location": self.cache_location,
            "run_config": f"{base}/run_config.json",
            "posts_raw": f"{base}/posts_raw.json",
            "posts_hydrated": f"{base}/posts_hydrated.json",
            "posts_scored": f"{base}/posts_scored.json",
            "candidates": f"{base}/candidates.json",
            "selected_posts": f"{base}/selected_posts.json",
            "community_stats": f"{base}/community_stats.json",
            "images_manifest": f"{base}/images_manifest.json",
            "comments_dir": f"{base}/comments",
        }

    def _cache_dir_from_manifest(self) -> Path | None:
        manifest_path = self.run_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            manifest = _read_json_file(manifest_path)
        except CacheError:
            return None
        cache = manifest.get("cache") if isinstance(manifest, dict) else None
        if not isinstance(cache, dict):
            return None
        raw = str(cache.get("cache_dir") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            return path.resolve()
        location = str(cache.get("location") or "").strip()
        if location == "project_root":
            return (ROOT_DIR / path).resolve()
        if location == "run_dir_legacy":
            return (self.run_dir / path).resolve()
        if raw == LEGACY_CACHE_DIR_NAME:
            return self.legacy_cache_dir
        if raw.startswith(f"{LEGACY_CACHE_DIR_NAME}/") and self.run_dir.name in path.parts:
            return (ROOT_DIR / path).resolve()
        return (self.run_dir / path).resolve()

    def _display_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.run_dir.resolve(), ROOT_DIR.resolve()):
            try:
                return str(resolved.relative_to(base)).replace("\\", "/")
            except ValueError:
                continue
        return str(resolved).replace("\\", "/")


def default_cache_root() -> Path:
    raw = str(os.environ.get(CACHE_ROOT_ENV) or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()
    return ROOT_DIR / "cache"


def read_manifest(run_dir: Path, default: Any = None) -> Any:
    path = run_dir / "manifest.json"
    if not path.exists():
        return default
    return sanitize_for_cache(_read_json_file(path))


def write_manifest_json(run_dir: Path, manifest: dict[str, Any]) -> Path:
    return _atomic_write_json(run_dir / "manifest.json", sanitize_for_cache(manifest))


def _atomic_write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return path


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise CacheError(f"缓存文件不存在：{path.name}", "请重新执行一次完整任务。") from err
    except json.JSONDecodeError as err:
        raise CacheError(f"缓存文件 JSON 格式损坏：{path.name}", "请删除损坏缓存并重新执行任务。") from err
    except OSError as err:
        raise CacheError(f"缓存文件读取失败：{path.name}", "请检查文件权限后重试。") from err


def _safe_cache_filename(name: str) -> str:
    text = str(name or "").strip().replace("\\", "/").split("/")[-1]
    text = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]", "_", text)
    if not text:
        text = "cache.json"
    if not text.endswith(".json"):
        text += ".json"
    return text


def _comment_filename(post_id: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_.-]", "_", str(post_id or "").strip())
    return f"post_{text or 'unknown'}.json"

