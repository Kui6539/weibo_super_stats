from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import threading
import uuid
import webbrowser
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from cookie_helper import (
    CookieFetchError,
    extract_cookie_from_text,
    get_weibo_cookie_header,
    launch_edge_debug_browser,
)
from crawler import (
    CrawlConfig,
    CrawlError,
    WeiboSuperTopicCrawler,
    analyze_active_period,
    build_comment_leaderboards,
    build_summary,
    download_post_images,
    export_posts_csv,
    export_posts_xlsx,
    export_weekly_report_docx,
    export_weekly_report_md,
    export_weekly_report_sum_docx,
    select_weekly_posts,
    write_summary_txt,
)

APP_HOST = "127.0.0.1"
APP_PORT = 8765
WEB_ROOT = Path(__file__).with_name("web")
CONFIG_PATH = Path(__file__).with_name("weibo_stats_config.json")
DEFAULT_SUPER_TOPIC = "https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index"
ACTIVE_STATUSES = {"running", "awaiting_selection", "exporting"}

_console_lock = threading.Lock()
_job_lock = threading.RLock()
_current_job: CrawlJob | None = None


def console_log(message: str, timestamp: str | None = None) -> None:
    stamp = timestamp or datetime.now().strftime("%H:%M:%S")
    with _console_lock:
        print(f"[{stamp}] {message}", flush=True)


def default_time_window() -> tuple[datetime, datetime]:
    now = datetime.now()
    end_dt = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < end_dt:
        end_dt -= timedelta(days=1)
    return end_dt - timedelta(days=7), end_dt


def datetime_local_value(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def parse_datetime_local(value: Any) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        parsed = _parse_datetime_with_format(text, fmt)
        if parsed is not None:
            return parsed
    raise ValueError("日期时间格式无效")


def _parse_datetime_with_format(text: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(text, fmt)
    except ValueError:
        return None


def normalize_output_dir(value: Any) -> Path:
    raw = str(value or "").strip() or "output"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def build_config(payload: dict[str, Any]) -> tuple[CrawlConfig, Path]:
    super_topic = str(payload.get("super_topic") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    if not super_topic:
        raise ValueError("请填写超话链接或ID。")
    if not cookie:
        raise ValueError("请先填写 Cookie。")

    try:
        max_pages = int(str(payload.get("max_pages", "80")).strip())
        topic_comment_factor = float(str(payload.get("topic_comment_factor", "1.0")).strip())
        pause_seconds = float(str(payload.get("pause_seconds", "1.0")).strip())
    except ValueError as err:
        raise ValueError("最大翻页页数、话题评论系数、请求间隔必须是数字。") from err

    if max_pages <= 0:
        raise ValueError("最大翻页页数需为正数。")
    if pause_seconds < 0:
        raise ValueError("请求间隔需非负。")
    if topic_comment_factor < 0.5:
        raise ValueError("话题评论系数需 >= 0.5。")

    window_start = parse_datetime_local(payload.get("window_start"))
    window_end = parse_datetime_local(payload.get("window_end"))
    if window_end <= window_start:
        raise ValueError("结束时间必须晚于开始时间。")

    days_window = max(1, int((window_end - window_start).days) + 1)
    cfg = CrawlConfig(
        super_topic=super_topic,
        cookie=cookie,
        max_pages=max_pages,
        days_window=days_window,
        topic_comment_factor=topic_comment_factor,
        pause_seconds=pause_seconds,
        window_start=window_start,
        window_end=window_end,
        carryover_hours=0,
    )
    return cfg, normalize_output_dir(payload.get("output_dir"))


def load_saved_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as err:
        console_log(f"读取配置失败：{type(err).__name__}: {err}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "super_topic": str(data.get("super_topic") or "").strip(),
        "cookie": str(data.get("cookie") or "").strip(),
        "output_dir": str(data.get("output_dir") or "").strip(),
    }


def save_user_config(payload: dict[str, Any]) -> dict[str, str]:
    current = load_saved_config()
    for key in ("super_topic", "cookie", "output_dir"):
        if key in payload:
            current[key] = str(payload.get(key) or "").strip()
    CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return current


def compact_content(value: Any, max_chars: int = 420) -> str:
    content = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(content) > max_chars:
        return content[:max_chars] + "..."
    return content


def to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def serialize_candidate(post: dict, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "rank": index + 1,
        "user_name": str(post.get("user_name", "未知作者") or "未知作者"),
        "publish_time": str(post.get("publish_time", "") or ""),
        "content": compact_content(post.get("content", "")),
        "score": round(to_float(post.get("score")), 2),
        "likes": to_int(post.get("likes")),
        "comments": to_int(post.get("comments")),
        "reposts": to_int(post.get("reposts")),
        "post_url": str(post.get("post_url", "") or ""),
    }


class CrawlJob:
    def __init__(self, cfg: CrawlConfig, output_dir: Path) -> None:
        self.id = str(uuid.uuid4())
        self.cfg = cfg
        self.output_dir = output_dir
        self.status = "running"
        self.started_at = datetime.now()
        self.updated_at = self.started_at
        self.logs: list[dict[str, str]] = []
        self.candidates: list[dict[str, Any]] = []
        self.required_pick_count = 0
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.selected_indexes: list[int] | None = None

        self._candidate_posts: list[dict] = []
        self._lock = threading.RLock()
        self._selection_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"crawl-{self.id[:8]}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.logs.append({"time": timestamp, "message": str(message)})
            if len(self.logs) > 1000:
                self.logs = self.logs[-1000:]
            self.updated_at = datetime.now()
        console_log(str(message), timestamp=timestamp)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "status": self.status,
                "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "logs": list(self.logs),
                "candidates": list(self.candidates),
                "required_pick_count": self.required_pick_count,
                "result": self.result,
                "error": self.error,
            }

    def submit_selection(self, indexes: list[Any]) -> None:
        with self._lock:
            if self.status != "awaiting_selection":
                raise ValueError("当前任务不在人工筛选阶段。")

            cleaned: list[int] = []
            for item in indexes:
                try:
                    idx = int(item)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(self._candidate_posts) and idx not in cleaned:
                    cleaned.append(idx)

            target = self.required_pick_count
            if len(self._candidate_posts) >= target and len(cleaned) != target:
                raise ValueError(f"请恰好勾选 {target} 条帖子。")
            if not cleaned:
                raise ValueError("请至少勾选 1 条帖子。")

            self.selected_indexes = cleaned[:target]
            self.status = "exporting"
            self.updated_at = datetime.now()
        self._selection_event.set()

    def cancel_selection(self) -> None:
        with self._lock:
            if self.status != "awaiting_selection":
                raise ValueError("当前任务不在人工筛选阶段。")
            self.status = "cancelled"
            self.updated_at = datetime.now()
        self.log("已取消人工筛选。")
        self._selection_event.set()

    def _set_failed(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = message
            self.updated_at = datetime.now()

    def _set_completed(self, result: dict[str, Any]) -> None:
        with self._lock:
            self.status = "completed"
            self.result = result
            self.updated_at = datetime.now()

    def _run(self) -> None:
        try:
            self.log("开始任务...")
            self.log("计算方式：Python")
            if self.cfg.window_start and self.cfg.window_end:
                self.log(
                    "自定义日期区间："
                    f"{self.cfg.window_start.strftime('%Y-%m-%d %H:%M')} -> "
                    f"{self.cfg.window_end.strftime('%Y-%m-%d %H:%M')}"
                )

            crawler = WeiboSuperTopicCrawler(cookie=self.cfg.cookie, progress_callback=self.log)
            posts_all = crawler.crawl(self.cfg)
            active_period = analyze_active_period(posts_all)
            if int(active_period.get("valid_posts", 0) or 0) > 0:
                h = int(active_period.get("top_hour", 0) or 0)
                c = int(active_period.get("top_hour_count", 0) or 0)
                s = int(active_period.get("top_two_hour_start", 0) or 0)
                c2 = int(active_period.get("top_two_hour_count", 0) or 0)
                rec = int(active_period.get("recommended_anchor_hour", s) or s)
                self.log(f"活跃单小时高峰：{h:02d}:00-{h:02d}:59（{c}帖）")
                self.log(f"活跃两小时高峰：{s:02d}:00-{(s + 2) % 24:02d}:00（{c2}帖）")
                self.log(f"建议固定周统计时间：每周 {rec:02d}:00")

            candidates = select_weekly_posts(posts_all, limit=20)
            if not candidates:
                raise CrawlError("当前窗口内没有可用于周报的候选帖子。")

            target = min(15, len(candidates))
            with self._lock:
                self._candidate_posts = list(candidates)
                self.candidates = [serialize_candidate(post, i) for i, post in enumerate(candidates)]
                self.required_pick_count = target
                self.status = "awaiting_selection"
                self.updated_at = datetime.now()
            self.log(f"等待人工筛选：候选 {len(candidates)} 条，默认勾选前 {target} 条。")

            self._selection_event.wait()
            with self._lock:
                if self.status == "cancelled":
                    return
                selected_indexes = list(self.selected_indexes or [])

            selected_posts = [candidates[i] for i in selected_indexes if 0 <= i < len(candidates)]
            if not selected_posts:
                raise CrawlError("没有可导出的入选帖子。")
            self.log(f"人工筛选完成：最终导出 {len(selected_posts)} 条。")

            self.output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.output_dir / ts
            run_dir.mkdir(parents=True, exist_ok=True)
            image_dir = run_dir / "images"

            self.log("正在下载帖子/评论图片...")
            download_post_images(
                posts=selected_posts,
                image_dir=image_dir,
                cookie=self.cfg.cookie,
                progress_callback=self.log,
            )

            summary = build_summary(selected_posts)
            all_posts_summary = build_summary(posts_all)
            leaderboards = build_comment_leaderboards(posts_all, top_n=3)

            xlsx_path = run_dir / "weibo_posts.xlsx"
            csv_path = run_dir / "weibo_posts.csv"
            txt_path = run_dir / "weibo_summary.txt"
            report_docx_path = run_dir / "warma_weekly_report.docx"
            report_sum_docx_path = run_dir / "weekly_report_sum.docx"
            report_md_path = run_dir / "warma_weekly_report.md"

            export_posts_xlsx(selected_posts, xlsx_path)
            export_posts_csv(selected_posts, csv_path)
            write_summary_txt(
                summary,
                txt_path,
                leaderboards=leaderboards,
                active_period=active_period,
                all_posts_summary=all_posts_summary,
                carryover_hours=self.cfg.carryover_hours,
            )
            report_docx_paths = export_weekly_report_docx(
                selected_posts,
                report_docx_path,
                leaderboards=leaderboards,
                preselected=True,
            )
            report_sum_docx = export_weekly_report_sum_docx(
                selected_posts,
                report_sum_docx_path,
                leaderboards=leaderboards,
                preselected=True,
            )
            export_weekly_report_md(selected_posts, report_md_path, leaderboards=leaderboards, preselected=True)

            self.log(f"抓取完成，共 {summary['total_posts']} 条帖子。")
            self.log(f"Excel 已保存：{xlsx_path}")
            self.log(f"CSV 已保存：{csv_path}")
            for path in report_docx_paths:
                size_mb = path.stat().st_size / 1000 / 1000 if path.exists() else 0
                self.log(f"DOCX 已保存：{path}（{size_mb:.2f} MB）")
            size_mb = report_sum_docx.stat().st_size / 1000 / 1000 if report_sum_docx.exists() else 0
            self.log(f"总 DOCX 已保存：{report_sum_docx}（{size_mb:.2f} MB）")
            self.log(f"MD 已保存：{report_md_path}")
            self.log(f"汇总已保存：{txt_path}")
            self.log(f"本次导出目录：{run_dir}")

            self._set_completed(
                {
                    "total_posts": summary["total_posts"],
                    "run_dir": str(run_dir),
                    "image_dir": str(image_dir),
                    "xlsx": str(xlsx_path),
                    "csv": str(csv_path),
                    "docx": [str(path) for path in report_docx_paths],
                    "docx_sum": str(report_sum_docx),
                    "md": str(report_md_path),
                    "summary": str(txt_path),
                }
            )
        except CrawlError as err:
            self.log(f"任务失败：{err}")
            self._set_failed(str(err))
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            self.log(f"任务失败：{message}")
            self._set_failed(message)


def get_current_job() -> CrawlJob | None:
    with _job_lock:
        return _current_job


def create_job(cfg: CrawlConfig, output_dir: Path) -> CrawlJob:
    global _current_job
    with _job_lock:
        if _current_job and _current_job.status in ACTIVE_STATUSES:
            raise RuntimeError("已有任务正在运行，请等待完成后再开始新的任务。")
        _current_job = CrawlJob(cfg, output_dir)
        _current_job.start()
        return _current_job


def app_defaults() -> dict[str, Any]:
    window_start, window_end = default_time_window()
    saved = load_saved_config()
    return {
        "super_topic": DEFAULT_SUPER_TOPIC,
        "cookie": "",
        "max_pages": 80,
        "topic_comment_factor": 1.0,
        "pause_seconds": 1.0,
        "window_start": datetime_local_value(window_start),
        "window_end": datetime_local_value(window_end),
        "output_dir": str(Path.cwd() / "output"),
    } | {key: value for key, value in saved.items() if value}


class AppRequestHandler(BaseHTTPRequestHandler):
    server_version = "WeiboStatsHTML/2.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/defaults":
            self._send_json({"defaults": app_defaults()})
            return
        if path == "/api/status":
            job = get_current_job()
            self._send_json({"job": job.snapshot() if job else None})
            return
        if path == "/api/report-preview":
            self._send_report_preview()
            return
        if path == "/api/report-asset":
            self._send_report_asset()
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        static_path = resolve_static_path(path)
        if static_path:
            self._send_static(static_path)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/start":
                payload = self._read_json()
                cfg, output_dir = build_config(payload)
                save_user_config(payload)
                job = create_job(cfg, output_dir)
                self._send_json({"job": job.snapshot()})
                return
            if path == "/api/config":
                payload = self._read_json()
                config = save_user_config(payload)
                self._send_json({"config": config})
                return
            if path == "/api/select":
                payload = self._read_json()
                job = get_current_job()
                if not job:
                    raise ValueError("没有正在运行的任务。")
                job.submit_selection(list(payload.get("indexes") or []))
                self._send_json({"job": job.snapshot()})
                return
            if path == "/api/cancel-selection":
                job = get_current_job()
                if not job:
                    raise ValueError("没有正在运行的任务。")
                job.cancel_selection()
                self._send_json({"job": job.snapshot()})
                return
            if path == "/api/cookie/auto":
                console_log("正在自动读取浏览器 Cookie...")
                cookie = get_weibo_cookie_header()
                console_log("Cookie 自动读取成功。")
                self._send_json({"cookie": cookie})
                return
            if path == "/api/cookie/edge-debug":
                console_log("正在打开调试 Edge...")
                endpoint = launch_edge_debug_browser(Path.cwd() / ".edge_cdp_profile")
                console_log(f"调试 Edge 已启动：{endpoint}")
                self._send_json({"endpoint": endpoint})
                return
            if path == "/api/cookie/extract":
                payload = self._read_json()
                cookie = extract_cookie_from_text(str(payload.get("text") or ""))
                if not cookie:
                    raise ValueError("粘贴内容中未识别到 Cookie。")
                self._send_json({"cookie": cookie})
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except CookieFetchError as err:
            console_log(f"Cookie 自动读取失败：{err}")
            self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as err:
            self._send_json({"error": str(err)}, HTTPStatus.CONFLICT)
        except ValueError as err:
            self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
        except Exception as err:
            self._send_json({"error": f"{type(err).__name__}: {err}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send_report_preview(self) -> None:
        report_path = current_report_md_path()
        if not report_path:
            self._send_json({"error": "当前没有可预览的 Markdown 周报。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            markdown = report_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            markdown = report_path.read_text(encoding="utf-8-sig")
        self._send_json(
            {
                "markdown": markdown,
                "path": str(report_path),
            }
        )

    def _send_report_asset(self) -> None:
        report_path = current_report_md_path()
        if not report_path:
            self._send_json({"error": "当前没有可预览的 Markdown 周报。"}, HTTPStatus.NOT_FOUND)
            return
        parsed = urlparse(self.path)
        rel_values = parse_qs(parsed.query).get("path", [])
        rel_text = rel_values[0] if rel_values else ""
        asset_path = resolve_report_asset_path(report_path, rel_text)
        if not asset_path:
            self._send_json({"error": "资源不存在。"}, HTTPStatus.NOT_FOUND)
            return
        self._send_static(asset_path)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(
            body,
            status=status,
            content_type="application/json; charset=utf-8",
        )

    def _send_static(self, path: Path) -> None:
        body = path.read_bytes()
        self._send_bytes(
            body,
            status=HTTPStatus.OK,
            content_type=content_type_for(path),
        )

    def _send_bytes(self, body: bytes, status: HTTPStatus, content_type: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError as err:
            if _is_client_disconnect(err):
                return
            raise


def content_type_for(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


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


def resolve_report_asset_path(report_path: Path, rel_text: str) -> Path | None:
    if not rel_text or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", rel_text):
        return None
    base = report_path.parent.resolve()
    target = (base / unquote(rel_text).replace("\\", "/")).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    if target.exists() and target.is_file():
        return target
    return None


def _is_client_disconnect(err: OSError) -> bool:
    if isinstance(err, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    return getattr(err, "winerror", None) in {10053, 10054, 10058}


def resolve_static_path(url_path: str) -> Path | None:
    rel = "index.html" if url_path in {"", "/", "/index.html"} else unquote(url_path).lstrip("/")
    root = WEB_ROOT.resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    if target.is_file():
        return target
    return None


def create_server(host: str, port: int) -> tuple[ThreadingHTTPServer, str]:
    ports = [port, *range(port + 1, port + 20)]
    last_error: OSError | None = None
    for candidate in ports:
        server, error = _try_create_server(host, candidate)
        if server:
            return server, f"http://{host}:{candidate}/"
        last_error = error
    raise RuntimeError(f"无法启动本地服务：{last_error}")


def _try_create_server(host: str, port: int) -> tuple[ThreadingHTTPServer | None, OSError | None]:
    try:
        return ThreadingHTTPServer((host, port), AppRequestHandler), None
    except OSError as err:
        return None, err


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="微博超话周报统计本地 Web 工具")
    parser.add_argument("--host", default=APP_HOST, help=f"监听地址，默认 {APP_HOST}")
    parser.add_argument("--port", default=APP_PORT, type=int, help=f"监听端口，默认 {APP_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server, url = create_server(args.host, args.port)
    console_log(f"微博超话周报统计已启动：{url}")
    console_log("命令行会实时滚动输出抓取日志；结束时按 Ctrl+C。")
    if not args.no_browser and os.environ.get("WEIBO_STATS_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console_log("正在关闭服务...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
