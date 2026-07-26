"""Pins how a crawl run reports progress, before that mechanism is replaced.

Progress currently travels as Chinese prose: the crawler logs a sentence, and
``CrawlJob._parse_progress_message`` runs six regex groups over it to recover a
stage and an x/y count. Nothing tested it, and nothing could catch a break --
rewording a log line in crawler.py silently freezes the progress bar, and the
front end has its own second copy of the same parsing.

Every input below is a real format string taken from crawler.py, cited by line,
so this file doubles as the inventory of that coupling. The assertions describe
today's behaviour so the structured-event replacement can be checked against
it rather than against someone's memory.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from core.crawl_types import CrawlConfig
from core.job import CrawlJob


def make_job(max_pages: int = 80) -> CrawlJob:
    """A job that is never started -- only its parsing is exercised."""
    cfg = CrawlConfig(
        super_topic="https://weibo.com/p/100808abc/super_index",
        cookie="SUB=x",
        max_pages=max_pages,
        window_start=datetime(2026, 6, 1),
        window_end=datetime(2026, 6, 8),
    )
    return CrawlJob(cfg, Path("output"))


class CrawlStageParsingTests(unittest.TestCase):
    def test_page_fetch_line_drives_the_crawl_bar(self) -> None:
        # crawler.py:283 -- f"抓取第 {page} 页..."
        info = make_job(max_pages=80)._parse_progress_message("抓取第 12 页...")
        self.assertEqual(info["stage"], "crawl")
        self.assertEqual(info["current"], 12)
        self.assertEqual(info["total"], 80)
        self.assertAlmostEqual(info["percent"], 15.0)

    def test_page_percent_is_capped_below_completion(self) -> None:
        """The crawl bar must not read 100% while paging is still going."""
        info = make_job(max_pages=10)._parse_progress_message("抓取第 10 页...")
        self.assertEqual(info["percent"], 96.0)

    def test_page_summary_line_also_drives_the_bar(self) -> None:
        # crawler.py:349 -- f"第 {page} 页读取 {n} 条，窗口内命中 {m} 条，新增 {k} 条。"
        info = make_job(max_pages=80)._parse_progress_message("第 7 页读取 20 条，窗口内命中 5 条，新增 3 条。")
        self.assertEqual(info["stage"], "crawl")
        self.assertEqual(info["current"], 7)

    def test_the_empty_page_stop_line_completes_the_crawl_stage(self) -> None:
        # crawler.py:312 -- this one the parser does recognise.
        info = make_job()._parse_progress_message("本页没有帖子数据，停止翻页。")
        self.assertEqual(info["stage"], "crawl")
        self.assertEqual(info["percent"], 100.0)

    def test_the_other_stop_reasons_are_missed_entirely(self) -> None:
        """A live bug, and the clearest argument for structured events.

        core/job.py:449 tests for "已连续5页无时间窗口命中帖子", but crawler.py:365
        emits "已连续5页没有时间窗口内的新增帖子" -- different wording, so the
        branch has never once fired. "新版超话接口没有更多页" (crawler.py:286,
        369) was never covered at all. In both cases paging stops but the crawl
        bar is left frozen wherever the last page number put it.
        """
        job = make_job()
        for message in (
            "已连续5页没有时间窗口内的新增帖子，停止翻页。",
            "新版超话接口没有更多页，停止翻页。",
            "已翻到最大页数 80，停止抓取。",
        ):
            with self.subTest(message=message):
                self.assertIsNone(job._parse_progress_message(message))


class HydrateStageParsingTests(unittest.TestCase):
    def test_the_headline_has_no_counts_yet(self) -> None:
        # crawler.py:387 -- "补全帖子正文（包含疑似截断内容）..."
        info = make_job()._parse_progress_message("补全帖子正文（包含疑似截断内容）...")
        self.assertEqual(info["stage"], "hydrate")
        self.assertEqual(info["percent"], 0.0)
        self.assertNotIn("current", info)

    def test_per_post_lines_carry_the_counts(self) -> None:
        # crawler.py:984 / 1004 -- f"正文校正 {idx}/{total}: {post_id}"
        info = make_job()._parse_progress_message("正文校正 3/17: 5302410982984385")
        self.assertEqual(info["stage"], "hydrate")
        self.assertEqual((info["current"], info["total"]), (3, 17))

    def test_the_parallel_progress_line_carries_the_counts(self) -> None:
        # crawler.py:1004 -- f"正文校正进度 {completed}/{total}"
        info = make_job()._parse_progress_message("正文校正进度 9/17")
        self.assertEqual((info["current"], info["total"]), (9, 17))


class ScoreStageParsingTests(unittest.TestCase):
    def test_every_scoring_phrase_maps_to_the_score_stage(self) -> None:
        job = make_job()
        for message in (
            "开始计算评分（包含评论结构估算与时间权重）...",  # crawler.py:391
            "自动校准时间权重（目标拟合度 90%~93%）...",  # crawler.py:394
            "快速评分已完成：评论结构精查 12/30 条。",  # crawler.py:477
            "评分进度 5/30",  # crawler.py:506
            "候选评论补全进度 4/20",  # crawler.py:609
        ):
            with self.subTest(message=message):
                self.assertEqual(job._parse_progress_message(message)["stage"], "score")

    def test_counts_are_extracted_when_present(self) -> None:
        info = make_job()._parse_progress_message("评分进度 5/30")
        self.assertEqual((info["current"], info["total"]), (5, 30))

    def test_a_scoring_headline_without_counts_still_switches_stage(self) -> None:
        info = make_job()._parse_progress_message("开始计算评分（包含评论结构估算与时间权重）...")
        self.assertEqual(info["stage"], "score")
        self.assertNotIn("current", info)


class ImageStageParsingTests(unittest.TestCase):
    def test_download_progress_and_failure_both_drive_the_bar(self) -> None:
        job = make_job()
        # crawler.py:1425 and :1490
        for message, expected in (
            ("下载图片进度 4/15: 5302410982984385", (4, 15)),
            ("下载图片失败 6/15: OSError: timed out", (6, 15)),
        ):
            with self.subTest(message=message):
                info = job._parse_progress_message(message)
                self.assertEqual(info["stage"], "images")
                self.assertEqual((info["current"], info["total"]), expected)


class UnmatchedMessageTests(unittest.TestCase):
    def test_informational_lines_do_not_move_the_bar(self) -> None:
        """Anything unparsed returns None and is logged without a progress update."""
        job = make_job()
        for message in (
            "按周报抓取规则，本次最多翻到第 80 页。",  # crawler.py:280
            "评论结构与基础评分并行处理：6 个线程。",  # crawler.py:489
            "已识别超话名称：永雏塔菲",
            "",
        ):
            with self.subTest(message=message):
                self.assertIsNone(job._parse_progress_message(message))

    def test_a_reworded_log_line_silently_stops_reporting_progress(self) -> None:
        """The fragility this refactor exists to remove.

        The parser keys off whitespace: "抓取第 12 页" is recognised, "抓取第12页"
        is not. Dropping one space in crawler.py freezes the bar, and no other
        test would notice.
        """
        job = make_job()
        self.assertIsNotNone(job._parse_progress_message("抓取第 12 页..."))
        self.assertIsNone(job._parse_progress_message("抓取第12页..."))


class SubtaskContractTests(unittest.TestCase):
    def test_subtasks_cover_every_stage_from_the_start(self) -> None:
        """The front end's log-parsing fallback exists for a case that never
        happens: a snapshot always carries one row per stage."""
        from core.events import STAGE_ORDER

        snapshot = make_job().snapshot()
        self.assertEqual([row["id"] for row in snapshot["subtasks"]], list(STAGE_ORDER))
        self.assertTrue(all(row["label"] for row in snapshot["subtasks"]))


if __name__ == "__main__":
    unittest.main()
