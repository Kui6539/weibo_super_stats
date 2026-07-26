from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.artifact_cleanup import (
    cleanup_cancelled_artifacts,
    cleanup_incomplete_artifacts,
)
from core.cache import CacheStore, sanitize_for_cache
from core.candidates import (
    count_downloaded_images,
    count_expected_images,
    serialize_candidate,
)
from core.crawl_types import CrawlConfig, CrawlError
from core.errors import JobCancelled
from core.events import (
    EVENT_LIMIT,
    SNAPSHOT_LIMIT,
    STAGE_LABELS,
    STAGE_ORDER,
    JobEvent,
    clamp_percent,
    infer_log_level,
    optional_int,
    redact_cookie_values,
    sanitize_event_payload,
    stage_label,
)
from core.history import add_history_item_from_manifest
from core.paths import make_run_dir
from core.recovery import recovery_suggestions_for_status
from crawler import (
    WeiboSuperTopicCrawler,
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
from export.context import ExportContext
from export.image_report import export_image_report
from export.manifest import build_manifest, write_manifest
from export.pipeline import ExportTask, run_export_tasks
from export.summary_exporter import analyze_active_period, build_summary
from export.weibo_body_exporter import export_weibo_body
from modules.comments.ranking import build_comment_leaderboards
from modules.images.candidate_thumbnails import build_candidate_thumbnails
from modules.images.manifest import build_images_manifest
from modules.topic import build_report_title, format_report_title_with_issue

# Artifact cleanup now lives in core.artifact_cleanup and candidate
# serialization in core.candidates; both stay importable from here because
# handlers, tests and older call sites reach for them by this name.
__all__ = [
    "ACTIVE_STATUSES",
    "CrawlJob",
    "JobManager",
    "cancel_current_job",
    "cleanup_cancelled_artifacts",
    "cleanup_incomplete_artifacts",
    "console_log",
    "count_downloaded_images",
    "count_expected_images",
    "create_job",
    "get_current_job",
    "serialize_candidate",
    "serialize_job",
    "shutdown_current_job",
]

ACTIVE_STATUSES = {"running", "awaiting_selection", "exporting"}

# Paging usually stops before max_pages, so the crawl bar is held short of full
# until the crawler says it is done.
CRAWL_PROGRESS_CAP = 96.0


def _stage_advances(current_stage: str, next_stage: str) -> bool:
    """True when moving to *next_stage* is forward progress.

    Progress events arrive from worker threads, so a straggler from an earlier
    phase can land after the job has moved on. Without this the bar would jump
    backwards -- from scoring to crawling and then forward again.
    """
    if next_stage not in STAGE_ORDER:
        return False
    if current_stage not in STAGE_ORDER:
        return True
    return STAGE_ORDER.index(next_stage) > STAGE_ORDER.index(current_stage)
RUN_DIR_RE = re.compile(r"^\d{8}_\d{6}$")
_console_lock = threading.Lock()
_job_lock = threading.RLock()
_current_job: CrawlJob | None = None


def console_log(message: str, timestamp: str | None = None) -> None:
    stamp = timestamp or datetime.now().strftime("%H:%M:%S")
    with _console_lock:
        print(f"[{stamp}] {message}", flush=True)


def visible_job_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    run_dir = str(result.get("run_dir") or "").strip()
    if run_dir and not Path(run_dir).exists():
        return None
    return dict(result)


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
        self.run_dir: Path | None = None
        self.cancel_cleanup: dict[str, Any] | None = None
        self.artifact_cleanup: dict[str, Any] | None = None
        self.selected_indexes: list[int] | None = None
        self.cancel_requested = threading.Event()
        self.super_topic_name = ""
        self.report_title = format_report_title_with_issue(build_report_title("", self.cfg.super_topic), self.cfg.issue)

        self._candidate_posts: list[dict] = []
        # Highest count seen in the current stage; see _hold_high_water.
        self._progress_high_water = -1
        # True once the cache holds enough to regenerate reports offline; from
        # that point a failure cleans up the half-written output only.
        self._cache_recoverable = False
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
                    current=optional_int(self.progress.get("current")),
                    total=optional_int(self.progress.get("total")),
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
                    current=optional_int(self.progress.get("current")),
                    total=optional_int(self.progress.get("total")),
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
                    payload=sanitize_event_payload(payload or {}),
                )
            )
            self.updated_at = datetime.now()

    def add_log(self, message: str, level: str = "info", stage: str | None = None) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        clean_stage = stage if stage in STAGE_LABELS else self.stage
        clean_level = level or infer_log_level(str(message))
        # Last line of defence: logs reach /api/status and the front end can
        # save them to a file, so a credential that slipped into a message --
        # typically inside an exception carrying a request header -- must not
        # survive this far.
        message = redact_cookie_values(str(message))
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
                "cancel_cleanup": sanitize_for_cache(self.cancel_cleanup),
                "artifact_cleanup": sanitize_for_cache(self.artifact_cleanup),
                "cancel_requested": self.cancel_requested.is_set(),
                "recovery_suggestions": recovery_suggestions_for_status(
                    {"status": self.status, "error": self.error, "progress": self.progress}
                ),
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
            self._append_event_unlocked(
                JobEvent(type="warning", stage=self.stage, message=message, level="warning")
            )
            self.updated_at = datetime.now()
        self._selection_event.set()
        return True

    def check_cancelled(self) -> None:
        if self.cancel_requested.is_set():
            raise JobCancelled("任务已取消。")

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

    def _crawler_log(self, message: str) -> None:
        """Record a crawler log line, inferring progress from it if possible.

        The inference is legacy: crawler.py now reports progress through
        _crawler_progress, so anything still arriving here is either a purely
        informational line or a caller that predates the structured channel.
        """
        self.check_cancelled()
        info = self._parse_progress_message(str(message))
        if info:
            self._apply_progress(
                stage=str(info.get("stage") or self.stage),
                message=str(info.get("message") or message),
                current=info.get("current"),
                total=info.get("total"),
                percent=info.get("percent"),
            )
        self.add_log(str(message), level=infer_log_level(str(message)), stage=str(info.get("stage") if info else self.stage))
        self.check_cancelled()

    def _crawler_progress(self, event: dict[str, Any]) -> None:
        """Consume a structured progress event: move the bar and log the line.

        The event carries the message, so this is the only place it is
        recorded -- routing it through the log channel as well would duplicate
        every progress line in the user's log panel.

        Cancellation is checked here because during a long parallel phase these
        events may be the only thing calling back into the job, and a cancel
        that goes unnoticed until the phase ends feels like a hang.
        """
        self.check_cancelled()
        if not isinstance(event, dict):
            return
        stage = str(event.get("stage") or self.stage)
        message = str(event.get("message") or "")
        current = optional_int(event.get("current"))
        total = optional_int(event.get("total"))
        self._apply_progress(
            stage=stage,
            message=message,
            current=current,
            total=total,
            percent=self._stage_percent(stage, current, total, done=bool(event.get("done"))),
        )
        if message:
            self.add_log(message, level=infer_log_level(message), stage=self.stage)
        self.check_cancelled()

    def _apply_progress(
        self,
        *,
        stage: str,
        message: str,
        current: Any = None,
        total: Any = None,
        percent: Any = None,
    ) -> None:
        if stage != self.stage and _stage_advances(self.stage, stage):
            self.set_stage(stage, message=stage_label(stage))
            self._progress_high_water = -1
        current, percent = self._hold_high_water(current, percent)
        self.update_progress(
            current=current,
            total=total,
            percent=percent,
            message=message,
            stage=stage if stage == self.stage else self.stage,
        )

    def _hold_high_water(self, current: Any, percent: Any) -> tuple[Any, Any]:
        """Never let a count go backwards inside a stage.

        Image downloads and the scoring phases report from a thread pool, so a
        slower worker's event can arrive after a faster one's. Without this the
        bar visibly jumps back and forth. The high-water mark resets whenever
        the stage advances.
        """
        value = optional_int(current)
        if value is None:
            return current, percent
        if value < self._progress_high_water:
            return None, None
        self._progress_high_water = value
        return current, percent

    def _stage_percent(self, stage: str, current: int | None, total: int | None, done: bool) -> float | None:
        """Turn counts into a bar percentage.

        Crawling stops early far more often than it exhausts max_pages -- the
        window fills up, or the topic runs out of posts -- so the page ratio is
        capped short of full and only an explicit stop marks it complete.
        Otherwise the bar would sit at, say, 15% and jump straight to the next
        stage.
        """
        if done:
            return 100.0
        if current is None or not total:
            return None
        ratio = (current / max(1, total)) * 100
        if stage == "crawl":
            return min(CRAWL_PROGRESS_CAP, ratio)
        return min(100.0, ratio)

    def _parse_progress_message(self, message: str) -> dict[str, Any] | None:
        """Recover progress from a log line. Superseded by _crawler_progress.

        Kept as a fallback for log lines that have no structured counterpart.
        It is why rewording a message in crawler.py used to freeze the bar --
        and why two stop-paging lines never registered at all.
        """
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
        run_dir: Path | None = None
        cache_store: CacheStore | None = None
        try:
            self.set_stage("init", message="任务初始化")
            self.add_log("开始任务...", stage="init")
            self.add_log("计算方式：Python", stage="init")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            run_dir = make_run_dir(self.output_dir)
            self.run_dir = run_dir
            image_dir = run_dir / "images"
            cache_store = CacheStore(run_dir)
            cache_store.init()
            self._write_cache_stage(cache_store, "run_config", self._run_config_payload(run_dir), critical=True)
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
            crawler = WeiboSuperTopicCrawler(
                cookie=self.cfg.cookie,
                progress_callback=self._crawler_log,
                progress_event_callback=self._crawler_progress,
                stage_callback=lambda stage, posts: self._write_cache_stage(cache_store, stage, posts),
                comment_cache_reader=cache_store.read_comment_cache,
                comment_cache_writer=cache_store.write_comment_cache,
            )
            posts_all = crawler.crawl(self.cfg)
            self.super_topic_name = crawler.topic_name
            self.report_title = format_report_title_with_issue(
                crawler.report_title or build_report_title(self.super_topic_name, self.cfg.super_topic),
                self.cfg.issue,
            )
            self._write_cache_stage(cache_store, "run_config", self._run_config_payload(run_dir), critical=True)
            self.check_cancelled()
            self._write_cache_stage(cache_store, "posts_scored", posts_all)
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
            self.check_cancelled()
            self.set_stage("thumbnails", message="开始下载预选帖缩略图")
            self.update_progress(current=0, total=1, percent=0, message="正在准备预选帖缩略图缓存", stage="thumbnails")
            thumbnail_summary = build_candidate_thumbnails(
                candidates,
                cache_store,
                cookie=self.cfg.cookie,
                cancel_checker=self.check_cancelled,
                progress_callback=self._candidate_thumbnail_log,
            )
            if thumbnail_summary.get("success"):
                total_thumbnails = max(1, int(thumbnail_summary.get("total") or 1))
                self.update_progress(
                    current=total_thumbnails,
                    total=total_thumbnails,
                    percent=100,
                    message="预选帖缩略图缓存完成",
                    stage="thumbnails",
                )
                self.add_log(
                    "预选帖缩略图缓存目录："
                    f"{thumbnail_summary.get('dir')}；"
                    f"新下载 {thumbnail_summary.get('downloaded', 0)} 张，"
                    f"缓存命中 {thumbnail_summary.get('cache_hits', 0)} 张。",
                    level="success",
                    stage="thumbnails",
                )
            elif thumbnail_summary.get("total"):
                self.add_log("预选帖缩略图下载失败，将只显示文字节选。", level="warning", stage="thumbnails")
            else:
                self.update_progress(current=1, total=1, percent=100, message="预选帖没有图片，跳过缩略图下载", stage="thumbnails")
            self._write_cache_stage(cache_store, "candidates", candidates)

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

            # request_cancel sets this event too, so a plain wait covers both
            # "user submitted a selection" and "user cancelled".
            self._selection_event.wait()
            self.check_cancelled()
            with self._lock:
                if self.status == "cancelled":
                    raise JobCancelled("任务已取消。")
                selected_indexes = list(self.selected_indexes or [])

            selected_posts = [candidates[i] for i in selected_indexes if 0 <= i < len(candidates)]
            if not selected_posts:
                raise CrawlError("没有可导出的入选帖子。")
            self._write_cache_stage(cache_store, "selected_posts", selected_posts, critical=True)
            # From here the cache holds everything reexport needs, so a later
            # failure must not throw away the crawl. See _cleanup_incomplete_artifacts.
            self._cache_recoverable = True
            self.add_log(f"人工筛选完成：最终导出 {len(selected_posts)} 条。", level="success", stage="selection")
            self.check_cancelled()

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
                progress_event_callback=self._crawler_progress,
                cancel_checker=self.check_cancelled,
            )
            self.check_cancelled()
            downloaded_image_count = count_downloaded_images(selected_posts)
            failed_image_count = max(0, expected_image_count - downloaded_image_count)
            images_manifest = build_images_manifest(run_dir, selected_posts)
            self._write_cache_stage(cache_store, "images_manifest", images_manifest)
            self._write_cache_stage(cache_store, "selected_posts", selected_posts, critical=True)
            self.update_progress(
                current=image_total,
                total=image_total,
                percent=100,
                message="图片下载阶段完成",
                stage="images",
            )

            self.check_cancelled()
            self.set_stage("export", message="开始生成导出文件")
            export_total = 9
            export_current = 0
            self.update_progress(current=0, total=export_total, percent=0, message="正在准备导出文件", stage="export")
            summary = build_summary(selected_posts)
            all_posts_summary = build_summary(posts_all)
            leaderboards = build_comment_leaderboards(posts_all, top_n=3)
            community_stats = {
                "schema_version": 1,
                "summary": summary,
                "all_posts_summary": all_posts_summary,
                "leaderboards": leaderboards,
                "active_period": active_period,
            }
            self._write_cache_stage(cache_store, "community_stats", community_stats)

            xlsx_path = run_dir / "weibo_posts.xlsx"
            csv_path = run_dir / "weibo_posts.csv"
            txt_path = run_dir / "weibo_summary.txt"
            report_docx_path = run_dir / "weekly_report.docx"
            report_sum_docx_path = run_dir / "weekly_report_sum.docx"
            report_md_path = run_dir / "weekly_report.md"
            weibo_body_path = run_dir / "weibo_body.txt"

            warnings: list[str] = []
            if failed_image_count:
                warnings.append(f"约 {failed_image_count} 张图片未成功保存，可在导出目录中检查 images 文件夹。")
            # Built before the first exporter so image-embedding warnings from
            # Excel and DOCX reach the manifest instead of being dropped into a
            # throwaway context.
            export_ctx = ExportContext(
                run_dir=run_dir,
                selected_posts=selected_posts,
                all_posts=posts_all,
                config=self._run_config_payload(run_dir) | {"candidate_count": len(candidates), "leaderboards": leaderboards},
                stats=summary,
                images_manifest=images_manifest,
                warnings=warnings,
            )
            tasks = [
                ExportTask("XLSX", lambda: export_posts_xlsx(selected_posts, xlsx_path), xlsx_path),
                ExportTask("CSV", lambda: export_posts_csv(selected_posts, csv_path), csv_path),
                ExportTask(
                    "summary txt",
                    lambda: write_summary_txt(
                        summary,
                        txt_path,
                        leaderboards=leaderboards,
                        active_period=active_period,
                        all_posts_summary=all_posts_summary,
                        carryover_hours=self.cfg.carryover_hours,
                    ),
                    txt_path,
                ),
                ExportTask(
                    "DOCX",
                    lambda: export_weekly_report_docx(
                        selected_posts,
                        report_docx_path,
                        title=self.report_title,
                        leaderboards=leaderboards,
                        preselected=True,
                    ),
                    report_docx_path,
                ),
                ExportTask(
                    "总 DOCX",
                    lambda: export_weekly_report_sum_docx(
                        selected_posts,
                        report_sum_docx_path,
                        title=self.report_title,
                        leaderboards=leaderboards,
                        preselected=True,
                    ),
                    report_sum_docx_path,
                ),
                ExportTask(
                    "Markdown",
                    lambda: export_weekly_report_md(
                        selected_posts,
                        report_md_path,
                        title=self.report_title,
                        leaderboards=leaderboards,
                        preselected=True,
                    ),
                    report_md_path,
                ),
                ExportTask("微博正文", lambda: export_weibo_body(export_ctx, weibo_body_path), weibo_body_path),
                ExportTask("长图报告", lambda: export_image_report(export_ctx)),
            ]

            def on_export_done(task: ExportTask, value: Any) -> None:
                nonlocal export_current
                export_current += 1
                self._mark_export_result(
                    task.label, task.target if value is None else value, export_current, export_total
                )

            def on_export_failed(task: ExportTask, err: Exception) -> None:
                nonlocal export_current
                export_current += 1
                self.add_log(f"{task.label} 导出失败：{type(err).__name__}: {err}", level="warning", stage="export")

            outcome = run_export_tasks(
                tasks,
                action="导出",
                check_cancelled=self.check_cancelled,
                on_success=on_export_done,
                on_failure=on_export_failed,
            )
            warnings.extend(outcome.warnings)
            failed_exports = outcome.failed_labels
            report_docx_paths = outcome.result("DOCX", [])
            report_sum_docx = outcome.results.get("总 DOCX")
            image_report = outcome.results.get("长图报告")

            files = {
                "markdown": report_md_path if report_md_path.exists() else None,
                "docx": report_docx_paths,
                "docx_sum": report_sum_docx,
                "xlsx": xlsx_path if xlsx_path.exists() else None,
                "csv": csv_path if csv_path.exists() else None,
                "summary": txt_path if txt_path.exists() else None,
                "weibo_body": outcome.results.get("微博正文"),
                "images": image_dir,
                "image_report_preview": None,
                "image_report_pages": [],
                "image_report_metadata": None,
            }
            if image_report is not None:
                files["image_report_preview"] = image_report.preview
                files["image_report_pages"] = image_report.pages
                files["image_report_metadata"] = image_report.metadata
                warnings.extend(image_report.warnings)

            self.add_log(f"抓取完成，共 {summary['total_posts']} 条帖子。", level="success", stage="export")
            if xlsx_path.exists():
                self.add_log(f"Excel 已保存：{xlsx_path}", level="success", stage="export")
            if csv_path.exists():
                self.add_log(f"CSV 已保存：{csv_path}", level="success", stage="export")
            for path in report_docx_paths:
                size_mb = path.stat().st_size / 1000 / 1000 if path.exists() else 0
                self.add_log(f"DOCX 已保存：{path}（{size_mb:.2f} MB）", level="success", stage="export")
            if report_sum_docx and Path(report_sum_docx).exists():
                size_mb = Path(report_sum_docx).stat().st_size / 1000 / 1000
                self.add_log(f"总 DOCX 已保存：{report_sum_docx}（{size_mb:.2f} MB）", level="success", stage="export")
            if report_md_path.exists():
                self.add_log(f"MD 已保存：{report_md_path}", level="success", stage="export")
            if txt_path.exists():
                self.add_log(f"汇总已保存：{txt_path}", level="success", stage="export")
            if files["weibo_body"]:
                self.add_log(f"微博正文已保存：{files['weibo_body']}", level="success", stage="export")
            if image_report is not None:
                self.add_log(f"长图预览已保存：{image_report.preview}", level="success", stage="export")
                for path in image_report.pages:
                    self.add_log(f"长图 JPG 已保存：{path}", level="success", stage="export")
                for warning in image_report.warnings:
                    self.add_log(warning, level="warning", stage="export")
            if failed_image_count:
                self.add_log(f"图片下载警告：约 {failed_image_count} 张图片未成功保存。", level="warning", stage="export")
            if failed_exports:
                self.add_log(
                    f"以下格式未能生成：{'、'.join(failed_exports)}。关闭占用这些文件的程序后，可在历史任务中『重新生成报告』补齐。",
                    level="warning",
                    stage="export",
                )
            self.add_log(f"本次导出目录：{run_dir}", level="success", stage="export")

            manifest = build_manifest(
                export_ctx,
                files,
                warnings=warnings,
                failed_images=failed_image_count,
                status="export_failed" if failed_exports else "completed",
            )
            manifest_path = write_manifest(run_dir, manifest)
            try:
                add_history_item_from_manifest(run_dir, manifest)
            except Exception as err:
                self.add_log(f"历史记录写入失败：{type(err).__name__}: {err}", level="warning", stage="export")
            self._mark_export_result("manifest.json", manifest_path, export_total, export_total)
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
                "weibo_body": str(files["weibo_body"]),
                "image_report_preview": str(image_report.preview),
                "image_report_pages": [str(path) for path in image_report.pages],
                "image_report_metadata": str(image_report.metadata),
                "manifest_path": str(manifest_path),
                "failed_image_count": failed_image_count,
                "warnings": warnings,
                "manifest": manifest,
            }
            self._set_completed(result)
        except JobCancelled as err:
            self.add_log(str(err), level="warning", stage="cancelled")
            # An explicit cancel really does mean "throw it all away".
            self._cleanup_incomplete_artifacts(run_dir, cache_store, reason="cancelled", keep_cache=False)
            self._set_cancelled(str(err))
        except CrawlError as err:
            self.add_log(f"任务失败：{err}", level="error", stage="failed")
            self._cleanup_incomplete_artifacts(run_dir, cache_store, reason="failed")
            self._set_failed(self._failure_message(str(err)))
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            console_log(f"任务 {self.id} 失败：{message}")
            self.add_log(f"任务失败：{message}", level="error", stage="failed")
            self._cleanup_incomplete_artifacts(run_dir, cache_store, reason="failed")
            self._set_failed(self._failure_message(f"任务执行失败：{message}"))

    def _failure_message(self, message: str) -> str:
        if not self._cache_recoverable:
            return message
        return f"{message} 抓取数据已保留在缓存中，可在历史任务里直接『重新生成报告』，无需重新抓取。"

    def _run_config_payload(self, run_dir: Path) -> dict[str, Any]:
        return sanitize_for_cache(
            {
                "schema_version": 1,
                "run_id": run_dir.name,
                "created_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "super_topic": self.cfg.super_topic,
                "super_topic_name": self.super_topic_name,
                "report_title": self.report_title,
                "issue": self.cfg.issue,
                "super_topic_id": parse_super_topic_id(self.cfg.super_topic) or "",
                "max_pages": self.cfg.max_pages,
                "pause_seconds": self.cfg.pause_seconds,
                "days_window": self.cfg.days_window,
                "topic_comment_factor": self.cfg.topic_comment_factor,
                "comment_page_limit": self.cfg.comment_page_limit,
                "text_workers": self.cfg.text_workers,
                "comment_workers": self.cfg.comment_workers,
                "window_start": self.cfg.window_start.strftime("%Y-%m-%d %H:%M:%S") if self.cfg.window_start else "",
                "window_end": self.cfg.window_end.strftime("%Y-%m-%d %H:%M:%S") if self.cfg.window_end else "",
                "carryover_hours": self.cfg.carryover_hours,
            }
        )

    def _write_cache_stage(
        self,
        cache_store: CacheStore,
        stage: str,
        data: Any,
        critical: bool = False,
    ) -> None:
        try:
            path = cache_store.write_stage(stage, data)
        except Exception as err:
            message = f"缓存写入失败：{stage}，{type(err).__name__}: {err}"
            self.add_log(message, level="error" if critical else "warning", stage=self.stage)
            self.add_event("warning", self.stage, message, level="warning", payload={"cache_stage": stage})
            if critical:
                raise CrawlError(message) from err
            return
        self.add_event(
            "result",
            self.stage,
            f"已写入缓存：cache/{path.name}",
            level="success",
            payload={"cache_stage": stage, "path": str(path)},
        )

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

    def _candidate_thumbnail_log(self, event: dict[str, Any]) -> None:
        message = str(event.get("message") or "").strip()
        if not message:
            return
        level = str(event.get("level") or "info")
        current = optional_int(event.get("current"))
        total = optional_int(event.get("total"))
        if current is not None and total:
            self.update_progress(
                current=current,
                total=total,
                percent=(current / max(1, total)) * 100,
                message=message,
                stage="thumbnails",
            )
        elif str(event.get("type") or "") in {"start", "skip"}:
            self.update_progress(message=message, stage="thumbnails")
        self.add_log(message, level=level, stage="thumbnails")

    def _cleanup_incomplete_artifacts(
        self,
        run_dir: Path | None,
        cache_store: CacheStore | None,
        *,
        reason: str,
        keep_cache: bool | None = None,
    ) -> None:
        preserve = self._cache_recoverable if keep_cache is None else keep_cache
        cleanup = cleanup_incomplete_artifacts(
            run_dir=run_dir or self.run_dir,
            output_dir=self.output_dir,
            cache_store=cache_store,
            keep_cache=preserve,
        )
        self.artifact_cleanup = cleanup
        if reason == "cancelled":
            self.cancel_cleanup = cleanup
        deleted = list(cleanup.get("deleted_dirs") or [])
        skipped = list(cleanup.get("skipped") or [])
        errors = list(cleanup.get("errors") or [])
        stage = "cancelled" if reason == "cancelled" else "failed"
        action = "取消清理" if reason == "cancelled" else "失败清理"
        if deleted:
            self.add_log(f"已自动清理未完成任务目录与缓存：{', '.join(deleted)}", level="success", stage=stage)
        if preserve:
            self.add_log("已保留本次抓取缓存，可在历史任务中重新生成报告。", level="warning", stage=stage)
        if skipped:
            self.add_log(f"{action}跳过：{'; '.join(skipped)}", level="warning", stage=stage)
        if errors:
            self.add_log(f"{action}失败：{'; '.join(errors)}", level="warning", stage=stage)


class JobManager:
    def get_current_job(self) -> CrawlJob | None:
        return get_current_job()

    def create_job(self, cfg: CrawlConfig, output_dir: Path) -> CrawlJob:
        return create_job(cfg, output_dir)

    def cancel_current_job(self) -> tuple[bool, str, CrawlJob | None]:
        return cancel_current_job()


def get_current_job() -> CrawlJob | None:
    with _job_lock:
        return _current_job


def create_job(cfg: CrawlConfig, output_dir: Path) -> CrawlJob:
    global _current_job
    with _job_lock:
        if _current_job and _current_job.status in ACTIVE_STATUSES:
            raise RuntimeError(_busy_message(_current_job))
        _current_job = CrawlJob(cfg, output_dir)
        _current_job.start()
        return _current_job


def _busy_message(job: CrawlJob) -> str:
    """Say what the blocking task is actually doing.

    awaiting_selection counts as active and has no timeout, so closing the tab
    parks a task there forever. A bare "a task is already running" leaves the
    user thinking the tool has hung rather than that it is waiting on them.
    """
    label = STAGE_LABELS.get(job.stage, job.stage or "进行中")
    started = job.started_at.strftime("%H:%M") if getattr(job, "started_at", None) else ""
    when = f"（开始于 {started}）" if started else ""
    if job.status == "awaiting_selection":
        return f"已有任务停留在『{label}』{when}，请先完成候选筛选，或取消该任务后再开始新的任务。"
    return f"已有任务正在『{label}』{when}，请等待完成或取消后再开始新的任务。"


def shutdown_current_job(timeout: float = 10.0) -> bool:
    """Ask a running job to stop and wait for its cleanup to finish.

    The worker is a daemon thread, so process exit would otherwise kill it
    mid-step: no except/finally runs, the cancel-cleanup path never fires, and
    a partially written cache JSON can be left behind.
    """
    job = get_current_job()
    if not job or job.status not in ACTIVE_STATUSES:
        return True
    console_log("正在等待当前任务安全停止...")
    job.request_cancel("服务正在关闭，任务已取消。")
    thread = getattr(job, "thread", None)
    if thread is None or not thread.is_alive():
        return True
    thread.join(timeout=timeout)
    if thread.is_alive():
        console_log("任务未能在超时前停止，仍会退出；下次启动可用『扫描 output』清理残留目录。")
        return False
    console_log("当前任务已安全停止。")
    return True


def cancel_current_job() -> tuple[bool, str, CrawlJob | None]:
    job = get_current_job()
    if not job:
        return False, "当前没有可取消的任务。", None
    if job.status in {"completed", "failed", "cancelled"}:
        return True, "任务已结束，无需取消。", job
    job.request_cancel("正在取消，请等待当前请求结束。")
    return True, "已请求取消任务。", job


def serialize_job(job: CrawlJob | None) -> dict[str, Any] | None:
    return job.snapshot() if job else None
