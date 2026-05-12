from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExportContext:
    run_dir: Path
    selected_posts: list[dict]
    all_posts: list[dict]
    config: dict[str, Any]
    stats: dict[str, Any]
    images_manifest: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    failed_images: list[dict[str, Any]] = field(default_factory=list)
    reexport: bool = False
