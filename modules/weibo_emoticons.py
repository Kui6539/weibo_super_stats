from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


WEIBO_EMOTICON_INDEX_URL = "https://h5.sinaimg.cn/m/emoticon/all.json"
WEIBO_EMOTICON_API_URL = "https://api.weibo.com/2/emotions.json?source=3818214747&type=face&language=cnname"
EMOTICON_TOKEN_RE = re.compile(r"\[([^\[\]\r\n]{1,24})\]")


def extract_weibo_emoticon_names(*texts: str) -> set[str]:
    names: set[str] = set()
    for text in texts:
        for match in EMOTICON_TOKEN_RE.finditer(str(text or "")):
            name = match.group(1).strip()
            if name:
                names.add(name)
    return names


def ensure_weibo_emoticon_assets(
    target_dir: Path,
    *,
    names: set[str] | None = None,
    download_all: bool = True,
    index_url: str = WEIBO_EMOTICON_INDEX_URL,
) -> tuple[dict[str, str], list[str]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    index, index_warnings = _load_or_fetch_index(target_dir / "index.json", index_url)
    warnings.extend(index_warnings)
    missing_names = {name for name in (names or set()) if name not in index}
    if missing_names:
        api_index, api_warnings = _fetch_api_index()
        warnings.extend(api_warnings)
        if api_index:
            index.update(api_index)
            _write_index(target_dir / "index.json", index)
    if not index:
        return {}, warnings

    requested = set(index) if download_all else {name for name in (names or set()) if name in index}
    if not requested:
        return {}, warnings

    assets: dict[str, str] = {}
    pending: list[tuple[str, str, Path, str]] = []
    for name in sorted(requested):
        item = index.get(name)
        if not isinstance(item, dict):
            continue
        source = _normalize_source(item.get("source"))
        if not source:
            continue
        filename = _asset_filename(name, item, source)
        path = target_dir / filename
        rel_path = f"{target_dir.name}/{filename}"
        if path.exists() and path.stat().st_size > 0:
            assets[name] = rel_path
        else:
            pending.append((name, source, path, rel_path))

    if pending:
        with ThreadPoolExecutor(max_workers=min(8, len(pending)), thread_name_prefix="weibo-emoticon") as executor:
            futures = {
                executor.submit(_download_asset, name, source, path): (name, path, rel_path)
                for name, source, path, rel_path in pending
            }
            for future in as_completed(futures):
                name, path, rel_path = futures[future]
                warning = future.result()
                if warning:
                    warnings.append(warning)
                if path.exists() and path.stat().st_size > 0:
                    assets[name] = rel_path
    return assets, warnings


def _load_or_fetch_index(index_path: Path, index_url: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if index_path.exists():
        try:
            cached = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                return {str(k): v for k, v in cached.items() if isinstance(v, dict)}, warnings
        except Exception:
            pass

    index: dict[str, dict[str, Any]] = {}
    try:
        resp = requests.get(index_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("index payload is not a JSON object")
        index.update({str(k): v for k, v in payload.items() if isinstance(v, dict)})
    except Exception as err:
        warnings.append(f"微博 H5 表情索引获取失败：{type(err).__name__}: {err}")

    api_index, api_warnings = _fetch_api_index()
    warnings.extend(api_warnings)
    index.update(api_index)
    if index:
        _write_index(index_path, index)
    return index, warnings


def _fetch_api_index(api_url: str = WEIBO_EMOTICON_API_URL) -> tuple[dict[str, dict[str, Any]], list[str]]:
    try:
        resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError("api payload is not a JSON array")
        return _api_payload_to_index(payload), []
    except Exception as err:
        return {}, [f"微博 API 表情索引获取失败：{type(err).__name__}: {err}"]


def _api_payload_to_index(payload: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase") or item.get("value") or "").strip()
        match = EMOTICON_TOKEN_RE.fullmatch(phrase)
        if not match:
            continue
        name = match.group(1).strip()
        source = str(item.get("icon") or item.get("url") or "").strip()
        if not name or not source:
            continue
        index[name] = {
            "class": _class_name_from_api_item(name, source),
            "source": source,
            "group": str(item.get("category") or item.get("type") or "api"),
        }
    return index


def _write_index(index_path: Path, index: dict[str, dict[str, Any]]) -> None:
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_source(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return ""


def _asset_filename(name: str, item: dict[str, Any], source: str) -> str:
    parsed = urlparse(source)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".png", ".gif", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(item.get("class") or "")).strip("_")
    if not slug:
        slug = f"emoticon_{hashlib.md5(name.encode('utf-8')).hexdigest()[:10]}"
    return f"{slug}{suffix}"


def _class_name_from_api_item(name: str, source: str) -> str:
    stem = Path(urlparse(source).path).stem
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    return slug or f"emoticon_{hashlib.md5(name.encode('utf-8')).hexdigest()[:10]}"


def _download_asset(name: str, source: str, path: Path) -> str:
    last_err: Exception | None = None
    for _attempt in range(2):
        try:
            resp = requests.get(source, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            return ""
        except Exception as err:
            last_err = err
    return f"微博表情下载失败：[{name}] {type(last_err).__name__}: {last_err}"
