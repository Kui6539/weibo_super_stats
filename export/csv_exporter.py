from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def export_posts_csv(posts: Iterable[dict[str, Any]], csv_path: Path, column_map: list[tuple[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [cn for _, cn in column_map]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for post in posts:
            writer.writerow(build_export_row(post, column_map))


def build_export_row(post: dict[str, Any], column_map: list[tuple[str, str]]) -> dict[str, Any]:
    return {cn: post.get(en, "") for en, cn in column_map}
