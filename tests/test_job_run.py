"""Characterization tests for the ``CrawlJob`` state machine in ``core/job.py``.

``core/job.py`` orchestrates a whole run -- init, crawl, scoring, the manual
selection gate, image download, export, manifest and history -- and is the file
the maintainability batch is about to split apart. Nothing in ``tests/``
exercised ``CrawlJob._run()`` end to end, so these tests pin the *observable*
behaviour a refactor must not change:

* the ``/api/status`` snapshot field contract the web UI depends on;
* the selection gate (exact pick count, then ``exporting`` -> ``completed``);
* what a completed run leaves behind (manifest, history entry, stage caches);
* the single-active-job rule in ``JobManager``;
* cancel -> ``cancelled`` plus the artifact cleanup rules;
* "one locked output file must not kill the other exporters", where the run
  still completes but the manifest is marked ``export_failed`` and the cache is
  preserved for an offline reexport.

Everything is faked at the network boundary -- crawler, post image download,
candidate thumbnails and the Playwright long-image export -- so the tests are
offline, fast and repeatable. ``make_temp_run_dir()`` redirects the cache root
and the history file is patched to a temp path, so no test writes the real
``output/``, ``cache/`` or ``weibo_stats_history.json``.
"""

from __future__ import annotations

import copy
import json
import time
import unittest
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any
from unittest import mock

import core.history
import core.job
from core.artifact_cleanup import is_run_dir_deletable
from core.cache import CacheStore
from core.crawl_types import CrawlConfig
from core.job import CrawlJob, JobManager
from export.image_report.models import ImageReportResult
from modules.crawler_filters import should_exclude_post
from tests.helpers import load_fixture, make_temp_run_dir

# Every key /api/status promises the front end (CLAUDE.md "job snapshot").
SNAPSHOT_CONTRACT_KEYS = {
    "id",
    "status",
    "stage",
    "stage_label",
    "progress",
    "subtasks",
    "started_at",
    "created_at",
    "updated_at",
    "logs",
    "events",
    "candidates",
    "required_pick_count",
    "result",
    "error",
    "cancel_requested",
    "recovery_suggestions",
}

# Keys serialize_candidate() promises web/js/candidates.js.
CANDIDATE_CONTRACT_KEYS = {
    "index",
    "rank",
    "user_name",
    "publish_time",
    "content",
    "content_excerpt",
    "content_full",
    "score",
    "score_detail",
    "likes",
    "comments",
    "reposts",
    "post_url",
    "image_count",
    "image_preview_paths",
}

# Stage caches a full run must leave behind for an offline reexport.
EXPECTED_CACHE_FILES = (
    "run_config.json",
    "posts_raw.json",
    "posts_hydrated.json",
    "posts_scored.json",
    "candidates.json",
    "selected_posts.json",
    "community_stats.json",
    "images_manifest.json",
)

WAIT_TIMEOUT = 8.0


def sample_posts(count: int = 4) -> list[dict[str, Any]]:
    """Build ``count`` distinct posts that survive the weekly-report filter."""
    base = [post for post in load_fixture("sample_posts_scored.json") if not should_exclude_post(post)[0]]
    rows: list[dict[str, Any]] = []
    for index in range(count):
        post = copy.deepcopy(base[index % len(base)])
        post["post_id"] = f"9{index:03d}"
        post["post_url"] = f"https://weibo.com/9{index:03d}"
        post["score"] = float(post.get("score") or 0) + index
        rows.append(post)
    return rows


def make_config(**overrides: Any) -> CrawlConfig:
    values: dict[str, Any] = {
        "super_topic": "https://weibo.com/p/100808abc/super_index",
        "cookie": "SUB=fake-cookie-value",
        "max_pages": 2,
        "pause_seconds": 0,
        "issue": "6",
        "window_start": datetime(2026, 5, 1, 4, 0),
        "window_end": datetime(2026, 5, 8, 4, 0),
    }
    values.update(overrides)
    return CrawlConfig(**values)


class FakeCrawler:
    """Offline stand-in for ``WeiboSuperTopicCrawler``.

    Reproduces only what ``CrawlJob._run()`` touches: the keyword-only
    constructor, the ``topic_name``/``report_title`` attributes read after
    ``crawl()``, the stage-cache callbacks and the progress log callback (which
    is also the job's cancellation checkpoint).
    """

    def __init__(
        self,
        cookie: str = "",
        progress_callback: Callable[[str], None] | None = None,
        stage_callback: Callable[[str, Any], None] | None = None,
        comment_cache_reader: Callable[[str], Any] | None = None,
        comment_cache_writer: Callable[[str, Any], Any] | None = None,
        progress_event_callback: Callable[[dict[str, Any]], None] | None = None,
        posts: list[dict[str, Any]] | None = None,
        crawl_error: BaseException | None = None,
    ) -> None:
        self.cookie = cookie
        self.progress_callback = progress_callback
        self.progress_event_callback = progress_event_callback
        self.stage_callback = stage_callback
        self.comment_cache_reader = comment_cache_reader
        self.comment_cache_writer = comment_cache_writer
        self.posts = posts if posts is not None else []
        self.crawl_error = crawl_error
        self.topic_name = "测试超话"
        self.report_title = "测试超话周报"
        self.crawl_calls: list[CrawlConfig] = []

    def _log(self, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(message)

    def _progress(self, stage: str, message: str, current: int | None = None, total: int | None = None,
                  *, done: bool = False) -> None:
        """Mirrors WeiboSuperTopicCrawler._progress, including its fallback."""
        if not self.progress_event_callback:
            self._log(message)
            return
        event: dict[str, Any] = {"stage": stage, "message": message, "done": done}
        if current is not None:
            event["current"] = current
        if total is not None:
            event["total"] = total
        self.progress_event_callback(event)

    def _stage(self, stage: str, data: Any) -> None:
        if self.stage_callback:
            self.stage_callback(stage, data)

    def crawl(self, config: CrawlConfig) -> list[dict[str, Any]]:
        self.crawl_calls.append(config)
        if self.crawl_error is not None:
            raise self.crawl_error
        self._log(f"已识别超话名称：{self.topic_name}")
        posts = copy.deepcopy(self.posts)
        self._log(f"抓取第 1 页，共获取 {len(posts)} 条帖子")
        self._stage("posts_raw", posts)
        self._log(f"补全帖子正文 {len(posts)}/{len(posts)}")
        self._stage("posts_hydrated", posts)
        for post in posts:
            post_id = str(post.get("post_id") or "")
            if post_id and self.comment_cache_writer:
                self.comment_cache_writer(post_id, {"comments": post.get("all_comments_data") or []})
        self._log(f"评分进度 {len(posts)}/{len(posts)}")
        return posts


def fake_download_post_images(
    posts: Any = None,
    image_dir: Path | None = None,
    cookie: str = "",
    progress_callback: Callable[[str], None] | None = None,
    cancel_checker: Callable[[], None] | None = None,
    progress_event_callback: Callable[[dict[str, Any]], None] | None = None,
    **_kwargs: Any,
) -> None:
    """No-op stand-in that still honours the cancellation checkpoint."""
    if cancel_checker:
        cancel_checker()
    if image_dir is not None:
        Path(image_dir).mkdir(parents=True, exist_ok=True)
    total = max(1, len(list(posts or [])))
    message = f"下载图片进度 {total}/{total}"
    if progress_event_callback:
        progress_event_callback({"stage": "images", "message": message, "current": total, "total": total})
    elif progress_callback:
        progress_callback(message)


def fake_build_candidate_thumbnails(posts: Any, cache_store: Any, **_kwargs: Any) -> dict[str, Any]:
    """Report "no thumbnails to fetch", the branch that needs no network."""
    for post in posts:
        post["candidate_thumbnail_urls"] = []
        post["candidate_thumbnail_count"] = 0
    return {"success": False, "total": 0, "downloaded": 0, "cache_hits": 0, "dir": str(cache_store.cache_dir)}


def fake_export_image_report(ctx: Any) -> ImageReportResult:
    """Write the long-image artifacts without starting Playwright."""
    report_dir = Path(ctx.run_dir) / "image_report"
    report_dir.mkdir(parents=True, exist_ok=True)
    preview = report_dir / "preview.html"
    preview.write_text("<html><body>fake preview</body></html>", encoding="utf-8")
    page = report_dir / "page_01.jpg"
    page.write_bytes(b"fake-jpeg-bytes")
    metadata = report_dir / "metadata.json"
    metadata.write_text("{}\n", encoding="utf-8")
    return ImageReportResult(preview=preview, pages=[page], metadata=metadata, warnings=[], page_count=1)


class JobEnv:
    """Isolated filesystem + patched boundaries for one test."""

    def __init__(self, root: Path, history_path: Path) -> None:
        self.root = root
        self.output_dir = root / "output"
        self.history_path = history_path
        self.jobs: list[CrawlJob] = []

    def start_job(self, config: CrawlConfig | None = None) -> CrawlJob:
        job = CrawlJob(config or make_config(), self.output_dir)
        self.jobs.append(job)
        job.start()
        return job

    def stop_all(self) -> None:
        for job in self.jobs:
            if job.thread.is_alive():
                job.request_cancel("测试结束，任务已取消。")
                job.thread.join(timeout=WAIT_TIMEOUT)

    def history_items(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        return list(json.loads(self.history_path.read_text(encoding="utf-8")).get("items") or [])

    def cache_store(self, run_dir: Path) -> CacheStore:
        return CacheStore(run_dir)


@contextmanager
def job_env(
    posts: list[dict[str, Any]] | None = None,
    crawl_error: BaseException | None = None,
    extra_patches: tuple[Any, ...] = (),
) -> Iterator[JobEnv]:
    with make_temp_run_dir() as root, ExitStack() as stack:
        env = JobEnv(root, root / "weibo_stats_history.json")
        crawler_factory = partial(
            FakeCrawler,
            posts=sample_posts() if posts is None else posts,
            crawl_error=crawl_error,
        )
        stack.enter_context(mock.patch.object(core.history, "HISTORY_PATH", env.history_path))
        stack.enter_context(mock.patch.object(core.job, "console_log", lambda *a, **k: None))
        stack.enter_context(mock.patch.object(core.job, "WeiboSuperTopicCrawler", crawler_factory))
        stack.enter_context(mock.patch.object(core.job, "download_post_images", fake_download_post_images))
        stack.enter_context(mock.patch.object(core.job, "build_candidate_thumbnails", fake_build_candidate_thumbnails))
        stack.enter_context(mock.patch.object(core.job, "export_image_report", fake_export_image_report))
        for patcher in extra_patches:
            stack.enter_context(patcher)
        # Registered last so it unwinds first: threads must be joined before the
        # patches are undone and before the temp tree is deleted.
        stack.callback(env.stop_all)
        yield env


def wait_until(predicate: Callable[[], bool], timeout: float = WAIT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class JobRunTests(unittest.TestCase):
    def await_status(self, job: CrawlJob, status: str) -> None:
        reached = wait_until(lambda: job.status == status)
        self.assertTrue(reached, f"job stayed in {job.status!r} instead of reaching {status!r}: {job.error}")

    def run_to_completion(self, env: JobEnv) -> CrawlJob:
        job = env.start_job()
        self.await_status(job, "awaiting_selection")
        job.submit_selection(list(range(job.required_pick_count)))
        self.await_status(job, "completed")
        return job

    def test_run_reaches_awaiting_selection_with_full_snapshot_contract(self) -> None:
        with job_env() as env:
            job = env.start_job()
            self.await_status(job, "awaiting_selection")
            snapshot = job.snapshot()

            self.assertTrue(SNAPSHOT_CONTRACT_KEYS.issubset(snapshot.keys()), SNAPSHOT_CONTRACT_KEYS - snapshot.keys())
            self.assertEqual(snapshot["stage"], "selection")
            self.assertEqual(snapshot["stage_label"], "等待人工筛选")
            self.assertEqual(snapshot["required_pick_count"], 4)
            self.assertEqual(len(snapshot["candidates"]), 4)
            self.assertFalse(snapshot["cancel_requested"])
            self.assertIsNone(snapshot["error"])
            self.assertIsNone(snapshot["result"])
            self.assertEqual(snapshot["id"], job.id)
            self.assertEqual({"current", "total", "percent", "message"}, set(snapshot["progress"]))
            self.assertTrue(snapshot["logs"])
            self.assertTrue(snapshot["events"])
            self.assertIsInstance(snapshot["recovery_suggestions"], list)

    def test_awaiting_selection_snapshot_exposes_stage_and_candidate_shape(self) -> None:
        with job_env() as env:
            job = env.start_job()
            self.await_status(job, "awaiting_selection")
            snapshot = job.snapshot()

            stage_ids = [row["id"] for row in snapshot["subtasks"]]
            self.assertEqual(stage_ids, core.job.STAGE_ORDER)
            for row in snapshot["subtasks"]:
                self.assertEqual({"id", "label", "status", "percent"}, set(row))
            states = {row["id"]: row["status"] for row in snapshot["subtasks"]}
            self.assertEqual(states["selection"], "active")
            self.assertEqual(states["crawl"], "done")
            self.assertEqual(states["export"], "pending")

            for index, candidate in enumerate(snapshot["candidates"]):
                self.assertEqual(CANDIDATE_CONTRACT_KEYS, set(candidate))
                self.assertEqual(candidate["index"], index)
                self.assertEqual(candidate["rank"], index + 1)
                self.assertIsInstance(candidate["image_preview_paths"], list)

    def test_submit_selection_requires_the_exact_pick_count(self) -> None:
        with job_env() as env:
            job = env.start_job()
            self.await_status(job, "awaiting_selection")

            with self.assertRaises(ValueError) as too_few:
                job.submit_selection([0, 1])
            self.assertIn("恰好勾选 4 条", str(too_few.exception))

            with self.assertRaises(ValueError):
                job.submit_selection([])

            with self.assertRaises(ValueError):
                job.submit_selection([0, 1, 2, 99])

            self.assertEqual(job.status, "awaiting_selection")
            self.assertIsNone(job.selected_indexes)

    def test_submit_selection_moves_through_exporting_to_completed(self) -> None:
        with job_env() as env:
            job = env.start_job()
            self.await_status(job, "awaiting_selection")
            job.submit_selection([0, 1, 2, 3])

            self.assertEqual(job.selected_indexes, [0, 1, 2, 3])
            self.assertIn(job.status, {"exporting", "completed"})
            self.await_status(job, "completed")

            snapshot = job.snapshot()
            self.assertEqual(snapshot["stage"], "completed")
            self.assertIsNone(snapshot["error"])
            self.assertEqual({row["status"] for row in snapshot["subtasks"]}, {"done"})
            self.assertEqual(snapshot["result"]["total_posts"], 4)
            self.assertEqual(snapshot["result"]["manifest"]["selected_count"], 4)

    def test_submit_selection_is_rejected_outside_the_selection_stage(self) -> None:
        with job_env() as env:
            job = self.run_to_completion(env)
            with self.assertRaises(ValueError):
                job.submit_selection([0, 1, 2, 3])

    def test_completed_run_writes_manifest_history_and_full_cache(self) -> None:
        with job_env() as env:
            job = self.run_to_completion(env)
            run_dir = job.run_dir
            self.assertIsNotNone(run_dir)
            assert run_dir is not None

            manifest_path = run_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["run_id"], run_dir.name)
            self.assertEqual(manifest["selected_count"], 4)
            self.assertEqual(manifest["candidate_count"], 4)
            self.assertEqual(manifest["super_topic_name"], "测试超话")
            self.assertNotIn("cookie", json.dumps(manifest, ensure_ascii=False).lower())

            for name in ("weibo_posts.xlsx", "weibo_posts.csv", "weibo_summary.txt", "weekly_report.md", "weibo_body.txt"):
                self.assertTrue((run_dir / name).exists(), f"missing export: {name}")
            self.assertTrue((run_dir / "image_report" / "preview.html").exists())

            cache_dir = env.cache_store(run_dir).cache_dir
            for name in EXPECTED_CACHE_FILES:
                self.assertTrue((cache_dir / name).exists(), f"missing cache file: {name}")
            self.assertEqual(len(list((cache_dir / "comments").glob("post_*.json"))), 4)
            can_reexport, missing = env.cache_store(run_dir).has_required_for_reexport()
            self.assertTrue(can_reexport, missing)

            items = env.history_items()
            self.assertEqual([item["run_id"] for item in items], [run_dir.name])
            self.assertEqual(items[0]["status"], "completed")
            self.assertTrue(items[0]["can_reexport"])

    def test_completed_run_never_writes_the_cookie_into_the_cache(self) -> None:
        with job_env() as env:
            job = self.run_to_completion(env)
            assert job.run_dir is not None
            run_config = json.loads((env.cache_store(job.run_dir).cache_dir / "run_config.json").read_text(encoding="utf-8"))

            self.assertNotIn("cookie", run_config)
            self.assertEqual(run_config["run_id"], job.run_dir.name)
            self.assertEqual(run_config["issue"], "6")

    def test_cancel_from_selection_cancels_and_removes_the_artifacts(self) -> None:
        with job_env() as env:
            job = env.start_job()
            self.await_status(job, "awaiting_selection")
            run_dir = job.run_dir
            assert run_dir is not None
            cache_dir = env.cache_store(run_dir).cache_dir
            self.assertTrue(run_dir.exists())
            self.assertTrue(cache_dir.exists())

            self.assertTrue(job.request_cancel("测试取消"))
            self.await_status(job, "cancelled")

            snapshot = job.snapshot()
            self.assertEqual(snapshot["stage"], "cancelled")
            self.assertTrue(snapshot["cancel_requested"])
            self.assertIsNone(snapshot["result"])
            self.assertIsInstance(snapshot["cancel_cleanup"], dict)
            self.assertFalse(run_dir.exists(), "cancel must discard the half-written run directory")
            self.assertFalse(cache_dir.exists(), "cancel must discard the run cache")
            self.assertIn(str(run_dir.resolve()), snapshot["cancel_cleanup"]["deleted_dirs"])
            self.assertEqual(env.history_items(), [])

    def test_cancel_is_refused_once_the_job_finished(self) -> None:
        with job_env() as env:
            job = self.run_to_completion(env)
            self.assertFalse(job.request_cancel("测试取消"))
            self.assertEqual(job.status, "completed")

    def test_crawl_error_fails_the_job_and_cleans_up_the_unrecoverable_run(self) -> None:
        with job_env(posts=[]) as env:
            job = env.start_job()
            self.await_status(job, "failed")

            snapshot = job.snapshot()
            self.assertEqual(snapshot["stage"], "failed")
            self.assertIn("候选帖子", snapshot["error"] or "")
            self.assertNotIn("重新生成报告", snapshot["error"] or "")
            self.assertTrue(snapshot["recovery_suggestions"])
            assert job.run_dir is not None
            self.assertFalse(job.run_dir.exists())
            self.assertFalse(env.cache_store(job.run_dir).cache_dir.exists())

    def test_one_failing_exporter_keeps_the_other_formats_cache_and_run_dir(self) -> None:
        """A locked weibo_posts.xlsx must not cost the user the crawl."""

        def locked_xlsx(*_args: Any, **_kwargs: Any) -> None:
            raise PermissionError(13, "文件被占用")

        with job_env(extra_patches=(mock.patch.object(core.job, "export_posts_xlsx", locked_xlsx),)) as env:
            job = self.run_to_completion(env)
            run_dir = job.run_dir
            assert run_dir is not None

            self.assertFalse((run_dir / "weibo_posts.xlsx").exists())
            for name in ("weibo_posts.csv", "weibo_summary.txt", "weekly_report.md", "weibo_body.txt"):
                self.assertTrue((run_dir / name).exists(), f"other formats must still be generated: {name}")

            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "export_failed")
            self.assertTrue(any("XLSX" in warning for warning in manifest["warnings"]))

            self.assertTrue(run_dir.exists())
            can_reexport, missing = env.cache_store(run_dir).has_required_for_reexport()
            self.assertTrue(can_reexport, missing)
            self.assertEqual([item["status"] for item in env.history_items()], ["export_failed"])
            self.assertFalse(is_run_dir_deletable(run_dir, env.output_dir))


class JobManagerTests(unittest.TestCase):
    def test_create_job_rejects_a_second_job_while_one_is_active(self) -> None:
        with job_env() as env:
            blocking = CrawlJob(make_config(), env.output_dir)
            blocking.status = "awaiting_selection"
            blocking.stage = "selection"
            with mock.patch.object(core.job, "_current_job", blocking):
                with self.assertRaises(RuntimeError) as ctx:
                    JobManager().create_job(make_config(), env.output_dir)
                self.assertIn("候选筛选", str(ctx.exception))
                # server/handlers.py calls the module-level function, not the class.
                with self.assertRaises(RuntimeError):
                    core.job.create_job(make_config(), env.output_dir)
                self.assertIs(core.job.get_current_job(), blocking)

    def test_create_job_starts_the_worker_when_no_job_is_active(self) -> None:
        with job_env() as env, mock.patch.object(core.job, "_current_job", None):
            manager = JobManager()
            job = manager.create_job(make_config(), env.output_dir)
            env.jobs.append(job)

            self.assertIs(manager.get_current_job(), job)
            self.assertTrue(wait_until(lambda: job.status == "awaiting_selection"), job.status)
            self.assertTrue(job.request_cancel("测试取消"))
            self.assertTrue(wait_until(lambda: job.status == "cancelled"), job.status)


if __name__ == "__main__":
    unittest.main()
