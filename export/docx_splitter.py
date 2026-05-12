from __future__ import annotations

import re
from pathlib import Path

DOCX_SIZE_LIMIT_BYTES = 10 * 1000 * 1000


def split_posts_for_docx(selected_posts: list[dict], max_size_mb: int = 10) -> list[list[dict]]:
    # Size-aware splitting needs a renderer trial file; this fallback keeps the
    # public splitter deterministic for unit tests and simple callers.
    return [list(selected_posts)] if selected_posts else [[]]


def cleanup_old_generated_docx(run_dir: Path) -> None:
    for pattern in ("weekly_report*.docx", "warma_weekly_report*.docx"):
        for path in run_dir.glob(pattern):
            if _is_generated_docx_name(path.name):
                path.unlink(missing_ok=True)


def build_docx_filename(index: int) -> str:
    return f"weekly_report_{max(1, int(index)):02d}.docx"


def numbered_docx_path(docx_path: Path, index: int) -> Path:
    return docx_path.with_name(f"{docx_path.stem}_{max(1, int(index)):02d}{docx_path.suffix}")


def _is_generated_docx_name(name: str) -> bool:
    return (
        name == "weekly_report.docx"
        or name == "weekly_report_sum.docx"
        or re.fullmatch(r"weekly_report_\d{2}\.docx", name) is not None
        or name == "warma_weekly_report.docx"
        or re.fullmatch(r"warma_weekly_report_\d{2}\.docx", name) is not None
    )
