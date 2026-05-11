from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import threading
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from cookie_helper import (
    CookieFetchError,
    close_edge_debug_browser,
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
    parse_super_topic_id,
    select_weekly_posts,
    write_summary_txt,
)

APP_HOST = "127.0.0.1"
APP_PORT = 8765
WEB_ROOT = Path(__file__).with_name("web")
CONFIG_PATH = Path(__file__).with_name("weibo_stats_config.json")
HELP_DOC_PATH = Path(__file__).with_name("Cookie获取简短教程.md")
BACKGROUND_PATH = WEB_ROOT / "Background.png"
DEFAULT_SUPER_TOPIC = "https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index"
ACTIVE_STATUSES = {"running", "awaiting_selection", "exporting"}
WEIBO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
STAGE_LABELS = {
    "idle": "未开始",
    "init": "初始化任务",
    "crawl": "抓取帖子数据",
    "hydrate": "补全微博正文",
    "score": "评论分析与评分",
    "selection": "等待人工筛选",
    "images": "下载图片",
    "export": "导出文件",
    "completed": "任务完成",
    "failed": "任务失败",
    "cancelled": "任务已取消",
}
STAGE_ORDER = ["init", "crawl", "hydrate", "score", "selection", "images", "export", "completed"]
EVENT_LIMIT = 1000
SNAPSHOT_LIMIT = 300

_console_lock = threading.Lock()
_job_lock = threading.RLock()
_current_job: CrawlJob | None = None


class JobCancelled(Exception):
    pass


@dataclass
class JobEvent:
    type: str
    stage: str
    message: str
    level: str = "info"
    current: int | None = None
    total: int | None = None
    percent: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "stage": self.stage,
            "message": self.message,
            "level": self.level,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "payload": _sanitize_event_payload(self.payload),
            "created_at": self.created_at,
        }


def console_log(message: str, timestamp: str | None = None) -> None:
    stamp = timestamp or datetime.now().strftime("%H:%M:%S")
    with _console_lock:
        print(f"[{stamp}] {message}", flush=True)


def _sanitize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if "cookie" in lowered or lowered in {"sub", "subp", "scf", "wbpsess"}:
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_event_payload(value)
        elif isinstance(value, list):
            clean[key] = [
                _sanitize_event_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            clean[key] = value
    return clean


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage or STAGE_LABELS["idle"])


def clamp_percent(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(100.0, number)), 2)


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
    theme = str(data.get("theme") or "").strip().lower()
    if theme not in {"dark", "light"}:
        theme = ""
    advanced_mode = str(data.get("advanced_mode") or "").strip().lower()
    if advanced_mode not in {"true", "false"}:
        advanced_mode = ""
    return {
        "super_topic": str(data.get("super_topic") or "").strip(),
        "cookie": str(data.get("cookie") or "").strip(),
        "max_pages": str(data.get("max_pages") or "").strip(),
        "topic_comment_factor": str(data.get("topic_comment_factor") or "").strip(),
        "pause_seconds": str(data.get("pause_seconds") or "").strip(),
        "output_dir": str(data.get("output_dir") or "").strip(),
        "theme": theme,
        "advanced_mode": advanced_mode,
    }


def save_user_config(payload: dict[str, Any]) -> dict[str, str]:
    current = load_saved_config()
    for key in ("super_topic", "cookie", "max_pages", "topic_comment_factor", "pause_seconds", "output_dir"):
        if key in payload:
            current[key] = str(payload.get(key) or "").strip()
    if "theme" in payload:
        theme = str(payload.get("theme") or "").strip().lower()
        if theme in {"dark", "light"}:
            current["theme"] = theme
    if "advanced_mode" in payload:
        current["advanced_mode"] = "true" if _as_bool(payload.get("advanced_mode")) else "false"
    CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return current


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "是"}


def compact_content(value: Any, max_chars: int = 420) -> str:
    content = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(content) > max_chars:
        return content[:max_chars] + "..."
    return content


def visible_job_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    run_dir = str(result.get("run_dir") or "").strip()
    if run_dir and not Path(run_dir).exists():
        return None
    return dict(result)


def to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def infer_log_level(message: str) -> str:
    text = str(message or "")
    if re.search(r"失败|错误|异常|访客验证|不可写|invalid|error|failed", text, re.I):
        return "error"
    if re.search(r"警告|可能|跳过|无命中|等待|建议|warning", text, re.I):
        return "warning"
    if re.search(r"成功|完成|已保存|已生成|可用|completed|saved", text, re.I):
        return "success"
    return "info"


def serialize_candidate(post: dict, index: int) -> dict[str, Any]:
    content = str(post.get("content", "") or "")
    image_count = to_int(post.get("image_count"))
    if image_count <= 0:
        image_count = len(split_multi_value(post.get("original_image_urls")))
    preview_paths = [
        path
        for path in split_multi_value(post.get("image_local_paths"))
        if Path(path).exists() and Path(path).is_file()
    ][:3]
    return {
        "index": index,
        "rank": index + 1,
        "user_name": str(post.get("user_name", "未知作者") or "未知作者"),
        "publish_time": str(post.get("publish_time", "") or ""),
        "content": compact_content(content),
        "content_excerpt": compact_content(content, max_chars=160),
        "content_full": content,
        "score": round(to_float(post.get("score")), 2),
        "likes": to_int(post.get("likes")),
        "comments": to_int(post.get("comments")),
        "reposts": to_int(post.get("reposts")),
        "post_url": str(post.get("post_url", "") or ""),
        "image_count": image_count,
        "image_preview_paths": preview_paths,
    }


def split_multi_value(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = [str(item).strip() for item in value]
    else:
        rows = [part.strip() for part in re.split(r"\s*\|\s*|\n+", str(value or ""))]
    return [item for item in rows if item]


def build_result_manifest(result: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(str(result.get("run_dir") or "")).resolve()

    def item(label: str, raw_path: Any, action: str | None = None) -> dict[str, Any]:
        text = str(raw_path or "").strip()
        path = Path(text) if text else Path()
        exists = bool(text) and path.exists()
        rel = ""
        if text:
            try:
                rel = str(path.resolve().relative_to(run_dir))
            except Exception:
                rel = text
        return {
            "label": label,
            "name": path.name if text else "",
            "path": text,
            "relative_path": rel,
            "exists": exists,
            "action": action or "",
        }

    docx_rows = [item("DOCX", path) for path in result.get("docx", []) or []]
    files = {
        "markdown": item("Markdown", result.get("md"), action="preview_markdown"),
        "docx": docx_rows,
        "docx_sum": item("总 DOCX", result.get("docx_sum")),
        "xlsx": item("XLSX", result.get("xlsx")),
        "csv": item("CSV", result.get("csv")),
        "summary": item("summary txt", result.get("summary")),
        "images": item("images 图片目录", result.get("image_dir"), action="open_result_dir"),
    }
    return {
        "run_dir": str(run_dir),
        "files": files,
        "warnings": list(result.get("warnings") or []),
        "failed_image_count": to_int(result.get("failed_image_count")),
    }


def count_expected_images(posts: list[dict]) -> int:
    total = 0
    for post in posts:
        total += len(split_multi_value(post.get("original_image_urls")))
        for comment in list(post.get("top_comments_data") or []):
            total += len(split_multi_value(comment.get("image_urls")))
    return total


def count_downloaded_images(posts: list[dict]) -> int:
    total = 0
    for post in posts:
        paths = split_multi_value(post.get("image_local_paths_all"))
        if not paths:
            paths = split_multi_value(post.get("image_local_paths")) + split_multi_value(
                post.get("comment_image_local_paths")
            )
        total += sum(1 for path in paths if Path(path).exists())
    return total


class CrawlJob:
    def __init__(self, cfg: CrawlConfig, output_dir: Path) -> None:
        self.id = str(uuid.uuid4())
        self.cfg = cfg
        self.output_dir = output_dir
        self.status = "running"
        self.started_at = datetime.now()
        self.updated_at = self.started_at
        self.stage = "idle"
        self.stage_label = STAGE_LABELS["idle"]
        self.last_work_stage = "init"
        self.progress: dict[str, Any] = {
            "current": 0,
            "total": 0,
            "percent": 0.0,
            "message": "",
        }
        self.subtasks: list[dict[str, Any]] = []
        self.logs: list[dict[str, str]] = []
        self.events: list[JobEvent] = []
        self.candidates: list[dict[str, Any]] = []
        self.required_pick_count = 0
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.selected_indexes: list[int] | None = None
        self.cancel_requested = threading.Event()

        self._candidate_posts: list[dict] = []
        self._lock = threading.RLock()
        self._selection_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"crawl-{self.id[:8]}", daemon=True)

    def start(self) -> None:
        self.set_stage("init", message="任务初始化")
        self.thread.start()

    def log(self, message: str) -> None:
        self.add_log(message)

    def set_stage(self, stage: str, label: str | None = None, message: str | None = None) -> None:
        clean_stage = stage if stage in STAGE_LABELS else "idle"
        with self._lock:
            self.stage = clean_stage
            if clean_stage in STAGE_ORDER:
                self.last_work_stage = clean_stage
            self.stage_label = label or stage_label(clean_stage)
            if message is not None:
                self.progress["message"] = str(message)
            self.updated_at = datetime.now()
            self._append_event_unlocked(
                JobEvent(
                    type="progress",
                    stage=self.stage,
                    message=message or self.stage_label,
                    level="info",
                    current=_optional_int(self.progress.get("current")),
                    total=_optional_int(self.progress.get("total")),
                    percent=clamp_percent(self.progress.get("percent")),
                )
            )

    def update_progress(
        self,
        current: int | None = None,
        total: int | None = None,
        percent: float | None = None,
        message: str | None = None,
        stage: str | None = None,
    ) -> None:
        with self._lock:
            if stage:
                self.stage = stage if stage in STAGE_LABELS else self.stage
                self.stage_label = stage_label(self.stage)
                if self.stage in STAGE_ORDER:
                    self.last_work_stage = self.stage
            if current is not None:
                self.progress["current"] = max(0, int(current))
            if total is not None:
                self.progress["total"] = max(0, int(total))
            if percent is None:
                cur = int(self.progress.get("current") or 0)
                tot = int(self.progress.get("total") or 0)
                if tot > 0:
                    percent = (cur / tot) * 100
            if percent is not None:
                self.progress["percent"] = clamp_percent(percent)
            if message is not None:
                self.progress["message"] = str(message)
            self.updated_at = datetime.now()
            self._append_event_unlocked(
                JobEvent(
                    type="progress",
                    stage=self.stage,
                    message=str(message or self.progress.get("message") or self.stage_label),
                    level="info",
                    current=_optional_int(self.progress.get("current")),
                    total=_optional_int(self.progress.get("total")),
                    percent=clamp_percent(self.progress.get("percent")),
                )
            )

    def add_event(
        self,
        type: str,
        stage: str,
        message: str,
        level: str = "info",
        current: int | None = None,
        total: int | None = None,
        percent: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        clean_stage = stage if stage in STAGE_LABELS else self.stage
        with self._lock:
            self._append_event_unlocked(
                JobEvent(
                    type=str(type or "log"),
                    stage=clean_stage,
                    message=str(message),
                    level=str(level or "info"),
                    current=current,
                    total=total,
                    percent=clamp_percent(percent) if percent is not None else None,
                    payload=_sanitize_event_payload(payload or {}),
                )
            )
            self.updated_at = datetime.now()

    def add_log(self, message: str, level: str = "info", stage: str | None = None) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        clean_stage = stage if stage in STAGE_LABELS else self.stage
        clean_level = level or infer_log_level(str(message))
        with self._lock:
            self.logs.append({"time": timestamp, "message": str(message)})
            if len(self.logs) > 1000:
                self.logs = self.logs[-1000:]
            self._append_event_unlocked(
                JobEvent(
                    type="log" if clean_level not in {"warning", "error"} else clean_level,
                    stage=clean_stage,
                    message=str(message),
                    level=clean_level,
                )
            )
            self.updated_at = datetime.now()
        console_log(str(message), timestamp=timestamp)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            subtasks = self._build_subtasks_unlocked()
            return {
                "id": self.id,
                "status": self.status,
                "stage": self.stage,
                "stage_label": self.stage_label,
                "progress": dict(self.progress),
                "subtasks": subtasks,
                "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "logs": list(self.logs[-SNAPSHOT_LIMIT:]),
                "events": [event.to_dict() for event in self.events[-SNAPSHOT_LIMIT:]],
                "candidates": list(self.candidates),
                "required_pick_count": self.required_pick_count,
                "result": visible_job_result(self.result),
                "error": self.error,
                "cancel_requested": self.cancel_requested.is_set(),
            }

    def submit_selection(self, indexes: list[Any]) -> None:
        with self._lock:
            if self.status != "awaiting_selection":
                raise ValueError("当前任务不在人工筛选阶段。")
            if self.cancel_requested.is_set():
                raise ValueError("任务正在取消，不能提交人工筛选。")

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
            self.stage = "images"
            self.last_work_stage = "images"
            self.stage_label = stage_label("images")
            self.progress.update(
                {
                    "current": 0,
                    "total": len(cleaned[:target]),
                    "percent": 0.0,
                    "message": f"已收到人工选择 {len(cleaned[:target])} 条，准备下载图片",
                }
            )
            self._append_event_unlocked(
                JobEvent(
                    type="selection",
                    stage="selection",
                    message=f"已收到人工选择 {len(cleaned[:target])} 条",
                    level="success",
                    current=len(cleaned[:target]),
                    total=target,
                    percent=100.0,
                    payload={"selected_count": len(cleaned[:target])},
                )
            )
            self.updated_at = datetime.now()
        self._selection_event.set()

    def cancel_selection(self) -> None:
        self.request_cancel("已取消人工筛选。")

    def _set_failed(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.stage = "failed"
            self.stage_label = stage_label("failed")
            self.error = message
            self.progress["message"] = message
            self.updated_at = datetime.now()
            self._append_event_unlocked(
                JobEvent(type="error", stage="failed", message=message, level="error")
            )

    def _set_completed(self, result: dict[str, Any]) -> None:
        with self._lock:
            self.status = "completed"
            self.stage = "completed"
            self.stage_label = stage_label("completed")
            self.result = result
            self.progress.update(
                {
                    "current": 1,
                    "total": 1,
                    "percent": 100.0,
                    "message": "任务完成，导出文件已生成",
                }
            )
            self.updated_at = datetime.now()
            self._append_event_unlocked(
                JobEvent(
                    type="result",
                    stage="completed",
                    message="任务完成",
                    level="success",
                    current=1,
                    total=1,
                    percent=100.0,
                    payload={"run_dir": str(result.get("run_dir") or "")},
                )
            )

    def _set_cancelled(self, message: str = "任务已取消。") -> None:
        with self._lock:
            self.status = "cancelled"
            self.stage = "cancelled"
            self.stage_label = stage_label("cancelled")
            self.progress["message"] = message
            self.updated_at = datetime.now()
            self._append_event_unlocked(
                JobEvent(type="warning", stage="cancelled", message=message, level="warning")
            )

    def request_cancel(self, message: str = "正在取消，请等待当前请求结束。") -> bool:
        with self._lock:
            if self.status in {"completed", "failed", "cancelled"}:
                self._append_event_unlocked(
                    JobEvent(
                        type="warning",
                        stage=self.stage,
                        message="任务已结束，无需取消。",
                        level="warning",
                    )
                )
                return False
            self.cancel_requested.set()
            self.progress["message"] = message
            if self.status == "awaiting_selection":
                self.status = "cancelled"
                self.stage = "cancelled"
                self.stage_label = stage_label("cancelled")
            self._append_event_unlocked(
                JobEvent(type="warning", stage=self.stage, message=message, level="warning")
            )
            self.updated_at = datetime.now()
        self._selection_event.set()
        return True

    def check_cancelled(self) -> None:
        if self.cancel_requested.is_set():
            raise JobCancelled("任务已取消。")

    def _crawler_log(self, message: str) -> None:
        self.check_cancelled()
        info = self._parse_progress_message(str(message))
        if info:
            next_stage = str(info.get("stage") or self.stage)
            if next_stage != self.stage:
                self.set_stage(next_stage, message=str(info.get("stage_message") or stage_label(next_stage)))
            self.update_progress(
                current=info.get("current"),
                total=info.get("total"),
                percent=info.get("percent"),
                message=str(info.get("message") or message),
                stage=next_stage,
            )
        self.add_log(str(message), level=infer_log_level(str(message)), stage=str(info.get("stage") if info else self.stage))
        self.check_cancelled()

    def _parse_progress_message(self, message: str) -> dict[str, Any] | None:
        if match := re.search(r"抓取第\s+(\d+)\s+页", message):
            page = int(match.group(1))
            return {
                "stage": "crawl",
                "current": page,
                "total": self.cfg.max_pages,
                "percent": min(96.0, (page / max(1, self.cfg.max_pages)) * 100),
                "message": f"正在抓取第 {page} 页",
            }
        if match := re.search(r"第\s+(\d+)\s+页读取", message):
            page = int(match.group(1))
            return {
                "stage": "crawl",
                "current": page,
                "total": self.cfg.max_pages,
                "percent": min(98.0, (page / max(1, self.cfg.max_pages)) * 100),
                "message": message,
            }
        if "已连续5页无时间窗口命中帖子" in message or "本页没有帖子数据" in message:
            return {
                "stage": "crawl",
                "current": self.progress.get("current"),
                "total": self.cfg.max_pages,
                "percent": 100.0,
                "message": message,
            }
        if "补全帖子正文" in message or message.startswith("正文校正"):
            if match := re.search(r"(\d+)\/(\d+)", message):
                current, total = int(match.group(1)), int(match.group(2))
                return {
                    "stage": "hydrate",
                    "current": current,
                    "total": max(1, total),
                    "message": message,
                }
            return {"stage": "hydrate", "percent": 0.0, "message": message}
        if (
            "开始计算评分" in message
            or "评分进度" in message
            or "快速评分" in message
            or "候选评论补全" in message
            or "自动校准时间权重" in message
        ):
            if match := re.search(r"(\d+)\/(\d+)", message):
                current, total = int(match.group(1)), int(match.group(2))
                return {
                    "stage": "score",
                    "current": current,
                    "total": max(1, total),
                    "message": message,
                }
            return {"stage": "score", "message": message}
        if match := re.search(r"下载图片(?:进度|失败)\s+(\d+)\/(\d+)", message):
            current, total = int(match.group(1)), int(match.group(2))
            return {
                "stage": "images",
                "current": current,
                "total": max(1, total),
                "message": message,
            }
        return None

    def _append_event_unlocked(self, event: JobEvent) -> None:
        self.events.append(event)
        if len(self.events) > EVENT_LIMIT:
            self.events = self.events[-EVENT_LIMIT:]

    def _build_subtasks_unlocked(self) -> list[dict[str, Any]]:
        current_stage = self.stage
        if current_stage in {"failed", "cancelled"}:
            active_index = STAGE_ORDER.index(self.last_work_stage) if self.last_work_stage in STAGE_ORDER else 0
        elif current_stage in STAGE_ORDER:
            active_index = STAGE_ORDER.index(current_stage)
        else:
            active_index = -1
        rows: list[dict[str, Any]] = []
        for index, stage in enumerate(STAGE_ORDER):
            if self.status == "completed":
                state = "done"
                percent = 100.0
            elif self.status == "failed" and index == min(active_index, len(STAGE_ORDER) - 1):
                state = "failed"
                percent = clamp_percent(self.progress.get("percent"))
            elif self.status == "cancelled" and index == min(active_index, len(STAGE_ORDER) - 1):
                state = "cancelled"
                percent = clamp_percent(self.progress.get("percent"))
            elif index < active_index:
                state = "done"
                percent = 100.0
            elif index == active_index:
                state = "active"
                percent = clamp_percent(self.progress.get("percent"))
            else:
                state = "pending"
                percent = 0.0
            rows.append(
                {
                    "id": stage,
                    "label": stage_label(stage),
                    "status": state,
                    "percent": percent,
                }
            )
        self.subtasks = rows
        return list(rows)

    def _run(self) -> None:
        try:
            self.set_stage("init", message="任务初始化")
            self.add_log("开始任务...", stage="init")
            self.add_log("计算方式：Python", stage="init")
            if self.cfg.window_start and self.cfg.window_end:
                self.add_log(
                    "自定义日期区间："
                    f"{self.cfg.window_start.strftime('%Y-%m-%d %H:%M')} -> "
                    f"{self.cfg.window_end.strftime('%Y-%m-%d %H:%M')}",
                    stage="init",
                )

            self.check_cancelled()
            self.set_stage("crawl", message="开始翻页抓取超话帖子")
            self.update_progress(current=0, total=self.cfg.max_pages, percent=0, message="准备抓取第一页", stage="crawl")
            crawler = WeiboSuperTopicCrawler(cookie=self.cfg.cookie, progress_callback=self._crawler_log)
            posts_all = crawler.crawl(self.cfg)
            self.check_cancelled()
            self.update_progress(
                current=len(posts_all),
                total=max(1, len(posts_all)),
                percent=100,
                message=f"抓取、正文补全与评分完成，共获取 {len(posts_all)} 条原始帖子",
                stage="score",
            )
            active_period = analyze_active_period(posts_all)
            if int(active_period.get("valid_posts", 0) or 0) > 0:
                h = int(active_period.get("top_hour", 0) or 0)
                c = int(active_period.get("top_hour_count", 0) or 0)
                s = int(active_period.get("top_two_hour_start", 0) or 0)
                c2 = int(active_period.get("top_two_hour_count", 0) or 0)
                rec = int(active_period.get("recommended_anchor_hour", s) or s)
                self.add_log(f"活跃单小时高峰：{h:02d}:00-{h:02d}:59（{c}帖）", stage="score")
                self.add_log(f"活跃两小时高峰：{s:02d}:00-{(s + 2) % 24:02d}:00（{c2}帖）", stage="score")
                self.add_log(f"建议固定周统计时间：每周 {rec:02d}:00", level="warning", stage="score")

            candidates = select_weekly_posts(posts_all, limit=20)
            if not candidates:
                raise CrawlError("当前窗口内没有可用于周报的候选帖子。")

            target = min(15, len(candidates))
            with self._lock:
                self._candidate_posts = list(candidates)
                self.candidates = [serialize_candidate(post, i) for i, post in enumerate(candidates)]
                self.required_pick_count = target
                self.status = "awaiting_selection"
                self.stage = "selection"
                self.last_work_stage = "selection"
                self.stage_label = stage_label("selection")
                self.progress.update(
                    {
                        "current": target,
                        "total": len(candidates),
                        "percent": 100.0,
                        "message": f"已生成候选 {len(candidates)} 条，等待人工筛选",
                    }
                )
                self._append_event_unlocked(
                    JobEvent(
                        type="selection",
                        stage="selection",
                        message=f"已生成候选 {len(candidates)} 条，等待人工筛选",
                        level="success",
                        current=target,
                        total=len(candidates),
                        percent=100.0,
                        payload={"candidate_count": len(candidates), "required_pick_count": target},
                    )
                )
                self.updated_at = datetime.now()
            self.add_log(f"等待人工筛选：候选 {len(candidates)} 条，默认勾选前 {target} 条。", stage="selection")

            while not self._selection_event.wait(0.5):
                self.check_cancelled()
            self.check_cancelled()
            with self._lock:
                if self.status == "cancelled":
                    raise JobCancelled("任务已取消。")
                selected_indexes = list(self.selected_indexes or [])

            selected_posts = [candidates[i] for i in selected_indexes if 0 <= i < len(candidates)]
            if not selected_posts:
                raise CrawlError("没有可导出的入选帖子。")
            self.add_log(f"人工筛选完成：最终导出 {len(selected_posts)} 条。", level="success", stage="selection")
            self.check_cancelled()

            self.output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.output_dir / ts
            run_dir.mkdir(parents=True, exist_ok=True)
            image_dir = run_dir / "images"

            expected_image_count = count_expected_images(selected_posts)
            image_total = max(1, len(selected_posts))
            self.set_stage("images", message="开始下载帖子图片和热评图片")
            self.update_progress(current=0, total=image_total, percent=0, message="正在下载帖子/评论图片...", stage="images")
            self.add_log("正在下载帖子/评论图片...", stage="images")
            download_post_images(
                posts=selected_posts,
                image_dir=image_dir,
                cookie=self.cfg.cookie,
                progress_callback=self._crawler_log,
                cancel_checker=self.check_cancelled,
            )
            self.check_cancelled()
            downloaded_image_count = count_downloaded_images(selected_posts)
            failed_image_count = max(0, expected_image_count - downloaded_image_count)
            self.update_progress(
                current=image_total,
                total=image_total,
                percent=100,
                message="图片下载阶段完成",
                stage="images",
            )

            self.check_cancelled()
            self.set_stage("export", message="开始生成导出文件")
            export_total = 6
            export_current = 0
            self.update_progress(current=0, total=export_total, percent=0, message="正在准备导出文件", stage="export")
            summary = build_summary(selected_posts)
            all_posts_summary = build_summary(posts_all)
            leaderboards = build_comment_leaderboards(posts_all, top_n=3)

            xlsx_path = run_dir / "weibo_posts.xlsx"
            csv_path = run_dir / "weibo_posts.csv"
            txt_path = run_dir / "weibo_summary.txt"
            report_docx_path = run_dir / "warma_weekly_report.docx"
            report_sum_docx_path = run_dir / "weekly_report_sum.docx"
            report_md_path = run_dir / "warma_weekly_report.md"

            self.check_cancelled()
            export_posts_xlsx(selected_posts, xlsx_path)
            export_current += 1
            self._mark_export_result("XLSX", xlsx_path, export_current, export_total)
            self.check_cancelled()
            export_posts_csv(selected_posts, csv_path)
            export_current += 1
            self._mark_export_result("CSV", csv_path, export_current, export_total)
            self.check_cancelled()
            write_summary_txt(
                summary,
                txt_path,
                leaderboards=leaderboards,
                active_period=active_period,
                all_posts_summary=all_posts_summary,
                carryover_hours=self.cfg.carryover_hours,
            )
            export_current += 1
            self._mark_export_result("summary txt", txt_path, export_current, export_total)
            self.check_cancelled()
            report_docx_paths = export_weekly_report_docx(
                selected_posts,
                report_docx_path,
                leaderboards=leaderboards,
                preselected=True,
            )
            export_current += 1
            self._mark_export_result("DOCX", report_docx_path, export_current, export_total)
            self.check_cancelled()
            report_sum_docx = export_weekly_report_sum_docx(
                selected_posts,
                report_sum_docx_path,
                leaderboards=leaderboards,
                preselected=True,
            )
            export_current += 1
            self._mark_export_result("总 DOCX", report_sum_docx, export_current, export_total)
            self.check_cancelled()
            export_weekly_report_md(selected_posts, report_md_path, leaderboards=leaderboards, preselected=True)
            export_current += 1
            self._mark_export_result("Markdown", report_md_path, export_current, export_total)

            self.add_log(f"抓取完成，共 {summary['total_posts']} 条帖子。", level="success", stage="export")
            self.add_log(f"Excel 已保存：{xlsx_path}", level="success", stage="export")
            self.add_log(f"CSV 已保存：{csv_path}", level="success", stage="export")
            for path in report_docx_paths:
                size_mb = path.stat().st_size / 1000 / 1000 if path.exists() else 0
                self.add_log(f"DOCX 已保存：{path}（{size_mb:.2f} MB）", level="success", stage="export")
            size_mb = report_sum_docx.stat().st_size / 1000 / 1000 if report_sum_docx.exists() else 0
            self.add_log(f"总 DOCX 已保存：{report_sum_docx}（{size_mb:.2f} MB）", level="success", stage="export")
            self.add_log(f"MD 已保存：{report_md_path}", level="success", stage="export")
            self.add_log(f"汇总已保存：{txt_path}", level="success", stage="export")
            if failed_image_count:
                self.add_log(f"图片下载警告：约 {failed_image_count} 张图片未成功保存。", level="warning", stage="export")
            self.add_log(f"本次导出目录：{run_dir}", level="success", stage="export")

            warnings = []
            if failed_image_count:
                warnings.append(f"约 {failed_image_count} 张图片未成功保存，可在导出目录中检查 images 文件夹。")
            result = {
                "total_posts": summary["total_posts"],
                "run_dir": str(run_dir),
                "image_dir": str(image_dir),
                "xlsx": str(xlsx_path),
                "csv": str(csv_path),
                "docx": [str(path) for path in report_docx_paths],
                "docx_sum": str(report_sum_docx),
                "md": str(report_md_path),
                "summary": str(txt_path),
                "failed_image_count": failed_image_count,
                "warnings": warnings,
            }
            result["manifest"] = build_result_manifest(result)
            self._set_completed(result)
        except JobCancelled as err:
            self.add_log(str(err), level="warning", stage="cancelled")
            self._set_cancelled(str(err))
        except CrawlError as err:
            self.add_log(f"任务失败：{err}", level="error", stage="failed")
            self._set_failed(str(err))
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            friendly = f"任务执行失败：{message}"
            self.add_log(f"任务失败：{message}", level="error", stage="failed")
            self._set_failed(friendly)

    def _mark_export_result(self, label: str, path: Path, current: int, total: int) -> None:
        message = f"已生成 {label}: {path}"
        self.update_progress(current=current, total=total, message=message, stage="export")
        self.add_event(
            "result",
            "export",
            message,
            level="success",
            current=current,
            total=total,
            payload={"label": label, "path": str(path)},
        )


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


def cancel_current_job() -> tuple[bool, str, CrawlJob | None]:
    job = get_current_job()
    if not job:
        return False, "当前没有可取消的任务。", None
    if job.status in {"completed", "failed", "cancelled"}:
        return True, "任务已结束，无需取消。", job
    job.request_cancel("正在取消，请等待当前请求结束。")
    return True, "已请求取消任务。", job


def build_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(check_id: str, label: str, status: str, message: str) -> None:
        checks.append({"id": check_id, "label": label, "status": status, "message": message})

    super_topic = str(payload.get("super_topic") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()

    if not super_topic:
        add("topic_required", "超话输入", "error", "未填写超话链接或 ID。建议填写完整超话链接或 100808 开头的超话 ID。")
        add("topic_parse", "超话解析", "error", "超话为空，无法解析。请先填写超话链接或 ID。")
    else:
        add("topic_required", "超话输入", "ok", "已填写超话链接或 ID。")
        topic_id = parse_super_topic_id(super_topic)
        if topic_id:
            add("topic_parse", "超话解析", "ok", f"已解析超话 ID：{topic_id}")
        else:
            add("topic_parse", "超话解析", "error", "无法解析超话 ID。建议复制微博超话页面完整链接后重试。")

    if cookie:
        cookie_message = f"已填写 Cookie，长度 {len(cookie)} 字符。"
        if "SUB=" not in cookie:
            add("cookie", "微博 Cookie", "warning", cookie_message + "未检测到 SUB 字段，可能不是完整登录态。")
        else:
            add("cookie", "微博 Cookie", "ok", cookie_message)
    else:
        add("cookie", "微博 Cookie", "error", "未填写 Cookie。建议先自动获取 Cookie，失败时再手动复制。")

    start_dt: datetime | None = None
    end_dt: datetime | None = None
    try:
        start_dt = parse_datetime_local(payload.get("window_start"))
        add("start_time", "开始时间", "ok", "开始时间格式有效。")
    except ValueError:
        add("start_time", "开始时间", "error", "开始时间无效。建议使用页面日期时间选择器重新选择。")
    try:
        end_dt = parse_datetime_local(payload.get("window_end"))
        add("end_time", "结束时间", "ok", "结束时间格式有效。")
    except ValueError:
        add("end_time", "结束时间", "error", "结束时间无效。建议使用页面日期时间选择器重新选择。")
    if start_dt and end_dt:
        if end_dt > start_dt:
            add("time_order", "时间范围", "ok", "结束时间晚于开始时间。")
        else:
            add("time_order", "时间范围", "error", "结束时间必须晚于开始时间。建议检查周报统计区间。")

    try:
        max_pages = int(str(payload.get("max_pages", "80")).strip())
        if max_pages > 0:
            status = "warning" if max_pages > 300 else "ok"
            message = "最大页数有效。" if status == "ok" else "最大页数较大，抓取耗时可能明显增加。"
            add("max_pages", "最大页数", status, message)
        else:
            add("max_pages", "最大页数", "error", "最大页数必须是正整数。建议填写 80 或更大的正整数。")
    except ValueError:
        add("max_pages", "最大页数", "error", "最大页数不是有效整数。建议填写 80。")

    try:
        pause_seconds = float(str(payload.get("pause_seconds", "1.0")).strip())
        if pause_seconds >= 0:
            status = "warning" if pause_seconds == 0 else "ok"
            message = "请求间隔有效。" if status == "ok" else "请求间隔为 0，可能更容易触发微博限制。"
            add("pause_seconds", "请求间隔", status, message)
        else:
            add("pause_seconds", "请求间隔", "error", "请求间隔必须为非负数。建议填写 1.0。")
    except ValueError:
        add("pause_seconds", "请求间隔", "error", "请求间隔不是有效数字。建议填写 1.0。")

    try:
        factor = float(str(payload.get("topic_comment_factor", "1.0")).strip())
        if factor >= 0.5:
            add("topic_comment_factor", "话题评论系数", "ok", "话题评论系数有效。")
        else:
            add("topic_comment_factor", "话题评论系数", "error", "话题评论系数必须 >= 0.5。建议填写 1.0。")
    except ValueError:
        add("topic_comment_factor", "话题评论系数", "error", "话题评论系数不是有效数字。建议填写 1.0。")

    try:
        output_dir = normalize_output_dir(payload.get("output_dir"))
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / f".weibo_stats_write_test_{uuid.uuid4().hex}.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        add("output_dir", "导出目录", "ok", f"导出目录可写：{output_dir}")
    except Exception:
        add("output_dir", "导出目录", "error", "导出目录不可写或无法创建。建议换到桌面或项目 output 目录。")

    job = get_current_job()
    if job and job.status in ACTIVE_STATUSES:
        add("active_job", "任务状态", "error", "当前已有任务正在运行。请等待完成或取消后再开始。")
    else:
        add("active_job", "任务状态", "ok", "当前没有运行中的任务。")

    can_start = not any(item["status"] == "error" for item in checks)
    return {"can_start": can_start, "checks": checks}


def check_cookie_state(payload: dict[str, Any]) -> dict[str, str]:
    cookie = str(payload.get("cookie") or "").strip()
    super_topic = str(payload.get("super_topic") or "").strip()
    if not cookie:
        return {
            "login_state": "invalid",
            "message": "Cookie 为空",
            "suggestion": "请先自动获取 Cookie，或从已登录微博网页手动复制 Cookie。",
        }

    topic_id = parse_super_topic_id(super_topic) if super_topic else None
    url = f"https://weibo.com/p/{topic_id}/super_index" if topic_id else "https://weibo.com/"
    headers = {
        "User-Agent": WEIBO_USER_AGENT,
        "Cookie": cookie,
        "Referer": "https://weibo.com/",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
    except requests.RequestException:
        return {
            "login_state": "network_error",
            "message": "网络错误",
            "suggestion": "请确认网络可访问微博网页后重试。",
        }

    text = response.text[:200000]
    current_url = response.url or ""
    if looks_like_weibo_visitor(text, current_url):
        return {
            "login_state": "visitor",
            "message": "微博返回访客验证",
            "suggestion": "请在 weibo.com 重新登录后获取 Cookie，不要使用访客态 Cookie。",
        }
    if response.status_code in {401, 403}:
        return {
            "login_state": "invalid",
            "message": "Cookie 可能无权限",
            "suggestion": "请重新登录微博网页后再获取 Cookie。",
        }
    if response.status_code >= 500:
        return {
            "login_state": "network_error",
            "message": f"微博接口暂时异常，HTTP {response.status_code}",
            "suggestion": "请稍后重试，或先在浏览器打开微博确认服务正常。",
        }
    if "SUB=" in cookie and response.status_code < 400:
        return {
            "login_state": "valid",
            "message": "Cookie 可用",
            "suggestion": "可以继续开始抓取。",
        }
    return {
        "login_state": "unknown",
        "message": "Cookie 可能失效",
        "suggestion": "未检测到关键登录字段 SUB。建议手动复制 weibo.com/ajax 请求里的完整 Cookie。",
    }


def looks_like_weibo_visitor(text: str, url: str = "") -> bool:
    lowered = (text + "\n" + url).lower()
    return any(
        marker.lower() in lowered
        for marker in (
            "Sina Visitor System",
            "passport.weibo.com/visitor",
            "微博返回访客验证",
            "visitor/genvisitor",
            "访问验证",
        )
    )


def clear_config(scope: str) -> dict[str, Any]:
    clean_scope = scope if scope in {"cookie", "all"} else ""
    if not clean_scope:
        raise ValueError("清空范围无效。建议使用 scope=cookie 或 scope=all。")
    if clean_scope == "cookie":
        current = load_saved_config()
        current["cookie"] = ""
        CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return app_defaults()

    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_name("weibo_stats_config.backup.json"))
    window_start, window_end = default_time_window()
    defaults = {
        "super_topic": DEFAULT_SUPER_TOPIC,
        "cookie": "",
        "max_pages": "80",
        "topic_comment_factor": "1.0",
        "pause_seconds": "1.0",
        "window_start": datetime_local_value(window_start),
        "window_end": datetime_local_value(window_end),
        "output_dir": str(Path.cwd() / "output"),
        "theme": "dark",
        "advanced_mode": "false",
    }
    CONFIG_PATH.write_text(json.dumps(defaults, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return app_defaults()


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
        "theme": "dark",
        "advanced_mode": "false",
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
            snapshot = job.snapshot() if job else None
            self._send_json({"ok": True, "data": {"job": snapshot}, "job": snapshot})
            return
        if path == "/api/report-preview":
            self._send_report_preview()
            return
        if path == "/api/report-asset":
            self._send_report_asset()
            return
        if path == "/api/help-doc":
            self._send_help_doc()
            return
        if path == "/Background.png":
            if BACKGROUND_PATH.exists() and BACKGROUND_PATH.is_file():
                self._send_static(BACKGROUND_PATH)
            else:
                self._send_json({"error": "Background image not found"}, HTTPStatus.NOT_FOUND)
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
            if path == "/api/preflight":
                payload = self._read_json()
                data = build_preflight(payload)
                self._send_json({"ok": True, "data": data, **data})
                return
            if path == "/api/check-cookie":
                payload = self._read_json()
                data = check_cookie_state(payload)
                self._send_json({"ok": True, "data": data, **data})
                return
            if path == "/api/clear-config":
                payload = self._read_json()
                config = clear_config(str(payload.get("scope") or "cookie"))
                self._send_json({"ok": True, "data": {"config": config}, "config": config})
                return
            if path == "/api/cancel-job":
                ok, message, job = cancel_current_job()
                snapshot = job.snapshot() if job else None
                if not ok:
                    self._send_json(
                        {
                            "ok": False,
                            "error": {
                                "code": "NO_ACTIVE_JOB",
                                "message": "没有正在运行的任务",
                                "suggestion": "当前没有需要取消的任务。",
                            },
                            "job": snapshot,
                        }
                    )
                    return
                self._send_json({"ok": True, "data": {"message": message, "job": snapshot}, "message": message, "job": snapshot})
                return
            if path == "/api/start":
                payload = self._read_json()
                cfg, output_dir = build_config(payload)
                save_user_config(payload)
                job = create_job(cfg, output_dir)
                snapshot = job.snapshot()
                self._send_json({"ok": True, "data": {"job": snapshot}, "job": snapshot})
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
                snapshot = job.snapshot()
                self._send_json({"ok": True, "data": {"job": snapshot}, "job": snapshot})
                return
            if path == "/api/cancel-selection":
                job = get_current_job()
                if not job:
                    raise ValueError("没有正在运行的任务。")
                job.cancel_selection()
                snapshot = job.snapshot()
                self._send_json({"ok": True, "data": {"job": snapshot}, "job": snapshot})
                return
            if path == "/api/cookie/auto":
                console_log("正在自动读取浏览器 Cookie...")
                cookie = get_weibo_cookie_header()
                console_log("Cookie 自动读取成功。")
                debug_edge_closed = close_edge_debug_browser()
                if debug_edge_closed:
                    console_log("调试 Edge 已自动关闭。")
                self._send_json({"cookie": cookie, "debug_edge_closed": debug_edge_closed})
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
            if path == "/api/open-result-dir":
                result_dir = current_result_dir_path()
                if not result_dir:
                    raise ValueError("当前没有可打开的导出目录。")
                open_local_path(result_dir)
                self._send_json({"path": str(result_dir)})
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except CookieFetchError as err:
            console_log(f"Cookie 自动读取失败：{err}")
            self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as err:
            self._send_json({"error": str(err)}, HTTPStatus.CONFLICT)
        except ValueError as err:
            if path == "/api/clear-config":
                self._send_api_error(
                    "CLEAR_CONFIG_FAILED",
                    "清空配置失败",
                    str(err) or "请检查清空范围后重试。",
                    HTTPStatus.BAD_REQUEST,
                )
            else:
                self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
        except Exception as err:
            if path == "/api/preflight":
                self._send_api_error(
                    "PREFLIGHT_FAILED",
                    "预检查失败",
                    "请检查输入参数后重试。",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            elif path == "/api/check-cookie":
                self._send_api_error(
                    "COOKIE_CHECK_FAILED",
                    "Cookie 检测失败",
                    "请确认已登录微博网页，或重新获取 Cookie。",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            elif path == "/api/clear-config":
                self._send_api_error(
                    "CLEAR_CONFIG_FAILED",
                    "清空配置失败",
                    "请确认配置文件没有被其他程序占用后重试。",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            else:
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

    def _send_help_doc(self) -> None:
        if not HELP_DOC_PATH.exists() or not HELP_DOC_PATH.is_file():
            self._send_json({"error": "教程文档不存在。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            markdown = HELP_DOC_PATH.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            markdown = HELP_DOC_PATH.read_text(encoding="utf-8-sig")
        self._send_json({"markdown": markdown, "path": str(HELP_DOC_PATH)})

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

    def _send_api_error(self, code: str, message: str, suggestion: str, status: HTTPStatus) -> None:
        self._send_json(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "suggestion": suggestion,
                },
            },
            status,
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


def open_local_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))
        return
    raise RuntimeError("当前系统不支持从页面打开本地目录。")


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
