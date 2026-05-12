from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl.drawing.image import Image as XLImage


def add_images_to_sheet(sheet, post: dict[str, Any], row_index: int, first_image_col: int, image_count: int) -> None:
    image_paths = get_embed_image_paths(post)
    if not image_paths:
        return
    sheet.row_dimensions[row_index].height = 125
    for idx, image_path in enumerate(image_paths[:image_count], start=0):
        cell_ref = f"{sheet.cell(row=row_index, column=first_image_col + idx).coordinate}"
        image = prepare_excel_image(image_path)
        if image is None:
            continue
        sheet.add_image(image, cell_ref)


def prepare_excel_image(path: str | Path):
    try:
        image = XLImage(str(path))
    except Exception:
        return None
    max_w, max_h = 180, 120
    if image.width and image.height:
        scale = min(max_w / image.width, max_h / image.height, 1.0)
        image.width = int(image.width * scale)
        image.height = int(image.height * scale)
    return image


def calculate_image_cell_size(path: str | Path) -> tuple[int, int]:
    image = prepare_excel_image(path)
    if image is None:
        return 0, 0
    return int(image.width), int(image.height)


def get_embed_image_paths(post: dict[str, Any]) -> list[str]:
    all_paths = _split_multi_paths(post.get("image_local_paths_all"))
    if all_paths:
        return all_paths
    post_paths = _split_multi_paths(post.get("image_local_paths"))
    comment_paths = _split_multi_paths(post.get("comment_image_local_paths"))
    return _dedup(post_paths + comment_paths)


def _split_multi_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value]
    else:
        parts = [part.strip() for part in str(value or "").replace("\n", "|").split("|")]
    return [part for part in parts if part]


def _dedup(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
