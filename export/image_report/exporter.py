from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from export.context import ExportContext
from export.image_report.adapter import build_image_report_data
from export.image_report.models import ImageReportConfig, ImageReportResult, PageBlock
from export.image_report.paginator import paginate_posts
from export.image_report.renderer import render_preview_html
from modules.weibo_emoticons import ensure_weibo_emoticon_assets, extract_weibo_emoticon_names


def export_image_report(
    ctx: ExportContext,
    output_dir: Path | None = None,
    config: ImageReportConfig | dict[str, Any] | None = None,
) -> ImageReportResult:
    cfg = config if isinstance(config, ImageReportConfig) else ImageReportConfig.from_mapping(config)
    target_dir = output_dir or ctx.run_dir / "image_report"
    target_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    data = build_image_report_data(ctx, cfg)
    if cfg.render_weibo_emoticons:
        used_names = _collect_emoticon_names(data)
        if used_names:
            data.emoticons, emoticon_warnings = ensure_weibo_emoticon_assets(
                target_dir / "emoticons",
                names=used_names,
                download_all=cfg.download_all_emoticons,
            )
            warnings.extend(emoticon_warnings)
    pages = paginate_posts(data.posts, cfg)
    preview_path = target_dir / "preview.html"
    preview_path.write_text(render_preview_html(data, pages, cfg, target_dir), encoding="utf-8")

    page_paths: list[Path] = []
    if cfg.render_jpg:
        rendered, render_warnings = _render_jpg_pages(preview_path, pages, cfg, target_dir)
        page_paths.extend(rendered)
        warnings.extend(render_warnings)

    metadata_path = target_dir / "metadata.json"
    metadata = _build_metadata(data.title, data.issue, data.date_range, pages, cfg, page_paths, warnings)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ImageReportResult(
        preview=preview_path,
        pages=page_paths,
        metadata=metadata_path,
        warnings=warnings,
        page_count=len(pages),
    )


def _collect_emoticon_names(data: Any) -> set[str]:
    texts: list[str] = []
    for post in getattr(data, "posts", []) or []:
        texts.append(str(getattr(post, "content", "") or ""))
        for comment in getattr(post, "comments", []) or []:
            texts.append(str(getattr(comment, "text", "") or ""))
    return extract_weibo_emoticon_names(*texts)


def _render_jpg_pages(
    preview_path: Path,
    pages: list[PageBlock],
    config: ImageReportConfig,
    output_dir: Path,
) -> tuple[list[Path], list[str]]:
    try:
        return asyncio.run(_render_jpg_pages_async(preview_path, pages, config, output_dir))
    except ImportError:
        return [], ["未安装 Playwright，已生成 preview.html，但未生成 JPG。请先执行 pip install -r requirements.txt。"]
    except Exception as err:
        return [], [f"长图 JPG 导出失败：{type(err).__name__}: {err}"]


async def _render_jpg_pages_async(
    preview_path: Path,
    pages: list[PageBlock],
    config: ImageReportConfig,
    output_dir: Path,
) -> tuple[list[Path], list[str]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as err:
        raise ImportError from err

    warnings: list[str] = []
    rendered: list[Path] = []
    async with async_playwright() as playwright:
        browser = None
        launch_errors: list[str] = []
        if config.browser_channel:
            try:
                browser = await playwright.chromium.launch(channel=config.browser_channel, headless=True)
            except Exception as err:
                launch_errors.append(f"{config.browser_channel}: {type(err).__name__}: {err}")
        if browser is None:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception as err:
                launch_errors.append(f"chromium: {type(err).__name__}: {err}")
        if browser is None:
            details = "；".join(launch_errors)
            return [], [f"Playwright 浏览器启动失败，已保留 preview.html。{details}"]

        try:
            page = await browser.new_page(
                viewport={"width": config.width + 96, "height": min(config.max_page_height + 800, 12800)},
                device_scale_factor=1,
            )
            await page.goto(preview_path.resolve().as_uri(), wait_until="networkidle")
            await page.emulate_media(media="screen")
            for page_block in pages:
                locator = page.locator(f'.report-page[data-page="{page_block.number}"]')
                await locator.scroll_into_view_if_needed()
                actual_height = await locator.evaluate("el => Math.ceil(el.getBoundingClientRect().height)")
                page_block.actual_height = int(actual_height or 0)
                if page_block.actual_height > config.max_page_height:
                    warnings.append(
                        f"第 {page_block.number} 张长图实际高度 {page_block.actual_height}px，超过配置上限 {config.max_page_height}px。"
                    )
                out_path = output_dir / f"page_{page_block.number:02d}.jpg"
                await locator.screenshot(path=str(out_path), type="jpeg", quality=config.jpg_quality, animations="disabled")
                page_block.jpg_path = str(out_path)
                rendered.append(out_path)
        finally:
            await browser.close()
    return rendered, warnings


def _build_metadata(
    title: str,
    issue: str,
    date_range: str,
    pages: list[PageBlock],
    config: ImageReportConfig,
    page_paths: list[Path],
    warnings: list[str],
) -> dict[str, Any]:
    path_by_number = {index + 1: str(path) for index, path in enumerate(page_paths)}
    return {
        "schema_version": 1,
        "title": title,
        "issue": issue,
        "date_range": date_range,
        "width": config.width,
        "max_page_height": config.max_page_height,
        "jpg_quality": config.jpg_quality,
        "page_count": len(pages),
        "warnings": warnings,
        "pages": [
            {
                "page": page.number,
                "estimated_height": page.estimated_height,
                "actual_height": page.actual_height,
                "jpg_path": path_by_number.get(page.number, ""),
                "post_count": len(page.posts),
                "post_ids": [post.post_id for post in page.posts],
                "post_ranks": [post.rank for post in page.posts],
            }
            for page in pages
        ],
    }
