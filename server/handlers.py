from __future__ import annotations

import os
import re
import shutil
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from cookie_helper import (
    CookieFetchError,
    browser_display_name,
    clear_cdp_debug_cache,
    close_debug_browser,
    extract_cookie_from_text,
    get_weibo_cookie_header,
    launch_debug_browser,
    normalize_browser_name,
)
from core.cache import CacheStore
from core.config import (
    activate_preset,
    app_defaults,
    build_crawl_config,
    clear_config,
    delete_preset,
    duplicate_preset,
    get_presets_payload,
    load_saved_config,
    parse_datetime_local,
    resolve_payload_cookie,
    save_preset,
    save_user_config,
    validate_config_payload,
)
from core.errors import WeiboStatsError, to_error_response
from core.history import (
    add_history_item_from_manifest,
    find_history_duplicate,
    find_history_item,
    load_history,
    remove_history_item,
    resolve_history_report_dir,
    scan_output_history,
)
from core.job import (
    ACTIVE_STATUSES,
    cancel_current_job,
    console_log,
    create_job,
    get_current_job,
    serialize_job,
)
from core.output_cleanup import cleanup_output, cleanup_preview, output_summary
from core.paths import RUN_DIR_RE, is_relative_to, normalize_output_dir, safe_resolve
from crawler import parse_super_topic_id
from export.reexport import reexport_from_cache
from modules.crawler_client import WeiboClient
from modules.images.candidate_thumbnails import THUMBNAIL_DIR_NAME
from modules.topic import (
    build_report_title,
    calculate_weekly_issue,
    format_report_title_with_issue,
    normalize_issue_value,
    normalize_super_topic_name,
)
from modules.weibo_chaohua_api import CHAOHUA_API_URL, extract_chaohua_topic_name, initial_chaohua_params
from server.guards import (
    content_type_is_json,
    fetch_site_is_safe,
    host_is_local,
    origin_is_local,
)
from server.responses import (
    json_error,
    json_ok,
    parse_json_body,
    send_json,
    send_static_file,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT_DIR / "web"
HELP_DOC_PATH = ROOT_DIR / "docs" / "Cookie获取简短教程.md"
BACKGROUND_PATH = WEB_ROOT / "Background.png"


GET_ROUTES: dict[str, str] = {
    "/api/defaults": "handle_get_config",
    "/api/presets": "handle_get_presets",
    "/api/history": "handle_history",
    "/api/status": "handle_status",
    "/api/report-preview": "handle_report_preview",
    "/api/report-asset": "handle_report_asset",
    "/api/candidate-thumbnail": "handle_candidate_thumbnail",
    "/api/history/asset": "handle_history_asset",
    "/api/help-doc": "handle_help_doc",
}

POST_ROUTES: dict[str, str] = {
    "/api/preflight": "handle_preflight",
    "/api/topic-preview": "handle_topic_preview",
    "/api/check-cookie": "handle_check_cookie",
    "/api/clear-config": "handle_clear_config",
    "/api/cancel-job": "handle_cancel_job",
    "/api/cache-status": "handle_cache_status",
    "/api/reexport": "handle_reexport",
    "/api/history/scan": "handle_history_scan",
    "/api/history/remove": "handle_history_remove",
    "/api/history/cache-status": "handle_history_cache_status",
    "/api/history/reexport": "handle_history_reexport",
    "/api/history/open-dir": "handle_history_open_dir",
    "/api/history/preview": "handle_history_preview",
    "/api/presets/save": "handle_presets_save",
    "/api/presets/delete": "handle_presets_delete",
    "/api/presets/activate": "handle_presets_activate",
    "/api/presets/duplicate": "handle_presets_duplicate",
    "/api/output/summary": "handle_output_summary",
    "/api/output/cleanup-preview": "handle_output_cleanup_preview",
    "/api/output/cleanup": "handle_output_cleanup",
    "/api/start": "handle_start",
    "/api/config": "handle_save_config",
    "/api/select": "handle_select",
    "/api/cancel-selection": "handle_cancel_selection",
    "/api/cookie/auto": "handle_cookie_auto",
    "/api/cookie/edge-debug": "handle_cookie_edge_debug",
    "/api/cookie/clear-cdp-cache": "handle_cookie_clear_cdp_cache",
    "/api/cookie/extract": "handle_cookie_extract",
    "/api/open-result-dir": "handle_open_result_dir",
}


class AppRequestHandler(BaseHTTPRequestHandler):
    server_version = "WeiboStatsHTML/3.0"
    # Every response carries Content-Length, so keep-alive is safe. Without it
    # BaseHTTPRequestHandler speaks HTTP/1.0 and each poll, thumbnail and static
    # asset costs a fresh TCP connection and a fresh thread.
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._dispatch(GET_ROUTES, self._get_fallback, require_json_body=False)

    def do_POST(self) -> None:
        self._dispatch(POST_ROUTES, self._post_fallback, require_json_body=True)

    def _dispatch(self, routes: dict[str, str], fallback: Any, require_json_body: bool) -> None:
        path = urlparse(self.path).path
        if not self._request_origin_allowed(require_json_body):
            return
        try:
            handler_name = routes.get(path)
            if handler_name:
                getattr(self, handler_name)()
                return
            fallback(path)
        except CookieFetchError as err:
            console_log(f"Cookie 自动读取失败：{err}")
            json_error(self, "COOKIE_AUTO_FAILED", "Cookie 自动读取失败", str(err), HTTPStatus.BAD_REQUEST)
        except WeiboStatsError as err:
            send_json(self, to_error_response(err), HTTPStatus.BAD_REQUEST)
        except RuntimeError as err:
            json_error(self, "TASK_CONFLICT", str(err), "请等待当前任务完成或取消后重试。", HTTPStatus.CONFLICT)
        except ValueError as err:
            json_error(self, "BAD_REQUEST", str(err), "请检查输入参数后重试。", HTTPStatus.BAD_REQUEST)
        except Exception as err:
            self.handle_unknown_error(path, err)

    def _request_origin_allowed(self, require_json_body: bool) -> bool:
        """Reject anything that did not originate from this machine's own page.

        See server/guards for why each header matters. Failures are logged to
        the console rather than described to the caller.
        """
        port = self.server.server_address[1] if self.server else None
        if not host_is_local(self.headers.get("Host"), port):
            self._reject_request("HOST_NOT_ALLOWED", "请求的 Host 不是本机地址")
            return False
        if not origin_is_local(self.headers.get("Origin"), port):
            self._reject_request("ORIGIN_NOT_ALLOWED", "请求来源不是本机页面")
            return False
        if not fetch_site_is_safe(self.headers.get("Sec-Fetch-Site")):
            self._reject_request("CROSS_SITE_REJECTED", "已拒绝跨站请求")
            return False
        if require_json_body and not content_type_is_json(self.headers.get("Content-Type")):
            self._reject_request("CONTENT_TYPE_REJECTED", "请求体必须是 application/json")
            return False
        return True

    def _reject_request(self, code: str, message: str) -> None:
        console_log(f"已拒绝一个来源不可信的请求：{message}（{self.command} {self.path}）")
        # Rejected before reading any body, so the connection cannot be reused.
        self.close_connection = True
        json_error(self, code, message, "本工具只接受本机页面发起的请求。", HTTPStatus.FORBIDDEN)

    def _get_fallback(self, path: str) -> None:
        if path == "/Background.png":
            if BACKGROUND_PATH.exists() and BACKGROUND_PATH.is_file():
                send_static_file(self, BACKGROUND_PATH)
            else:
                json_error(self, "NOT_FOUND", "背景图片不存在", "请确认 web/Background.png 是否存在。", HTTPStatus.NOT_FOUND)
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        static_path = resolve_static_path(path)
        if static_path:
            send_static_file(self, static_path)
            return
        json_error(self, "NOT_FOUND", "接口或页面不存在", "请检查访问地址。", HTTPStatus.NOT_FOUND)

    def _post_fallback(self, _path: str) -> None:
        json_error(self, "NOT_FOUND", "接口不存在", "请检查请求地址。", HTTPStatus.NOT_FOUND)

    def handle_get_config(self) -> None:
        defaults = app_defaults()
        json_ok(self, {"defaults": defaults}, defaults=defaults)

    def handle_get_presets(self) -> None:
        data = get_presets_payload()
        json_ok(self, data, **data)

    def handle_save_config(self) -> None:
        payload = parse_json_body(self)
        config = save_user_config(payload)
        json_ok(self, {"config": config}, config=config)

    def handle_start(self) -> None:
        payload = parse_json_body(self)
        duplicate = find_duplicate_topic_issue(payload)
        if duplicate:
            raise ValueError(build_duplicate_topic_issue_message(duplicate))
        cfg, output_dir = build_crawl_config(payload)
        save_user_config(payload)
        job = create_job(cfg, output_dir)
        snapshot = serialize_job(job)
        json_ok(self, {"job": snapshot}, job=snapshot)

    def handle_status(self) -> None:
        snapshot = serialize_job(get_current_job())
        json_ok(self, {"job": snapshot}, job=snapshot)

    def handle_history(self) -> None:
        history = load_history()
        json_ok(self, {"history": history, "items": history.get("items", [])}, history=history, items=history.get("items", []))

    def handle_select(self) -> None:
        payload = parse_json_body(self)
        job = get_current_job()
        if not job:
            raise ValueError("没有正在运行的任务。")
        job.submit_selection(list(payload.get("indexes") or []))
        snapshot = job.snapshot()
        json_ok(self, {"job": snapshot}, job=snapshot)

    def handle_cancel_selection(self) -> None:
        job = get_current_job()
        if not job:
            raise ValueError("没有正在运行的任务。")
        job.cancel_selection()
        snapshot = job.snapshot()
        json_ok(self, {"job": snapshot}, job=snapshot)

    def handle_preflight(self) -> None:
        payload = parse_json_body(self)
        data = build_preflight(payload)
        json_ok(self, data, **data)

    def handle_topic_preview(self) -> None:
        payload = parse_json_body(self)
        data = resolve_topic_preview(payload)
        json_ok(self, data, **data)

    def handle_check_cookie(self) -> None:
        payload = parse_json_body(self)
        data = check_cookie_state(payload)
        json_ok(self, data, **data)

    def handle_clear_config(self) -> None:
        payload = parse_json_body(self)
        config = clear_config(str(payload.get("scope") or "cookie"))
        json_ok(self, {"config": config}, config=config)

    def handle_cancel_job(self) -> None:
        ok, message, job = cancel_current_job()
        snapshot = serialize_job(job)
        if not ok:
            send_json(
                self,
                {
                    "ok": False,
                    "error": {
                        "code": "NO_ACTIVE_JOB",
                        "message": "没有正在运行的任务",
                        "suggestion": "当前没有需要取消的任务。",
                    },
                    "job": snapshot,
                },
            )
            return
        json_ok(self, {"message": message, "job": snapshot}, message=message, job=snapshot)

    def handle_cache_status(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_run_dir_from_payload(payload)
        if not run_dir.exists() or not run_dir.is_dir():
            json_error(self, "CACHE_DIR_NOT_FOUND", "运行目录不存在", "请确认 run_dir 指向 output 下的时间戳目录。", HTTPStatus.NOT_FOUND)
            return
        data = CacheStore(run_dir).get_cache_status()
        json_ok(self, data, **data)

    def handle_reexport(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_run_dir_from_payload(payload)
        if not run_dir.exists() or not run_dir.is_dir():
            json_error(self, "CACHE_DIR_NOT_FOUND", "运行目录不存在", "请确认 run_dir 指向 output 下的时间戳目录。", HTTPStatus.NOT_FOUND)
            return
        data = reexport_from_cache(
            run_dir,
            selected_post_ids=payload.get("selected_post_ids"),
            export_types=list(payload.get("export_types") or []),
        )
        if isinstance(data.get("manifest"), dict):
            add_history_item_from_manifest(run_dir, data["manifest"])
        json_ok(self, data, **data)

    def handle_history_scan(self) -> None:
        payload = parse_json_body(self)
        data = scan_output_history(payload.get("output_dir") or "output")
        json_ok(self, data, **data)

    def handle_history_remove(self) -> None:
        payload = parse_json_body(self)
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("请填写 run_id。")
        item = find_history_item(run_id)
        if payload.get("delete_files"):
            if payload.get("confirm") is not True:
                json_error(self, "DELETE_CONFIRM_REQUIRED", "删除真实文件需要二次确认", "请确认 delete_files=true 且 confirm=true。", HTTPStatus.BAD_REQUEST)
                return
            report_dir = resolve_history_report_dir(run_id)
            output_root = (ROOT_DIR / "output").resolve()
            if not is_relative_to(report_dir, output_root) or not re.match(r"^\d{8}_\d{6}$", report_dir.name):
                json_error(self, "DELETE_PATH_REJECTED", "拒绝删除非运行目录", "只能删除 output 下的时间戳运行目录。", HTTPStatus.BAD_REQUEST)
                return
            if report_dir.exists() and report_dir.is_dir():
                shutil.rmtree(report_dir)
        history = remove_history_item(run_id)
        json_ok(self, {"history": history, "removed": run_id, "item": item}, history=history, removed=run_id, item=item)

    def handle_history_cache_status(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_history_report_dir(str(payload.get("run_id") or ""))
        data = CacheStore(run_dir).get_cache_status()
        json_ok(self, data, **data)

    def handle_history_reexport(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_history_report_dir(str(payload.get("run_id") or ""))
        data = reexport_from_cache(
            run_dir,
            selected_post_ids=payload.get("selected_post_ids"),
            export_types=list(payload.get("export_types") or []),
        )
        if isinstance(data.get("manifest"), dict):
            add_history_item_from_manifest(run_dir, data["manifest"])
        json_ok(self, data, **data)

    def handle_history_open_dir(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_history_report_dir(str(payload.get("run_id") or ""))
        open_local_path(run_dir)
        send_json(self, {"path": str(run_dir)})

    def handle_history_preview(self) -> None:
        payload = parse_json_body(self)
        run_dir = resolve_history_report_dir(str(payload.get("run_id") or ""))
        manifest_path = run_dir / "manifest.json"
        md_path: Path | None = None
        if manifest_path.exists():
            import json as _json
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
            md_name = files.get("markdown")
            if md_name:
                candidate = Path(str(md_name))
                if not candidate.is_absolute():
                    candidate = run_dir / candidate
                if candidate.exists() and candidate.is_file():
                    md_path = candidate
        if not md_path:
            for name in ("weekly_report.md", "report.md"):
                candidate = run_dir / name
                if candidate.exists() and candidate.is_file():
                    md_path = candidate
                    break
        if not md_path:
            json_error(self, "NO_MARKDOWN", "该历史任务没有 Markdown 报告", "请确认报告文件是否存在。", HTTPStatus.NOT_FOUND)
            return
        try:
            markdown = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            markdown = md_path.read_text(encoding="utf-8-sig")
        send_json(self, {"markdown": markdown, "path": _rel_display_path(md_path)})

    def handle_history_asset(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        run_id = (qs.get("run_id") or [""])[0]
        rel_text = (qs.get("path") or [""])[0]
        if not run_id or not rel_text:
            json_error(self, "BAD_REQUEST", "缺少参数", "需要 run_id 和 path 参数。", HTTPStatus.BAD_REQUEST)
            return
        run_dir = resolve_history_report_dir(run_id)
        asset_path = resolve_report_asset_path(run_dir / "_placeholder", rel_text)
        if not asset_path:
            json_error(self, "ASSET_NOT_FOUND", "资源不存在", "请检查路径。", HTTPStatus.NOT_FOUND)
            return
        send_static_file(self, asset_path)

    def handle_presets_save(self) -> None:
        payload = parse_json_body(self)
        preset = payload.get("preset") if isinstance(payload.get("preset"), dict) else payload
        data = save_preset(str(payload.get("preset_id") or payload.get("id") or ""), dict(preset))
        json_ok(self, data, **data)

    def handle_presets_delete(self) -> None:
        payload = parse_json_body(self)
        data = delete_preset(str(payload.get("preset_id") or payload.get("id") or ""))
        json_ok(self, data, **data)

    def handle_presets_activate(self) -> None:
        payload = parse_json_body(self)
        data = activate_preset(str(payload.get("preset_id") or payload.get("id") or ""))
        json_ok(self, data, **data)

    def handle_presets_duplicate(self) -> None:
        payload = parse_json_body(self)
        data = duplicate_preset(
            str(payload.get("source_id") or payload.get("preset_id") or payload.get("id") or ""),
            str(payload.get("new_id") or "") or None,
            str(payload.get("name") or "") or None,
        )
        json_ok(self, data, **data)

    def handle_output_summary(self) -> None:
        payload = parse_json_body(self)
        data = output_summary(payload.get("output_dir") or "output")
        json_ok(self, data, **data)

    def handle_output_cleanup_preview(self) -> None:
        payload = parse_json_body(self)
        data = cleanup_preview(
            output_dir=payload.get("output_dir") or "output",
            older_than_days=payload.get("older_than_days"),
            keep_recent=parse_optional_int(payload.get("keep_recent"), 5),
            incomplete_only=bool(payload.get("incomplete_only")),
            include_warnings=bool(payload.get("include_warnings")),
            include_failed=bool(payload.get("include_failed")),
            selected_run_ids=list(payload.get("selected_run_ids") or []) if isinstance(payload.get("selected_run_ids"), list) else None,
        )
        json_ok(self, data, **data)

    def handle_output_cleanup(self) -> None:
        payload = parse_json_body(self)
        data = cleanup_output(
            output_dir=payload.get("output_dir") or "output",
            confirm=payload.get("confirm") is True,
            older_than_days=payload.get("older_than_days"),
            keep_recent=parse_optional_int(payload.get("keep_recent"), 5),
            incomplete_only=bool(payload.get("incomplete_only")),
            include_warnings=bool(payload.get("include_warnings")),
            include_failed=bool(payload.get("include_failed")),
            selected_run_ids=list(payload.get("selected_run_ids") or []) if isinstance(payload.get("selected_run_ids"), list) else None,
        )
        json_ok(self, data, **data)

    def handle_report_preview(self) -> None:
        parsed = urlparse(self.path)
        qs_md = parse_qs(parsed.query).get("md_path", [])
        report_path = resolve_report_md_path(qs_md[0]) if qs_md and qs_md[0] else current_report_md_path()
        if not report_path:
            json_error(self, "NO_MARKDOWN_REPORT", "当前没有可预览的 Markdown 周报", "请先完成一次导出。", HTTPStatus.NOT_FOUND)
            return
        markdown = report_path.read_text(encoding="utf-8-sig", errors="replace")
        send_json(self, {"markdown": markdown, "path": _rel_display_path(report_path)})

    def handle_report_asset(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        qs_md = qs.get("md_path", [])
        report_path = resolve_report_md_path(qs_md[0]) if qs_md and qs_md[0] else current_report_md_path()
        if not report_path:
            json_error(self, "NO_MARKDOWN_REPORT", "当前没有可预览的 Markdown 周报", "请先完成一次导出。", HTTPStatus.NOT_FOUND)
            return
        rel_values = qs.get("path", [])
        rel_text = rel_values[0] if rel_values else ""
        asset_path = resolve_report_asset_path(report_path, rel_text)
        if not asset_path:
            json_error(self, "ASSET_NOT_FOUND", "资源不存在", "请检查 Markdown 中的图片路径。", HTTPStatus.NOT_FOUND)
            return
        send_static_file(self, asset_path)

    def handle_candidate_thumbnail(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        run_id = (qs.get("run_id") or [""])[0]
        rel_text = (qs.get("path") or [""])[0]
        job = get_current_job()
        run_dir = getattr(job, "run_dir", None) if job else None
        if not run_dir or not rel_text:
            json_error(self, "ASSET_NOT_FOUND", "缩略图不存在", "当前没有可读取的候选缩略图。", HTTPStatus.NOT_FOUND)
            return
        run_dir = Path(run_dir).resolve()
        if run_id and run_id != run_dir.name:
            json_error(self, "ASSET_NOT_FOUND", "缩略图不属于当前任务", "请刷新任务状态后重试。", HTTPStatus.NOT_FOUND)
            return
        cache_dir = CacheStore(run_dir).cache_dir
        try:
            asset_path = safe_resolve(cache_dir, unquote(rel_text).replace("\\", "/"))
        except ValueError:
            json_error(self, "ASSET_PATH_REJECTED", "缩略图路径越界", "已拒绝访问非缓存目录资源。", HTTPStatus.BAD_REQUEST)
            return
        thumbnail_root = (cache_dir / THUMBNAIL_DIR_NAME).resolve()
        if not is_relative_to(asset_path, thumbnail_root) or not asset_path.exists() or not asset_path.is_file():
            json_error(self, "ASSET_NOT_FOUND", "缩略图不存在", "请刷新任务状态后重试。", HTTPStatus.NOT_FOUND)
            return
        send_static_file(self, asset_path)

    def handle_help_doc(self) -> None:
        if not HELP_DOC_PATH.exists() or not HELP_DOC_PATH.is_file():
            json_error(self, "HELP_DOC_NOT_FOUND", "教程文档不存在", "请确认 docs/Cookie获取简短教程.md 是否存在。", HTTPStatus.NOT_FOUND)
            return
        try:
            markdown = HELP_DOC_PATH.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            markdown = HELP_DOC_PATH.read_text(encoding="utf-8-sig")
        send_json(self, {"markdown": markdown, "path": _rel_display_path(HELP_DOC_PATH)})

    def handle_open_result_dir(self) -> None:
        payload = parse_json_body(self)
        run_dir_value = (payload.get("run_dir") or "").strip() if payload else ""
        if run_dir_value:
            result_dir = confine_run_dir(Path(run_dir_value))
            if not result_dir.exists() or not result_dir.is_dir():
                result_dir = None
        else:
            result_dir = current_result_dir_path()
        if not result_dir:
            raise ValueError("当前没有可打开的导出目录。")
        open_local_path(result_dir)
        send_json(self, {"path": str(result_dir)})

    def handle_cookie_auto(self) -> None:
        payload = parse_json_body(self)
        browser = normalize_browser_name(payload.get("browser"))
        browser_label = browser_display_name(browser)
        console_log(f"正在自动读取 {browser_label} Cookie...")
        cookie = get_weibo_cookie_header(browser=browser)
        console_log(f"{browser_label} Cookie 自动读取成功。")
        console_log(f"等待 3 秒后关闭调试 {browser_label}，确保浏览器登录状态写入本地配置目录。")
        time.sleep(3)
        debug_browser_closed = close_debug_browser(browser)
        if debug_browser_closed:
            console_log(f"调试 {browser_label} 已自动关闭。")
        send_json(
            self,
            {
                "cookie": cookie,
                "browser": browser,
                "browser_label": browser_label,
                "debug_browser_closed": debug_browser_closed,
                "debug_edge_closed": debug_browser_closed if browser == "edge" else False,
            },
        )

    def handle_cookie_edge_debug(self) -> None:
        payload = parse_json_body(self)
        browser = normalize_browser_name(payload.get("browser"))
        browser_label = browser_display_name(browser)
        console_log(f"正在打开调试 {browser_label}...")
        endpoint = launch_debug_browser(browser, ROOT_DIR / f".{browser}_cdp_profile")
        console_log(f"调试 {browser_label} 已启动：{endpoint}")
        send_json(self, {"endpoint": endpoint, "browser": browser, "browser_label": browser_label})

    def handle_cookie_clear_cdp_cache(self) -> None:
        console_log("正在清理 CDP 调试缓存...")
        result = clear_cdp_debug_cache(ROOT_DIR)
        deleted_count = len(result.get("deleted") or [])
        missing_count = len(result.get("missing") or [])
        errors = list(result.get("errors") or [])
        if errors:
            send_json(
                self,
                {
                    "ok": False,
                    **result,
                    "error": {
                        "code": "CDP_CACHE_CLEAR_FAILED",
                        "message": "CDP 调试缓存清理不完整",
                        "suggestion": "请关闭调试浏览器窗口后重试。",
                    },
                },
                HTTPStatus.CONFLICT,
            )
            return
        console_log(f"CDP 调试缓存清理完成：删除 {deleted_count} 个，未找到 {missing_count} 个。")
        send_json(self, {"ok": True, **result})

    def handle_cookie_extract(self) -> None:
        payload = parse_json_body(self)
        cookie = extract_cookie_from_text(str(payload.get("text") or ""))
        if not cookie:
            raise ValueError("粘贴内容中未识别到 Cookie。")
        send_json(self, {"cookie": cookie})

    def handle_unknown_error(self, path: str, err: Exception) -> None:
        if path == "/api/preflight":
            json_error(self, "PREFLIGHT_FAILED", "预检查失败", "请检查输入参数后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if path == "/api/check-cookie":
            json_error(self, "COOKIE_CHECK_FAILED", "Cookie 检测失败", "请确认已登录微博网页，或重新获取 Cookie。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if path == "/api/clear-config":
            json_error(self, "CLEAR_CONFIG_FAILED", "清空配置失败", "请确认配置文件没有被其他程序占用后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        # str(err) on Windows routinely embeds C:\Users\<real name>\... . Keep
        # the detail on the operator's console; the page gets the type only.
        console_log(f"接口 {path} 执行失败：{type(err).__name__}: {err}")
        json_error(
            self,
            "INTERNAL_ERROR",
            "任务执行失败",
            f"发生了未预期的错误（{type(err).__name__}），详情见命令行窗口日志。",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def build_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    checks = validate_config_payload(payload)
    duplicate = find_duplicate_topic_issue(payload)
    if duplicate:
        checks.append({
            "id": "duplicate_issue",
            "label": "周报期数",
            "status": "error",
            "message": build_duplicate_topic_issue_message(duplicate),
        })
    else:
        checks.append({
            "id": "duplicate_issue",
            "label": "周报期数",
            "status": "ok",
            "message": "当前超话与期数未发现重复历史。",
        })
    job = get_current_job()
    if job and job.status in ACTIVE_STATUSES:
        checks.append({"id": "active_job", "label": "任务状态", "status": "error", "message": "当前已有任务正在运行。请等待完成或取消后再开始。"})
    else:
        checks.append({"id": "active_job", "label": "任务状态", "status": "ok", "message": "当前没有运行中的任务。"})
    can_start = not any(item["status"] == "error" for item in checks)
    return {"can_start": can_start, "checks": checks}


def find_duplicate_topic_issue(payload: dict[str, Any]) -> dict[str, Any] | None:
    super_topic = str(payload.get("super_topic") or "").strip()
    issue = normalize_issue_value(payload.get("issue")) or str(calculate_weekly_issue(_topic_preview_reference(payload)))
    if not super_topic or not issue:
        return None
    return find_history_duplicate(super_topic, issue)


def build_duplicate_topic_issue_message(item: dict[str, Any]) -> str:
    title = str(item.get("title_with_issue") or item.get("report_title") or item.get("super_topic_name") or item.get("run_id") or "该周报")
    run_id = str(item.get("run_id") or "")
    if run_id:
        return f"已存在相同超话与期数的历史任务：{title}（{run_id}）。"
    return f"已存在相同超话与期数的历史任务：{title}。"


def resolve_topic_preview(
    payload: dict[str, Any],
    *,
    client_factory: Any = WeiboClient,
) -> dict[str, str]:
    super_topic = str(payload.get("super_topic") or "").strip()
    topic_id = parse_super_topic_id(super_topic) if super_topic else ""
    issue = normalize_issue_value(payload.get("issue")) or str(calculate_weekly_issue(_topic_preview_reference(payload)))
    if not topic_id:
        return {
            "super_topic_id": "",
            "topic_name": "",
            "issue": issue,
            "title": "",
            "title_with_issue": "",
            "source": "empty",
            "message": "无法解析超话 ID，请检查链接或 ID。",
        }

    topic_name = normalize_super_topic_name(super_topic)
    source = "fallback" if topic_name else "id"
    message = "已解析超话 ID，等待识别名称。"
    cookie = resolve_payload_cookie(payload)
    if cookie:
        try:
            client = client_factory(cookie=cookie, timeout=(3, 8), retry=0, pause_seconds=0)
            data = client.get_json(
                CHAOHUA_API_URL,
                params=initial_chaohua_params(topic_id),
                headers={
                    "Referer": f"https://weibo.com/p/{topic_id}/super_index",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            fetched_name = normalize_super_topic_name(extract_chaohua_topic_name(data))
            if fetched_name:
                topic_name = fetched_name
                source = "chaohua_api"
                message = "已识别超话名称。"
        except Exception as err:
            message = f"已解析超话 ID，但名称识别失败：{type(err).__name__}"
    else:
        message = "已解析超话 ID；填写 Cookie 后可识别超话名称。"

    title = build_report_title(topic_name, super_topic)
    title_with_issue = format_report_title_with_issue(title, issue)
    if source == "chaohua_api":
        message = title_with_issue
    return {
        "super_topic_id": topic_id,
        "topic_name": topic_name,
        "issue": issue,
        "title": title,
        "title_with_issue": title_with_issue,
        "source": source,
        "message": message,
    }


def _topic_preview_reference(payload: dict[str, Any]) -> Any:
    for key in ("window_end", "window_start"):
        try:
            return parse_datetime_local(payload.get(key))
        except ValueError:
            continue
    return None


def check_cookie_state(payload: dict[str, Any]) -> dict[str, str]:
    cookie = resolve_payload_cookie(payload)
    super_topic = str(payload.get("super_topic") or "").strip()
    topic_id = parse_super_topic_id(super_topic) if super_topic else None
    return WeiboClient(cookie=cookie, timeout=10, retry=0).check_cookie(topic_id)


def parse_optional_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def allowed_run_dir_roots() -> list[Path]:
    """Directories a run directory is allowed to live in.

    ROOT_DIR itself is deliberately absent: reexport writes fixed file names
    (weekly_report.md, weibo_posts.xlsx, manifest.json...) into whatever
    run_dir it is handed, so allowing the whole project tree would make
    run_dir="web" a legal write target. It only failed before because the
    cache lookup happened to miss -- accidental safety, not designed safety.
    """
    configured_output = normalize_output_dir(load_saved_config().get("output_dir")).resolve()
    return [(ROOT_DIR / "output").resolve(), configured_output]


def confine_run_dir(path: Path) -> Path:
    resolved = path.expanduser()
    resolved = (ROOT_DIR / resolved).resolve() if not resolved.is_absolute() else resolved.resolve()
    if not any(is_relative_to(resolved, root) for root in allowed_run_dir_roots()):
        raise ValueError("运行目录不在允许的项目或导出目录范围内。")
    if not RUN_DIR_RE.match(resolved.name):
        raise ValueError("运行目录名无效，应形如 20260601_184009。")
    return resolved


def resolve_run_dir_from_payload(payload: dict[str, Any]) -> Path:
    raw = str(payload.get("run_dir") or "").strip()
    if not raw:
        raise ValueError("请填写运行目录。")
    return confine_run_dir(Path(raw))


def resolve_report_md_path(raw: str) -> Path | None:
    """Confine a caller-supplied md_path to a real run directory.

    Unconstrained, this parameter read any file on disk: the preview endpoint
    returned it as Markdown, and the asset endpoint used its parent as the base
    directory for further reads, which defeated that endpoint's own traversal
    check.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        candidate = Path(text).expanduser()
        candidate = (ROOT_DIR / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        confine_run_dir(candidate.parent)
    except (ValueError, OSError):
        return None
    if candidate.suffix.lower() != ".md":
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def current_report_md_path() -> Path | None:
    job = get_current_job()
    if not job:
        return None
    snapshot = job.snapshot()
    result = snapshot.get("result")
    if not isinstance(result, dict):
        return None
    md_path = result.get("md")
    if not md_path:
        return None
    path = Path(str(md_path))
    if path.exists() and path.is_file():
        return path.resolve()
    return None


def current_result_dir_path() -> Path | None:
    job = get_current_job()
    if not job:
        return None
    snapshot = job.snapshot()
    result = snapshot.get("result")
    if not isinstance(result, dict):
        return None
    run_dir = result.get("run_dir")
    if not run_dir:
        return None
    path = Path(str(run_dir))
    if path.exists() and path.is_dir():
        return path.resolve()
    return None


def _rel_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def open_local_path(path: Path) -> None:
    # Explicit invariant: startfile on a file would *execute* it, so the
    # directory check must not be left implicit in the callers.
    if not path.is_dir():
        raise ValueError("只允许打开目录。")
    if os.name == "nt":
        os.startfile(str(path))
        return
    raise RuntimeError("当前系统不支持从页面打开本地目录。")


def resolve_report_asset_path(report_path: Path, rel_text: str) -> Path | None:
    if not rel_text or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", rel_text):
        return None
    base = report_path.parent.resolve()
    try:
        target = safe_resolve(base, unquote(rel_text).replace("\\", "/"))
    except ValueError:
        return None
    if target.exists() and target.is_file():
        return target
    return None


def resolve_static_path(url_path: str) -> Path | None:
    rel = "index.html" if url_path in {"", "/", "/index.html"} else unquote(url_path).lstrip("/")
    try:
        target = safe_resolve(WEB_ROOT, rel)
    except ValueError:
        return None
    if target.is_file():
        return target
    return None
