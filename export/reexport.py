from __future__ import annotations

import re
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.cache import CacheStore, read_manifest, sanitize_for_cache
from core.errors import ReexportCacheMissingError, ReexportError
from crawler import (
    analyze_active_period,
    build_comment_leaderboards,
    build_report_title,
    build_summary,
    export_posts_csv,
    export_posts_xlsx,
    export_weekly_report_docx,
    export_weekly_report_md,
    export_weekly_report_sum_docx,
    write_summary_txt,
)
from export.context import ExportContext
from export.manifest import build_manifest, write_manifest

DEFAULT_EXPORT_TYPES = {"markdown", "docx", "excel", "csv", "summary"}


def reexport_from_cache(
    run_dir: Path,
    selected_post_ids: list[str] | None = None,
    export_types: list[str] | None = None,
) -> dict[str, Any]:
    store = CacheStore(run_dir)
    ok, missing = store.has_required_for_reexport()
    if not ok:
        raise ReexportCacheMissingError(
            "缓存文件不完整，无法重新生成报告",
            f"缺少：{', '.join(missing)}。请重新执行一次完整任务，或选择包含完整 cache 的运行目录。",
        )

    posts_all = store.read_stage("posts_scored")
    if not posts_all:
        posts_all = store.read_stage("posts_hydrated")
    if not isinstance(posts_all, list) or not posts_all:
        raise ReexportError("帖子缓存为空，无法重新生成报告", "请重新执行一次完整任务。")

    selected_posts = _resolve_selected_posts(store, posts_all, selected_post_ids)
    run_config = store.read_stage("run_config") or {}
    community_stats = store.read_stage("community_stats") or {}
    images_manifest = store.read_stage("images_manifest") or {}
    selected_posts = _restore_image_paths_from_manifest(run_dir, selected_posts, images_manifest)
    warnings = []
    warnings.extend(list(community_stats.get("warnings") or [])) if isinstance(community_stats, dict) else None
    warnings.extend(_collect_missing_image_warnings(run_dir, selected_posts))

    export_set = _normalize_export_types(export_types)
    summary = build_summary(selected_posts)
    all_posts_summary = build_summary(posts_all)
    leaderboards = build_comment_leaderboards(posts_all, top_n=3)
    active_period = (
        community_stats.get("active_period")
        if isinstance(community_stats, dict) and isinstance(community_stats.get("active_period"), dict)
        else analyze_active_period(posts_all)
    )
    report_title = _report_title_from_config(run_config)
    export_config = dict(run_config) if isinstance(run_config, dict) else {}
    export_config.setdefault("report_title", report_title)

    files: dict[str, Any] = {
        "markdown": run_dir / "weekly_report.md",
        "docx": [],
        "docx_sum": run_dir / "weekly_report_sum.docx",
        "xlsx": run_dir / "weibo_posts.xlsx",
        "csv": run_dir / "weibo_posts.csv",
        "summary": run_dir / "weibo_summary.txt",
        "images": run_dir / "images",
    }

    try:
        _remove_legacy_report_files(run_dir)
        if "excel" in export_set or "xlsx" in export_set:
            export_posts_xlsx(selected_posts, files["xlsx"])
        if "csv" in export_set:
            export_posts_csv(selected_posts, files["csv"])
        if "summary" in export_set:
            write_summary_txt(
                summary,
                files["summary"],
                leaderboards=leaderboards,
                active_period=active_period,
                all_posts_summary=all_posts_summary,
                carryover_hours=int(run_config.get("carryover_hours") or 0) if isinstance(run_config, dict) else 0,
            )
        if "docx" in export_set:
            _remove_generated_docx(run_dir)
            docx_paths = export_weekly_report_docx(
                selected_posts,
                run_dir / "weekly_report.docx",
                title=report_title,
                leaderboards=leaderboards,
                preselected=True,
            )
            files["docx"] = docx_paths
            files["docx_sum"] = export_weekly_report_sum_docx(
                selected_posts,
                run_dir / "weekly_report_sum.docx",
                title=report_title,
                leaderboards=leaderboards,
                preselected=True,
            )
        if "markdown" in export_set:
            export_weekly_report_md(
                selected_posts,
                files["markdown"],
                title=report_title,
                leaderboards=leaderboards,
                preselected=True,
            )
    except PermissionError as err:
        raise ReexportError("文件写入失败", "请关闭正在打开的 Word/Excel 文件后重试。") from err
    except OSError as err:
        raise ReexportError("文件写入失败", "请确认导出目录可写，并关闭正在打开的导出文件后重试。") from err

    if not files["docx"]:
        previous_manifest = read_manifest(run_dir, {}) or {}
        previous_files = previous_manifest.get("files") if isinstance(previous_manifest, dict) else {}
        files["docx"] = [run_dir / path for path in (previous_files or {}).get("docx", []) or []]

    ctx = ExportContext(
        run_dir=run_dir,
        selected_posts=selected_posts,
        all_posts=posts_all,
        config=export_config,
        stats=summary,
        images_manifest=images_manifest if isinstance(images_manifest, dict) else None,
        reexport=True,
    )
    previous = read_manifest(run_dir, {}) or {}
    manifest = build_manifest(
        ctx,
        files,
        warnings=warnings,
        failed_images=len((images_manifest or {}).get("failed", [])) if isinstance(images_manifest, dict) else 0,
        previous=previous,
        status="reexported",
    )
    write_manifest(run_dir, manifest)
    store.write_stage("run_config", export_config)
    store.write_stage("selected_posts", selected_posts)
    return {
        "message": "重新生成完成",
        "manifest": sanitize_for_cache(manifest),
        "result": _manifest_to_result(run_dir, manifest),
    }


def _resolve_selected_posts(
    store: CacheStore,
    posts_all: list[dict],
    selected_post_ids: list[str] | None,
) -> list[dict]:
    if selected_post_ids is None:
        selected = store.read_stage("selected_posts")
        if not isinstance(selected, list) or not selected:
            raise ReexportError("缺少人工选择缓存，无法重新生成报告", "请重新完成一次人工筛选或重新执行任务。")
        return selected
    wanted = {str(post_id) for post_id in selected_post_ids if str(post_id).strip()}
    by_id = {str(post.get("post_id") or ""): post for post in posts_all}
    selected = [by_id[str(post_id)] for post_id in selected_post_ids if str(post_id) in by_id]
    missing = wanted - set(by_id)
    if missing:
        raise ReexportError("选择的帖子不在评分缓存中", f"缺少 post_id：{', '.join(sorted(missing))}。请检查缓存文件。")
    if not selected:
        raise ReexportError("没有可重新生成的入选帖子", "请至少选择一条缓存中的帖子。")
    return selected


def _report_title_from_config(config: Any) -> str:
    if not isinstance(config, dict):
        return build_report_title()
    explicit_title = str(config.get("report_title") or "").strip()
    if explicit_title:
        return explicit_title
    return build_report_title(config.get("super_topic_name"), config.get("super_topic"))


def _restore_image_paths_from_manifest(
    run_dir: Path,
    posts: list[dict],
    images_manifest: Any,
) -> list[dict]:
    if not isinstance(images_manifest, dict):
        return deepcopy(posts)

    success_rows = [row for row in list(images_manifest.get("success") or []) if isinstance(row, dict)]
    if not success_rows:
        return deepcopy(posts)

    rows_by_post: dict[str, dict[str, list[dict]]] = {}
    for row in success_rows:
        post_id = str(row.get("post_id") or "")
        image_type = str(row.get("type") or "")
        local_path = str(row.get("local_path") or "").strip()
        if not post_id or not image_type or not local_path:
            continue
        rows_by_post.setdefault(post_id, {}).setdefault(image_type, []).append(row)

    restored = deepcopy(posts)
    for post in restored:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("post_id") or "")
        grouped = rows_by_post.get(post_id) or {}
        post_rows = list(grouped.get("post_image") or [])
        comment_rows = list(grouped.get("comment_image") or [])

        post_paths = [_manifest_local_path(run_dir, row) for row in post_rows]
        if post_paths:
            post["image_local_paths"] = " | ".join(post_paths)
            post["downloaded_image_count"] = len(post_paths)

        comment_paths_all: list[str] = []
        comments = list(post.get("top_comments_data") or [])
        if comments and comment_rows:
            rows_by_url: dict[str, list[dict]] = {}
            for row in comment_rows:
                rows_by_url.setdefault(str(row.get("url") or ""), []).append(row)
            sequential_rows = list(comment_rows)

            for comment in comments:
                if not isinstance(comment, dict):
                    continue
                urls = _split_paths(comment.get("image_urls"))
                if urls:
                    comment["image_urls"] = " | ".join(urls)
                local_paths: list[str] = []
                for url in urls:
                    matched_row = _pop_manifest_row(rows_by_url, sequential_rows, url)
                    if matched_row:
                        local_paths.append(_manifest_local_path(run_dir, matched_row))
                if not local_paths and comment.get("image_local_paths"):
                    local_paths = _split_paths(comment.get("image_local_paths"))
                if local_paths:
                    comment["image_local_paths"] = " | ".join(local_paths)
                    comment_paths_all.extend(local_paths)

            post["top_comments_data"] = comments

        if comment_paths_all:
            post["comment_image_local_paths"] = " | ".join(comment_paths_all)
            post["downloaded_comment_image_count"] = len(comment_paths_all)

        all_paths = post_paths + comment_paths_all
        if all_paths:
            post["image_local_paths_all"] = " | ".join(all_paths)

    return restored


def _manifest_local_path(run_dir: Path, row: dict) -> str:
    text = str(row.get("local_path") or "").strip()
    path = Path(text)
    if path.is_absolute():
        return str(path)
    return str((run_dir / path).resolve())


def _pop_manifest_row(
    rows_by_url: dict[str, list[dict]],
    sequential_rows: list[dict],
    url: str,
) -> dict | None:
    bucket = rows_by_url.get(str(url or ""))
    if bucket:
        row = bucket.pop(0)
        with suppress(ValueError):
            sequential_rows.remove(row)
        return row
    if sequential_rows:
        return sequential_rows.pop(0)
    return None


def _normalize_export_types(export_types: list[str] | None) -> set[str]:
    if not export_types:
        return set(DEFAULT_EXPORT_TYPES)
    aliases = {"xlsx": "excel"}
    result = {aliases.get(str(item).lower(), str(item).lower()) for item in export_types}
    return result & (DEFAULT_EXPORT_TYPES | {"xlsx"}) or set(DEFAULT_EXPORT_TYPES)


def _remove_generated_docx(run_dir: Path) -> None:
    for pattern in ("weekly_report*.docx", "warma_weekly_report*.docx"):
        for path in run_dir.glob(pattern):
            if _is_generated_report_docx(path.name):
                path.unlink(missing_ok=True)
    target = run_dir / "weekly_report_sum.docx"
    if target.exists():
        target.unlink()


def _is_generated_report_docx(name: str) -> bool:
    return (
        name == "weekly_report.docx"
        or name == "weekly_report_sum.docx"
        or re.fullmatch(r"weekly_report_\d{2}\.docx", name) is not None
        or name == "warma_weekly_report.docx"
        or re.fullmatch(r"warma_weekly_report_\d{2}\.docx", name) is not None
    )


def _remove_legacy_report_files(run_dir: Path) -> None:
    for path in [run_dir / "warma_weekly_report.md", *run_dir.glob("warma_weekly_report*.docx")]:
        if path.exists():
            path.unlink(missing_ok=True)


def _collect_missing_image_warnings(run_dir: Path, posts: list[dict]) -> list[str]:
    missing = 0
    for post in posts:
        for key in ("image_local_paths_all", "image_local_paths", "comment_image_local_paths"):
            for raw in _split_paths(post.get(key)):
                path = Path(raw)
                if not path.is_absolute():
                    path = run_dir / path
                if not path.exists():
                    missing += 1
    if not missing:
        return []
    return [f"有 {missing} 个本地图片路径不存在，报告已继续生成，请检查 images 目录。"]


def _split_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = [str(item).strip() for item in value]
    else:
        rows = [part.strip() for part in str(value or "").replace("\n", "|").split("|")]
    return [item for item in rows if item]


def _manifest_to_result(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest.get("files") if isinstance(manifest, dict) else {}

    def abs_path(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        path = Path(text)
        return str(path if path.is_absolute() else run_dir / path)

    docx = [abs_path(item) for item in list((files or {}).get("docx") or []) if item]
    return {
        "run_dir": str(run_dir),
        "image_dir": abs_path((files or {}).get("images_dir") or (files or {}).get("images")),
        "xlsx": abs_path((files or {}).get("xlsx") or (files or {}).get("excel")),
        "csv": abs_path((files or {}).get("csv")),
        "docx": docx,
        "docx_sum": abs_path((files or {}).get("docx_sum")),
        "md": abs_path((files or {}).get("markdown")),
        "summary": abs_path((files or {}).get("summary")),
        "failed_image_count": int(manifest.get("failed_image_count") or 0),
        "warnings": list(manifest.get("warnings") or []),
        "manifest": manifest,
    }
