from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_resolve(base: Path, target: str | Path) -> Path:
    base_resolved = base.resolve()
    raw = Path(target)
    candidate = raw if raw.is_absolute() else base_resolved / raw
    resolved = candidate.resolve()
    if not is_relative_to(resolved, base_resolved):
        raise ValueError("路径越界，已拒绝访问。")
    return resolved


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_writable_dir(path: Path) -> bool:
    try:
        ensure_dir(path)
        probe = path / f".weibo_stats_write_test_{datetime.now().timestamp():.6f}.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def sanitize_filename(name: str) -> str:
    text = str(name or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or "未命名"


def make_run_dir(output_dir: Path) -> Path:
    run_dir = output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def normalize_output_dir(value: Any) -> Path:
    raw = str(value or "").strip() or "output"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path

