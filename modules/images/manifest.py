from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_images_manifest(results: list[dict[str, Any]]) -> dict[str, Any]:
    success = [row for row in results if row.get("ok")]
    failed = [row for row in results if not row.get("ok")]
    return {"schema_version": 1, "success": success, "failed": failed}


def write_images_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    path = run_dir / "cache" / "images_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path


def read_images_manifest(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "cache" / "images_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
