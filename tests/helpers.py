from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from core.cache import CacheStore
from export.context import ExportContext
from export.summary_exporter import build_summary
from modules.comments.ranking import build_comment_leaderboards

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "session",
    "password",
    "passwd",
    "secret",
}


def load_fixture(name: str) -> Any:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def make_temp_run_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def write_cache_fixture(run_dir: Path) -> CacheStore:
    store = CacheStore(run_dir)
    posts_raw = load_fixture("sample_posts_raw.json")
    posts_hydrated = load_fixture("sample_posts_hydrated.json")
    posts_scored = load_fixture("sample_posts_scored.json")
    selected_posts = load_fixture("sample_selected_posts.json")
    community_stats = load_fixture("sample_community_stats.json")
    images_manifest = load_fixture("sample_images_manifest.json")

    store.write_stage(
        "run_config",
        {
            "super_topic": "100808abc",
            "super_topic_id": "100808abc",
            "super_topic_name": "测试超话",
            "report_title": "测试超话周报",
            "window_start": "2026-05-01 04:00",
            "window_end": "2026-05-08 04:00",
            "cookie": "SHOULD_NOT_BE_WRITTEN",
        },
    )
    store.write_stage("posts_raw", posts_raw)
    store.write_stage("posts_hydrated", posts_hydrated)
    store.write_stage("posts_scored", posts_scored)
    store.write_stage("candidates", posts_scored)
    store.write_stage("selected_posts", selected_posts)
    store.write_stage("community_stats", community_stats)
    store.write_stage("images_manifest", images_manifest)
    for post in posts_scored:
        store.write_comment_cache(str(post.get("post_id") or ""), {"comments": post.get("all_comments_data") or []})
    return store


def assert_no_sensitive_fields(testcase: unittest.TestCase, data: Any) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            testcase.assertNotIn(str(key).lower(), SENSITIVE_KEYS)
            assert_no_sensitive_fields(testcase, value)
    elif isinstance(data, list):
        for item in data:
            assert_no_sensitive_fields(testcase, item)


def assert_file_exists(testcase: unittest.TestCase, path: Path) -> None:
    testcase.assertTrue(path.exists(), f"missing file: {path}")
    testcase.assertTrue(path.is_file(), f"not a file: {path}")


def assert_json_ok(testcase: unittest.TestCase, payload: dict[str, Any]) -> None:
    testcase.assertIsInstance(payload, dict)
    testcase.assertIn("ok", payload)
    if payload.get("ok"):
        testcase.assertIn("data", payload)
    else:
        testcase.assertIn("error", payload)
        testcase.assertIn("code", payload["error"])
        testcase.assertIn("message", payload["error"])
        testcase.assertIn("suggestion", payload["error"])


def build_export_context_from_fixtures(tmpdir: str | Path) -> ExportContext:
    run_dir = Path(tmpdir)
    selected_posts = load_fixture("sample_selected_posts.json")
    all_posts = load_fixture("sample_posts_scored.json")
    images_manifest = load_fixture("sample_images_manifest.json")
    stats = build_summary(selected_posts)
    leaderboards = build_comment_leaderboards(all_posts, top_n=3)
    return ExportContext(
        run_dir=run_dir,
        selected_posts=selected_posts,
        all_posts=all_posts,
        config={
            "super_topic": "100808abc",
            "super_topic_name": "测试超话",
            "report_title": "测试超话周报",
            "leaderboards": leaderboards,
        },
        stats=stats,
        images_manifest=images_manifest,
    )
