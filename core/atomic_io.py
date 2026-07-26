"""Atomic JSON file writes shared by config, history and cache stores.

Writing config/history with a plain ``write_text`` truncates the target before
the new bytes land, so a crash (or a concurrent reader in the threading HTTP
server) can observe a half-written file. ``load_config`` treats an unparsable
file as corrupt and silently falls back to defaults, which means a torn write
costs the user their cookie and every saved preset.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> Path:
    """Serialize *data* to *path* via a temp file + ``os.replace``.

    ``Path.replace`` maps to ``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING``
    on Windows, so readers see either the old file or the new one, never a
    truncated one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=indent, default=str) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return path
