from __future__ import annotations

import os
import re
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from cookie_helper import (
    CookieFetchError,
    browser_display_name,
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
    save_user_config,
    save_preset,
    validate_config_payload,
)
from core.errors import WeiboStatsError, to_error_response
from core.history import (
    add_history_item_from_manifest,
    find_history_item,
    get_history_items,
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
from core.paths import is_relative_to, normalize_output_dir, safe_resolve
from crawler import parse_super_topic_id
from export.reexport import reexport_from_cache
from modules.crawler_client import WeiboClient
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


class AppRequestHandler(BaseHTTPRequestHandler):
    server_version = "WeiboStatsHTML/3.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/defaults":
            self.handle_get_config()
            return
        if path == "/api/presets":
            self.handle_get_presets()
            return
        if path == "/api/history":
            self.handle_history()
            return
        if path == "/api/status":
            self.handle_status()
            return
        if path == "/api/report-preview":
            self.handle_report_preview()
            return
        if path == "/api/report-asset":
            self.handle_report_asset()
            return
        if path == "/api/history/asset":
            self.handle_history_asset()
            return
        if path == "/api/help-doc":
            self.handle_help_doc()
            return
        if path == "/Background.png":
            if BACKGROUND_PATH.exists() and BACKGROUND_PATH.is_file():
                send_static_file(self, BACKGROUND_PATH)
            else:
                json_error(self, "NOT_FOUND", "背景图片不存在", "请确认 web/Background.png 是否存在。", HTTPStatus.NOT_FOUND)
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        static_path = resolve_static_path(path)
        if static_path:
            send_static_file(self, static_path)
            return
        json_error(self, "NOT_FOUND", "接口或页面不存在", "请检查访问地址。", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/preflight":
                self.handle_preflight()
                return
            if path == "/api/check-cookie":
                self.handle_check_cookie()
                return
            if path == "/api/clear-config":
                self.handle_clear_config()
                return
            if path == "/api/cancel-job":
                self.handle_cancel_job()
                return
            if path == "/api/cache-status":
                self.handle_cache_status()
                return
            if path == "/api/reexport":
                self.handle_reexport()
                return
            if path == "/api/history/scan":
                self.handle_history_scan()
                return
            if path == "/api/history/remove":
                self.handle_history_remove()
                return
            if path == "/api/history/cache-status":
                self.handle_history_cache_status()
                return
            if path == "/api/history/reexport":
                self.handle_history_reexport()
                return
            if path == "/api/history/open-dir":
                self.handle_history_open_dir()
                return
            if path == "/api/history/preview":
                self.handle_history_preview()
                return
            if path == "/api/presets/save":
                self.handle_presets_save()
                return
            if path == "/api/presets/delete":
                self.handle_presets_delete()
                return
            if path == "/api/presets/activate":
                self.handle_presets_activate()
                return
            if path == "/api/presets/duplicate":
                self.handle_presets_duplicate()
                return
            if path == "/api/output/summary":
                self.handle_output_summary()
                return
            if path == "/api/output/cleanup-preview":
                self.handle_output_cleanup_preview()
                return
            if path == "/api/output/cleanup":
                self.handle_output_cleanup()
                return
            if path == "/api/start":
                self.handle_start()
                return
            if path == "/api/config":
                self.handle_save_config()
                return
            if path == "/api/select":
                self.handle_select()
                return
            if path == "/api/cancel-selection":
                self.handle_cancel_selection()
                return
            if path == "/api/cookie/auto":
                self.handle_cookie_auto()
                return
            if path == "/api/cookie/edge-debug":
                self.handle_cookie_edge_debug()
                return
            if path == "/api/cookie/extract":
                self.handle_cookie_extract()
                return
            if path == "/api/open-result-dir":
                self.handle_open_result_dir()
                return
            json_error(self, "NOT_FOUND", "接口不存在", "请检查请求地址。", HTTPStatus.NOT_FOUND)
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
        )
        json_ok(self, data, **data)

    def handle_report_preview(self) -> None:
        parsed = urlparse(self.path)
        qs_md = parse_qs(parsed.query).get("md_path", [])
        if qs_md and qs_md[0]:
            path = Path(qs_md[0])
            report_path = path.resolve() if path.exists() and path.is_file() else None
        else:
            report_path = current_report_md_path()
        if not report_path:
            json_error(self, "NO_MARKDOWN_REPORT", "当前没有可预览的 Markdown 周报", "请先完成一次导出。", HTTPStatus.NOT_FOUND)
            return
        try:
            markdown = report_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            markdown = report_path.read_text(encoding="utf-8-sig")
        send_json(self, {"markdown": markdown, "path": _rel_display_path(report_path)})

    def handle_report_asset(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        qs_md = qs.get("md_path", [])
        if qs_md and qs_md[0]:
            md_file = Path(qs_md[0])
            report_path = md_file.resolve() if md_file.exists() and md_file.is_file() else None
        else:
            report_path = current_report_md_path()
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
            result_dir = Path(run_dir_value)
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
        json_error(self, "INTERNAL_ERROR", "任务执行失败", f"{type(err).__name__}: {err}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def build_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    checks = validate_config_payload(payload)
    job = get_current_job()
    if job and job.status in ACTIVE_STATUSES:
        checks.append({"id": "active_job", "label": "任务状态", "status": "error", "message": "当前已有任务正在运行。请等待完成或取消后再开始。"})
    else:
        checks.append({"id": "active_job", "label": "任务状态", "status": "ok", "message": "当前没有运行中的任务。"})
    can_start = not any(item["status"] == "error" for item in checks)
    return {"can_start": can_start, "checks": checks}


def check_cookie_state(payload: dict[str, Any]) -> dict[str, str]:
    cookie = str(payload.get("cookie") or "").strip()
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


def resolve_run_dir_from_payload(payload: dict[str, Any]) -> Path:
    raw = str(payload.get("run_dir") or "").strip()
    if not raw:
        raise ValueError("请填写运行目录。")
    path = Path(raw).expanduser()
    path = (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()
    configured_output = normalize_output_dir(load_saved_config().get("output_dir")).resolve()
    allowed_roots = [ROOT_DIR.resolve(), configured_output]
    if not any(is_relative_to(path, root) for root in allowed_roots):
        raise ValueError("运行目录不在允许的项目或导出目录范围内。")
    return path


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
