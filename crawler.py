from __future__ import annotations

"""Crawler compatibility layer.

已迁移：评分/过滤、评论榜单、Markdown/CSV/summary、DOCX、XLSX 等低风险导出入口。
暂留：超话抓取调度、HTML 解析、长正文补全、评论请求调度、图片下载调度和部分历史辅助函数。
"""

import hashlib
import heapq
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag
from core.crawl_types import CrawlConfig, CrawlError
from export.csv_exporter import DEFAULT_EXPORT_COLUMN_MAP
from export.csv_exporter import build_export_row as _export_build_row
from export.csv_exporter import export_posts_csv as _export_posts_csv
from export.docx_exporter import export_weekly_report_docx as _export_weekly_report_docx
from export.docx_exporter import export_weekly_report_sum_docx as _export_weekly_report_sum_docx
from export.excel_exporter import export_posts_xlsx as _export_posts_xlsx
from export.markdown_exporter import export_weekly_report_md as _export_weekly_report_md
from export.report_helpers import clean_report_text as _report_clean_report_text
from export.report_helpers import format_hot_comment_text as _report_format_hot_comment_text
from export.report_helpers import format_posts_date_range as _report_format_posts_date_range
from export.report_helpers import iter_report_comments as _report_iter_report_comments
from export.report_helpers import replace_unicode_emoji as _report_replace_unicode_emoji
from export.report_helpers import replace_weibo_emoticons as _report_replace_weibo_emoticons
from export.report_helpers import select_weekly_posts as _report_select_weekly_posts
from export.report_helpers import simplify_hot_comment as _report_simplify_hot_comment
from export.report_helpers import strip_url_like_text as _report_strip_url_like_text
from export.report_helpers import to_rel_path as _report_to_rel_path
from export.summary_exporter import analyze_active_period as _export_analyze_active_period
from export.summary_exporter import build_summary as _export_build_summary
from export.summary_exporter import calc_date_distribution_fit as _export_calc_date_distribution_fit
from export.summary_exporter import write_summary_txt as _export_write_summary_txt
from modules.comments.ranking import build_comment_leaderboards as _comments_build_comment_leaderboards
from modules.crawler_filters import should_exclude_post
from modules.crawler_scoring import calculate_score
from modules.images.url_extract import collect_comment_image_urls as _image_collect_comment_image_urls
from modules.images.url_extract import collect_top_comment_image_urls as _image_collect_top_comment_image_urls
from modules.images.url_extract import dedup_image_urls as _image_dedup_image_urls
from modules.images.url_extract import dedup_keep_order as _image_dedup_keep_order
from modules.images.url_extract import extract_sinaimg_host as _image_extract_sinaimg_host
from modules.images.url_extract import extract_status_image_urls as _image_extract_status_image_urls
from modules.images.url_extract import extract_urls_from_data_node as _image_extract_urls_from_data_node
from modules.images.url_extract import guess_image_ext as _image_guess_image_ext
from modules.images.url_extract import image_signature as _image_image_signature
from modules.images.url_extract import looks_like_image_url as _image_looks_like_image_url
from modules.images.url_extract import split_multi_urls as _image_split_multi_urls
from modules.images.url_extract import split_url_candidates as _image_split_url_candidates
from modules.images.url_extract import to_original_pic_url as _image_to_original_pic_url
from modules.text_cleaning import clean_topic_tags, collapse_blank_lines, normalize_weibo_text, strip_html_text
from modules.time_utils import normalize_date as _normalize_date
from modules.time_utils import parse_weibo_time
from modules.topic import build_report_title as _topic_build_report_title
from modules.topic import extract_super_topic_name as _topic_extract_super_topic_name
from modules.topic import normalize_super_topic_name as _topic_normalize_super_topic_name
from modules.weibo_html_parser import extract_feed_html_from_page as _html_extract_feed_html_from_page
from modules.weibo_html_parser import extract_original_image_urls as _html_extract_original_image_urls
from modules.weibo_html_parser import is_inside_forwarded_content as _html_is_inside_forwarded_content
from modules.weibo_html_parser import parse_count as _html_parse_count
from modules.weibo_html_parser import parse_fm_view_objects as _html_parse_fm_view_objects
from modules.weibo_html_parser import parse_posts_from_html as _html_parse_posts_from_html
from modules.weibo_url import parse_super_topic_id as _parse_super_topic_id, to_absolute_url

COMMENTS_API_URL = "https://weibo.com/ajax/statuses/buildComments"
COMMENT_ANALYSIS_MIN_ROWS = 60
COMMENT_ANALYSIS_RATIO = 0.36
FINAL_COMMENT_ANALYSIS_LIMIT = 45
EXPORT_COLUMN_MAP = DEFAULT_EXPORT_COLUMN_MAP
DOCX_SIZE_LIMIT_BYTES = 10 * 1000 * 1000


class WeiboSuperTopicCrawler:
    def __init__(
        self,
        cookie: str,
        user_agent: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        stage_callback: Callable[[str, list[dict]], None] | None = None,
        comment_cache_reader: Callable[[str], dict | None] | None = None,
        comment_cache_writer: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.cookie = cookie.strip()
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.progress_callback = progress_callback
        self.stage_callback = stage_callback
        self.comment_cache_reader = comment_cache_reader
        self.comment_cache_writer = comment_cache_writer
        self.topic_name = ""
        self.report_title = "微博超话周报"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Cookie": self.cookie,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/plain, */*",
            }
        )

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.session.headers)
        return session

    def _log(self, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(message)

    def _emit_stage_cache(self, stage: str, posts: list[dict]) -> None:
        if self.stage_callback:
            self.stage_callback(stage, posts)

    def crawl(self, config: CrawlConfig) -> list[dict]:
        topic_id = parse_super_topic_id(config.super_topic)
        if not topic_id:
            raise CrawlError("无法从输入中解析超话ID，请确认链接格式。")
        if not self.cookie:
            raise CrawlError("Cookie 为空。请先从已登录的微博页面复制 Cookie。")

        referer = f"https://weibo.com/p/{topic_id}/super_index"
        use_fixed_window = bool(config.window_start and config.window_end)
        if use_fixed_window:
            window_start = config.window_start or (datetime.now() - timedelta(days=config.days_window))
            window_end = config.window_end or datetime.now()
            if window_end <= window_start:
                raise CrawlError("固定周窗口参数错误：结束时间必须晚于开始时间。")
            self._log(
                f"按固定窗口抓取：{window_start.strftime('%Y-%m-%d %H:%M')} 至 "
                f"{window_end.strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            window_end = datetime.now()
            window_start = window_end - timedelta(days=config.days_window)
            self._log(f"按近 {config.days_window} 天抓取：{window_start.strftime('%Y-%m-%d %H:%M')} 起")

        carryover_hours = max(0, int(config.carryover_hours or 0))
        if carryover_hours > 0:
            self._log(
                f"已启用统计保险窗口：截止前 {carryover_hours} 小时发布的帖子顺延到下一期。"
            )

        all_posts: list[dict] = []
        seen_post_ids: set[str] = set()
        last_page_sig: tuple[str, ...] | None = None
        consecutive_same_pages = 0
        no_hit_streak = 0

        for page in range(1, config.max_pages + 1):
            self._log(f"抓取第 {page} 页...")
            page_html = self._fetch_super_index_page(referer, page)
            if not self.topic_name:
                self.topic_name = extract_super_topic_name(page_html, config.super_topic)
                self.report_title = build_report_title(self.topic_name, config.super_topic)
                if self.topic_name:
                    self._log(f"已识别超话名称：{self.topic_name}")
            feed_html = extract_feed_html_from_page(page_html)
            page_posts = parse_posts_from_html(feed_html)
            if not page_posts:
                self._log("本页没有帖子数据，停止翻页。")
                break

            # 用整页签名做“连续重复页”判断，避免仅比较前几条导致误判提前停页
            sig = tuple(
                str(post.get("post_id", "")).strip()
                for post in page_posts
                if str(post.get("post_id", "")).strip()
            )
            if sig and last_page_sig == sig:
                consecutive_same_pages += 1
                self._log(f"检测到重复页内容（连续{consecutive_same_pages + 1}页相同），继续翻页...")
            else:
                consecutive_same_pages = 0
            last_page_sig = sig if sig else last_page_sig

            page_recent = 0
            for post in page_posts:
                post_id = str(post.get("post_id") or "").strip()
                post_dt = parse_publish_datetime(str(post.get("publish_time") or ""))
                bucket_dt = _apply_carryover_bucket(post_dt, carryover_hours)

                if bucket_dt and window_start <= bucket_dt < window_end:
                    page_recent += 1

                keep = bucket_dt is not None and window_start <= bucket_dt < window_end
                if not keep:
                    continue
                if post_id and post_id in seen_post_ids:
                    continue
                if post_id:
                    seen_post_ids.add(post_id)
                all_posts.append(post)

            if use_fixed_window:
                self._log(f"第 {page} 页读取 {len(page_posts)} 条，窗口内命中 {page_recent} 条。")
            else:
                self._log(f"第 {page} 页读取 {len(page_posts)} 条，近 {config.days_window} 天命中 {page_recent} 条。")

            # 新停页规则：只有连续5页都没有命中时间窗口，才停止翻页
            if page_recent == 0:
                no_hit_streak += 1
                self._log(f"连续无命中页：{no_hit_streak}/5")
            else:
                no_hit_streak = 0

            if no_hit_streak >= 5:
                self._log("已连续5页无时间窗口命中帖子，停止翻页。")
                break

            time.sleep(max(config.pause_seconds, 0))

        if not all_posts:
            if use_fixed_window:
                raise CrawlError(
                    "未抓到该固定窗口内帖子。可能是 Cookie 失效，或该时段无数据。"
                )
            raise CrawlError(
                f"未抓到近 {config.days_window} 天帖子。可能是 Cookie 失效，或超话近 {config.days_window} 天无数据。"
            )

        self._emit_stage_cache("posts_raw", all_posts)
        self._log("补全帖子正文（包含疑似截断内容）...")
        self.hydrate_full_text_posts(all_posts, max_workers=config.text_workers)
        self._emit_stage_cache("posts_hydrated", all_posts)

        self._log("开始计算评分（包含评论结构估算与时间权重）...")
        self.enrich_score_fields(all_posts, config)

        self._log("自动校准时间权重（目标拟合度 90%~93%）...")
        self._recalibrate_time_weight(all_posts, config)
        for _ in range(2):
            if not self._ensure_candidate_comment_analysis(all_posts, config):
                break
            self._recalibrate_time_weight(all_posts, config)

        all_posts.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        self._emit_stage_cache("posts_scored", all_posts)
        return all_posts

    def _fetch_super_index_page(self, super_index_url: str, page: int) -> str:
        resp = self.session.get(
            super_index_url,
            params={"page": str(page)},
            headers={"Referer": "https://weibo.com/"},
            timeout=20,
        )
        text = resp.text.strip()
        if "<title>Sina Visitor System</title>" in text:
            raise CrawlError("微博返回访客验证页面。请使用已登录账号 Cookie 重试。")
        if resp.status_code >= 400:
            raise CrawlError(f"加载超话页面失败，HTTP {resp.status_code}")
        return text

    def enrich_score_fields(self, posts: list[dict], config: CrawlConfig) -> None:
        rows = list(posts)
        total = len(rows)
        if not total:
            return

        for post in rows:
            self._set_estimated_score_fields(post, config)

        comment_rows = [
            post
            for post in rows
            if int(post.get("comments", 0) or 0) > 0
            and str(post.get("post_id") or "").strip()
            and str(post.get("author_id") or "").strip()
        ]
        analysis_rows = self._select_comment_analysis_rows(comment_rows, config)
        analysis_total = len(analysis_rows)
        skipped = len(comment_rows) - analysis_total
        if skipped > 0:
            self._log(f"快速评分已完成：评论结构精查 {analysis_total}/{len(comment_rows)} 条，跳过低潜力 {skipped} 条。")
        elif comment_rows:
            self._log(f"快速评分已完成：评论结构精查 {analysis_total}/{len(comment_rows)} 条。")

        if not analysis_rows:
            return

        worker_count = _bounded_worker_count(config.comment_workers, analysis_total)
        if worker_count == 1:
            for idx, post in enumerate(analysis_rows, start=1):
                self._log(f"评分进度 {idx}/{analysis_total}: {post.get('post_id', '-')}")
                self._enrich_score_fields(post, config)
            return

        self._log(f"评论结构与基础评分并行处理：{worker_count} 个线程。")
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="score-enrich") as executor:
            futures = {
                executor.submit(self._enrich_score_fields_with_private_session, post, config): post
                for post in analysis_rows
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                post = futures[future]
                try:
                    future.result()
                except Exception as err:
                    self._log(
                        f"评分失败 {completed}/{analysis_total}: {post.get('post_id', '-')}, "
                        f"{type(err).__name__}: {err}"
                    )
                    self._set_estimated_score_fields(post, config)
                if completed == analysis_total or completed % 5 == 0:
                    self._log(f"评分进度 {completed}/{analysis_total}")

    def _select_comment_analysis_rows(self, rows: list[dict], config: CrawlConfig) -> list[dict]:
        if not rows:
            return []
        total = len(rows)
        if total <= COMMENT_ANALYSIS_MIN_ROWS:
            return rows
        limit = min(
            total,
            max(
                COMMENT_ANALYSIS_MIN_ROWS,
                int(total * COMMENT_ANALYSIS_RATIO),
                FINAL_COMMENT_ANALYSIS_LIMIT,
            ),
        )
        ref_now = config.window_end or datetime.now()
        return heapq.nlargest(
            limit,
            rows,
            key=lambda post: self._estimated_priority_score(post, config, ref_now),
        )

    def _estimated_priority_score(self, post: dict, config: CrawlConfig, ref_now: datetime) -> float:
        likes = int(post.get("likes", 0) or 0)
        comments = int(post.get("comments", 0) or 0)
        reposts = int(post.get("reposts", 0) or 0)
        comment_factor = max(0.5, float(config.topic_comment_factor))
        base = likes * config.likes_weight + comments * config.comment_weight * comment_factor + reposts * config.repost_weight
        publish_dt = parse_publish_datetime(str(post.get("publish_time") or ""))
        return base * _calc_time_weight(publish_dt, ref_now)

    def _set_estimated_score_fields(self, post: dict, config: CrawlConfig) -> None:
        total_comments = int(post.get("comments", 0) or 0)
        comment_factor = max(0.5, float(config.topic_comment_factor))
        publish_dt = parse_publish_datetime(str(post.get("publish_time") or ""))
        detail = calculate_score({**post, "author_replies": 0, "publish_dt": publish_dt}, config)

        post["non_author_comments"] = total_comments
        post["author_replies"] = 0
        post["topic_comment_factor"] = comment_factor
        post["base_score"] = detail.base_score
        post["time_weight"] = detail.time_weight
        post["score"] = detail.final_score
        post["score_detail"] = detail.to_dict()
        post.setdefault("top_comment_1", "")
        post.setdefault("top_comment_2", "")
        post.setdefault("top_comment_3", "")
        post.setdefault("top_comment_count", 0)
        post.setdefault("top_comments_data", [])
        post.setdefault("all_comments_data", [])
        post.setdefault("comment_image_urls", "")
        post["comment_analysis_done"] = total_comments <= 0

    def _ensure_candidate_comment_analysis(self, posts: list[dict], config: CrawlConfig) -> bool:
        candidate_pool = _select_weekly_posts(posts, limit=FINAL_COMMENT_ANALYSIS_LIMIT)
        missing = [
            post
            for post in candidate_pool
            if not bool(post.get("comment_analysis_done"))
            and int(post.get("comments", 0) or 0) > 0
            and str(post.get("post_id") or "").strip()
            and str(post.get("author_id") or "").strip()
        ]
        if not missing:
            return False

        total = len(missing)
        worker_count = _bounded_worker_count(config.comment_workers, total)
        self._log(f"补全候选热评与评论结构：{total} 条，{worker_count} 个线程。")
        if worker_count == 1:
            for idx, post in enumerate(missing, start=1):
                self._enrich_score_fields(post, config)
                if idx == total or idx % 5 == 0:
                    self._log(f"候选评论补全进度 {idx}/{total}")
            return True

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="candidate-comments") as executor:
            futures = {
                executor.submit(self._enrich_score_fields_with_private_session, post, config): post
                for post in missing
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                post = futures[future]
                try:
                    future.result()
                except Exception as err:
                    self._log(
                        f"候选评论补全失败 {completed}/{total}: {post.get('post_id', '-')}, "
                        f"{type(err).__name__}: {err}"
                    )
                if completed == total or completed % 5 == 0:
                    self._log(f"候选评论补全进度 {completed}/{total}")
        return True

    def _enrich_score_fields_with_private_session(self, post: dict, config: CrawlConfig) -> None:
        session = self._new_session()
        try:
            self._enrich_score_fields(post, config, session=session)
        finally:
            session.close()

    def _enrich_score_fields(
        self,
        post: dict,
        config: CrawlConfig,
        session: requests.Session | None = None,
    ) -> None:
        total_comments = int(post.get("comments", 0) or 0)
        author_id = str(post.get("author_id") or "")
        post_id = str(post.get("post_id") or "")

        author_replies = 0
        top_comments: list[dict] = []
        all_comments: list[dict] = []
        analysis_ok = total_comments <= 0
        if total_comments > 0 and post_id and author_id:
            try:
                comment_analysis = self._read_comment_cache(post_id)
                if comment_analysis is None:
                    comment_analysis = self._analyze_comments(
                        post_id=post_id,
                        author_id=author_id,
                        page_limit=min(config.comment_page_limit, max(1, math.ceil(total_comments / 20))),
                        session=session,
                    )
                    self._write_comment_cache(post_id, comment_analysis)
                else:
                    self._log(f"已读取评论缓存：{post_id}")
                author_replies = int(comment_analysis.get("author_replies", 0) or 0)
                top_comments = list(comment_analysis.get("top_comments", []) or [])
                all_comments = list(comment_analysis.get("all_comments", []) or [])
                analysis_ok = True
            except Exception:
                # 评论结构接口不稳定时，不让整批任务失败
                author_replies = 0
                top_comments = []
                all_comments = []

        non_author_comments = max(0, total_comments - author_replies)
        comment_factor = max(0.5, float(config.topic_comment_factor))
        publish_dt = parse_publish_datetime(str(post.get("publish_time") or ""))
        detail = calculate_score({**post, "author_replies": author_replies, "publish_dt": publish_dt}, config)

        post["non_author_comments"] = non_author_comments
        post["author_replies"] = author_replies
        post["topic_comment_factor"] = comment_factor
        post["base_score"] = detail.base_score
        post["time_weight"] = detail.time_weight
        post["score"] = detail.final_score
        post["score_detail"] = detail.to_dict()
        post["top_comment_1"] = _format_comment_for_cell(top_comments[0]) if len(top_comments) >= 1 else ""
        post["top_comment_2"] = _format_comment_for_cell(top_comments[1]) if len(top_comments) >= 2 else ""
        post["top_comment_3"] = _format_comment_for_cell(top_comments[2]) if len(top_comments) >= 3 else ""
        post["top_comment_count"] = len(top_comments)
        post["top_comments_data"] = top_comments
        post["all_comments_data"] = all_comments
        post["comment_image_urls"] = " | ".join(_collect_top_comment_image_urls(top_comments))
        post["comment_analysis_done"] = analysis_ok

    def _read_comment_cache(self, post_id: str) -> dict | None:
        if not self.comment_cache_reader:
            return None
        try:
            data = self.comment_cache_reader(post_id)
        except Exception as err:
            self._log(f"评论缓存无效，重新请求：{post_id}，{type(err).__name__}: {err}")
            return None
        if not isinstance(data, dict):
            return None
        required = {"author_replies", "top_comments", "all_comments"}
        if not required.issubset(data):
            self._log(f"评论缓存无效，重新请求：{post_id}")
            return None
        return data

    def _write_comment_cache(self, post_id: str, data: dict) -> None:
        if not self.comment_cache_writer:
            return
        try:
            self.comment_cache_writer(post_id, data)
        except Exception as err:
            self._log(f"评论缓存写入失败：{post_id}，{type(err).__name__}: {err}")

    def _recalibrate_time_weight(self, posts: list[dict], config: CrawlConfig) -> None:
        rows = list(posts)
        if len(rows) < 12:
            return

        # 只用周报候选帖评估拟合，和实际Top15逻辑保持一致
        row_meta: list[tuple[dict, float, datetime | None, str, float | None]] = []
        all_dist: Counter[str] = Counter()
        ref_now = config.window_end or datetime.now()
        for row in rows:
            publish_time = str(row.get("publish_time", "") or "")
            dt = parse_publish_datetime(publish_time)
            date_key = _date_key_from_publish_time(publish_time, dt)
            base_score = float(row.get("base_score", row.get("score", 0.0)) or 0.0)
            age_ratio = _time_age_ratio(dt, ref_now)
            row_meta.append((row, base_score, dt, date_key, age_ratio))
            all_dist[date_key] += 1

        candidate_meta = [item for item in row_meta if not _should_skip_weekly_post(item[0])]
        candidate_rows = [item[0] for item in candidate_meta]
        if len(candidate_rows) < 12:
            return

        if not all_dist:
            return

        # 扩大强度搜索范围，给近一周这类“沉淀不足窗口”更充分的校准空间
        strengths = [x / 100.0 for x in range(0, 121, 5)]  # 0.00 ~ 1.20
        top_n = min(15, len(candidate_rows))
        target_low, target_high = 0.90, 0.93
        target_mid = (target_low + target_high) / 2.0

        results: list[dict] = []
        for strength in strengths:
            picked = heapq.nlargest(
                top_n,
                (
                    (base_score * _time_weight_from_age_ratio(age_ratio, strength), date_key, row)
                    for row, base_score, _dt, date_key, age_ratio in candidate_meta
                ),
                key=lambda x: x[0],
            )
            picked_dist = Counter(item[1] for item in picked)
            fit_info = _calc_date_distribution_fit(all_dist, picked_dist)
            fit_score = float(fit_info.get("fit_score", 0.0) or 0.0)
            avg_score = sum(item[0] for item in picked) / max(1, top_n)
            in_range = target_low <= fit_score <= target_high
            results.append(
                {
                    "strength": strength,
                    "fit_score": fit_score,
                    "avg_score": avg_score,
                    "in_range": in_range,
                    "fit_gap": abs(fit_score - target_mid),
                }
            )

        if not results:
            return

        best = sorted(
            results,
            key=lambda x: (
                0 if x["in_range"] else 1,
                x["fit_gap"],
                -float(x["avg_score"]),
            ),
        )[0]

        # 兜底：若没有任何候选进入目标区间，则优先取拟合度最高者
        if not any(bool(x["in_range"]) for x in results):
            best = sorted(
                results,
                key=lambda x: (
                    -float(x["fit_score"]),
                    -float(x["avg_score"]),
                ),
            )[0]
            best_fit = max(float(x["fit_score"]) for x in results)
            self._log(
                "注意：当前窗口仅靠时间权重难以达到目标拟合区间，"
                f"本次可达到的最高预估拟合度为 {best_fit * 100:.2f}%"
            )

        chosen_strength = float(best["strength"])
        for row, base_score, _dt, _date_key, age_ratio in row_meta:
            w = _time_weight_from_age_ratio(age_ratio, chosen_strength)
            row["time_weight"] = round(w, 4)
            row["score"] = round(base_score * w, 4)

        self._log(
            "时间权重校准完成："
            f"strength={chosen_strength:.2f}，"
            f"预估拟合度={float(best['fit_score']) * 100:.2f}%"
        )

    def _analyze_comments(
        self,
        post_id: str,
        author_id: str,
        page_limit: int,
        session: requests.Session | None = None,
    ) -> dict:
        http = session or self.session
        max_id = "0"
        seen_root_ids: set[str] = set()
        seen_comment_ids: set[str] = set()
        root_reply_counts: dict[str, int] = {}
        comment_candidates: list[dict] = []

        for _ in range(max(1, page_limit)):
            params = {
                "id": post_id,
                "is_reload": "1",
                "is_show_bulletin": "2",
                "is_mix": "0",
                "flow": "1",
                "count": "20",
            }
            if max_id != "0":
                params["max_id"] = max_id

            resp = http.get(
                COMMENTS_API_URL,
                params=params,
                headers={"Referer": f"https://weibo.com/detail/{post_id}", "Origin": "https://weibo.com"},
                timeout=20,
            )
            if resp.status_code >= 400:
                break

            payload = resp.json()
            if int(payload.get("ok", 0) or 0) != 1:
                break

            data = payload.get("data") or []
            if not isinstance(data, list) or not data:
                break

            for root in data:
                root_comment_id = str(root.get("id") or "")
                if root_comment_id and root_comment_id not in seen_comment_ids:
                    seen_comment_ids.add(root_comment_id)
                    comment_candidates.append(
                        {
                            "user_name": str(((root.get("user") or {}).get("screen_name")) or ""),
                            "like_counts": int(root.get("like_counts") or 0),
                            "created_at": str(root.get("created_at") or ""),
                            "text": str(root.get("text_raw") or root.get("text") or ""),
                            "image_urls": _extract_comment_image_urls(root),
                        }
                    )

                root_id = str(root.get("id") or root.get("rootid") or "")
                if not root_id:
                    continue
                if root_id in seen_root_ids:
                    continue
                seen_root_ids.add(root_id)

                replies = root.get("comments") or []
                if not isinstance(replies, list):
                    continue
                for reply in replies:
                    reply_id = str(reply.get("id") or "")
                    if reply_id and reply_id not in seen_comment_ids:
                        seen_comment_ids.add(reply_id)
                        comment_candidates.append(
                            {
                                "user_name": str(((reply.get("user") or {}).get("screen_name")) or ""),
                                "like_counts": int(reply.get("like_counts") or 0),
                                "created_at": str(reply.get("created_at") or ""),
                                "text": str(reply.get("text_raw") or reply.get("text") or ""),
                                "image_urls": _extract_comment_image_urls(reply),
                            }
                        )

                    uid = str(((reply.get("user") or {}).get("id")) or "")
                    if uid != author_id:
                        continue
                    thread_id = str(reply.get("rootid") or root_id)
                    root_reply_counts[thread_id] = min(root_reply_counts.get(thread_id, 0) + 1, 3)

            max_id = str(payload.get("max_id") or "0")
            if max_id == "0":
                break

        top_comments = heapq.nlargest(
            3,
            comment_candidates,
            key=lambda x: (int(x.get("like_counts", 0) or 0), str(x.get("created_at", ""))),
        )

        return {
            "author_replies": sum(root_reply_counts.values()),
            "top_comments": top_comments,
            "all_comments": comment_candidates,
        }

    def hydrate_full_text_posts(self, posts: list[dict], max_workers: int | None = None) -> None:
        all_rows = list(posts)
        rows = [post for post in all_rows if _needs_full_text_hydration(post)]
        total = len(rows)
        skipped = len(all_rows) - total
        if skipped > 0:
            self._log(f"正文校正筛选：{total}/{len(all_rows)} 条需要网络补全，跳过 {skipped} 条完整正文。")
        if not total:
            self._log("正文校正：未发现疑似截断正文，跳过网络补全。")
            return

        worker_count = _bounded_worker_count(max_workers or 6, total)
        if worker_count == 1:
            for idx, post in enumerate(rows, start=1):
                post_id = str(post.get("post_id") or "")
                self._log(f"正文校正 {idx}/{total}: {post_id or '-'}")
                self._hydrate_one_post(post)
            return

        self._log(f"正文校正并行处理：{worker_count} 个线程。")
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="text-hydrate") as executor:
            futures = {
                executor.submit(self._hydrate_one_post_with_private_session, post): post
                for post in rows
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                post = futures[future]
                try:
                    future.result()
                except Exception as err:
                    self._log(
                        f"正文校正失败 {completed}/{total}: {post.get('post_id', '-')}, "
                        f"{type(err).__name__}: {err}"
                    )
                if completed == total or completed % 5 == 0:
                    self._log(f"正文校正进度 {completed}/{total}")

    def _hydrate_one_post_with_private_session(self, post: dict) -> None:
        session = self._new_session()
        try:
            self._hydrate_one_post(post, session=session)
        finally:
            session.close()

    def _hydrate_one_post(self, post: dict, session: requests.Session | None = None) -> None:
        content = str(post.get("content") or "")
        post_id = str(post.get("post_id") or "")
        if not post_id and not str(post.get("post_url") or "").strip():
            return
        full_text, extra_image_urls = self._fetch_post_full_text(post, session=session)
        cleaned_old = _strip_specific_topic_tags(_remove_expand_hint(_clean_text(content)))
        report_old = _strip_specific_topic_tags_preserve(_remove_expand_hint_preserve(content))
        cleaned_new = _strip_specific_topic_tags(_remove_expand_hint(_clean_text(full_text)))
        report_new = _strip_specific_topic_tags_preserve(_remove_expand_hint_preserve(full_text))
        if _should_replace_content(cleaned_old, cleaned_new):
            post["content"] = report_new or cleaned_new
        else:
            post["content"] = report_old or cleaned_old
        if extra_image_urls:
            merged = _dedup_keep_order(
                _split_multi_urls(str(post.get("original_image_urls") or ""), sep="|") + extra_image_urls
            )
            post["original_image_urls"] = " | ".join(merged)
            post["image_count"] = len(merged)

    def _fetch_post_full_text(
        self,
        post: dict,
        session: requests.Session | None = None,
    ) -> tuple[str, list[str]]:
        http = session or self.session
        post_id = str(post.get("post_id") or "")
        post_url = str(post.get("post_url") or "")
        referer = post_url or (f"https://weibo.com/detail/{post_id}" if post_id else "https://weibo.com/")
        full_text = ""
        image_urls: list[str] = []

        if post_id:
            try:
                resp = http.get(
                    "https://weibo.com/ajax/statuses/show",
                    params={"id": post_id},
                    headers={"Referer": referer, "Origin": "https://weibo.com"},
                    timeout=20,
                )
                if resp.status_code == 200:
                    data = resp.json() if resp.content else {}
                    if isinstance(data, dict):
                        raw_text = data.get("text_raw") or data.get("longTextContent_raw") or ""
                        if not raw_text:
                            raw_text = _html_to_text_preserve(str(data.get("text") or data.get("longTextContent") or ""))
                        full_text = _clean_text_preserve(str(raw_text or ""))
                        image_urls = _extract_status_image_urls(data)
            except Exception:
                pass

        if post_id and _looks_truncated_text(full_text):
            try:
                long_resp = http.get(
                    "https://weibo.com/ajax/statuses/longtext",
                    params={"id": post_id},
                    headers={"Referer": referer, "Origin": "https://weibo.com"},
                    timeout=20,
                )
                if long_resp.status_code == 200:
                    payload = long_resp.json() if long_resp.content else {}
                    if isinstance(payload, dict):
                        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                        raw_text = str((data or {}).get("longTextContent_raw") or "")
                        if not raw_text:
                            raw_text = _html_to_text_preserve(str((data or {}).get("longTextContent") or ""))
                        raw_text = _clean_text_preserve(raw_text)
                        if raw_text and _should_replace_content(full_text, raw_text):
                            full_text = raw_text
                        image_urls = _dedup_keep_order(image_urls + _extract_status_image_urls(data or {}))
            except Exception:
                pass

        if post_id and _looks_truncated_text(full_text):
            try:
                mobile_resp = http.get(
                    "https://m.weibo.cn/statuses/extend",
                    params={"id": post_id},
                    headers={"Referer": referer},
                    timeout=20,
                )
                if mobile_resp.status_code == 200 and mobile_resp.content:
                    payload = mobile_resp.json()
                    data = payload.get("data") if isinstance(payload, dict) else {}
                    mobile_text = _html_to_text_preserve(str((data or {}).get("longTextContent") or ""))
                    mobile_text = _clean_text_preserve(mobile_text)
                    if mobile_text and _should_replace_content(full_text, mobile_text):
                        full_text = mobile_text
            except Exception:
                pass

        if (not full_text or _looks_truncated_text(full_text)) and post_url:
            try:
                page = http.get(post_url, headers={"Referer": "https://weibo.com/"}, timeout=20)
                if page.status_code == 200 and page.text:
                    try:
                        html = extract_feed_html_from_page(page.text)
                        parsed = parse_posts_from_html(html)
                    except Exception:
                        parsed = []
                    if parsed:
                        matched = next((x for x in parsed if str(x.get("post_id") or "") == post_id), parsed[0])
                        full_text = _clean_text_preserve(str(matched.get("content") or full_text))
                        image_urls = _dedup_keep_order(
                            image_urls + _split_multi_urls(str(matched.get("original_image_urls") or ""), sep="|")
                        )
                    else:
                        detail_text = _extract_full_text_from_detail_html(page.text)
                        if detail_text:
                            full_text = _clean_text_preserve(detail_text)
                        elif not full_text:
                            blob_text = _extract_text_raw_from_page_blob(page.text)
                            if blob_text:
                                full_text = _clean_text_preserve(blob_text)
            except Exception:
                pass

        return _remove_expand_hint_preserve(full_text), image_urls


def parse_super_topic_id(input_text: str) -> str | None:
    return _parse_super_topic_id(input_text)


def build_report_title(topic_name: str | None = None, super_topic: str | None = None) -> str:
    return _topic_build_report_title(topic_name, super_topic)


def normalize_super_topic_name(value: str) -> str:
    return _topic_normalize_super_topic_name(value)


def extract_super_topic_name(page_html: str, fallback: str | None = None) -> str:
    return _topic_extract_super_topic_name(page_html, fallback)


def extract_feed_html_from_page(page_html: str) -> str:
    try:
        return _html_extract_feed_html_from_page(page_html)
    except ValueError as err:
        raise CrawlError(str(err)) from err


def parse_fm_view_objects(page_html: str) -> list[dict]:
    return _html_parse_fm_view_objects(page_html)


def _skip_space(text: str, start: int) -> int:
    i = start
    while i < len(text) and text[i] in (" ", "\n", "\r", "\t"):
        i += 1
    return i


def _find_json_object_end(text: str, obj_start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[obj_start:], start=obj_start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_posts_from_html(html: str) -> list[dict]:
    return _html_parse_posts_from_html(html)


def _extract_full_text_from_detail_html(page_html: str) -> str:
    try:
        soup = BeautifulSoup(page_html, "lxml")
    except Exception:
        soup = BeautifulSoup(page_html, "html.parser")
    selectors = [
        "div[node-type='feed_list_content_full']",
        "p[node-type='feed_list_content_full']",
        "div.WB_text",
        "p.WB_text",
    ]
    texts: list[str] = []
    for selector in selectors:
        for node in soup.select(selector):
            if _html_is_inside_forwarded_content(node):
                continue
            text = _clean_text_preserve(node.get_text("\n", strip=True))
            if text and "微博社区公约" not in text:
                texts.append(text)
    if not texts:
        return ""
    return max(texts, key=len)


def _extract_text_raw_from_page_blob(page_html: str) -> str:
    # 兜底：从详情页脚本中的 JSON 片段尝试抓 text_raw，避免“展开全文”残留。
    m = re.search(r'"text_raw"\s*:\s*"((?:\\.|[^"\\])*)"', page_html)
    if not m:
        return ""
    raw = m.group(1)
    try:
        decoded = json.loads(f"\"{raw}\"")
    except Exception:
        return ""
    return _html_to_text_preserve(str(decoded or ""))


def parse_publish_datetime(text: str) -> datetime | None:
    return parse_weibo_time(text)


def _parse_publish_datetime_with_format(raw: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        return None


def _apply_carryover_bucket(publish_dt: datetime | None, carryover_hours: int) -> datetime | None:
    """把截止前若干小时的帖子顺延到下一期（通过归档时间平移实现）。"""
    if publish_dt is None:
        return None
    hours = max(0, int(carryover_hours or 0))
    if hours <= 0:
        return publish_dt
    return publish_dt + timedelta(hours=hours)


def _bounded_worker_count(requested: int | None, total: int) -> int:
    if total <= 0:
        return 1
    try:
        desired = int(requested or 1)
    except (TypeError, ValueError):
        desired = 1
    return max(1, min(desired, total, 12))


def _calc_time_weight(publish_dt: datetime | None, now: datetime, strength: float = 0.06) -> float:
    """轻量时间权重：strength 越大，时间偏置越强。"""
    return _time_weight_from_age_ratio(_time_age_ratio(publish_dt, now), strength)


def _time_age_ratio(publish_dt: datetime | None, now: datetime) -> float | None:
    if publish_dt is None:
        return None
    age_hours = max(0.0, (now - publish_dt).total_seconds() / 3600.0)
    return min(1.0, age_hours / (7.0 * 24.0))


def _time_weight_from_age_ratio(age_ratio: float | None, strength: float = 0.06) -> float:
    if age_ratio is None:
        return 1.0
    # 中心约 1.01；strength=0.06 时范围约 [1.04, 0.98]
    # 为避免极端强度时旧帖权重过低，设置下限保护。
    s = max(0.0, float(strength))
    weight = 1.01 + s * (0.5 - age_ratio)
    return max(0.75, weight)


def _should_replace_content(old_text: str, new_text: str) -> bool:
    if not new_text:
        return False
    if not old_text:
        return True
    if old_text == new_text:
        return False
    if _looks_truncated_text(old_text):
        return True
    # 新内容明显更完整时替换
    if len(new_text) >= len(old_text) + 18:
        return True
    # 旧内容疑似截断，且新内容稍长时替换
    return _looks_truncated_text(old_text) and len(new_text) >= len(old_text) + 6


def _looks_truncated_text(text: str) -> bool:
    raw = _clean_text(text)
    if not raw:
        return False
    if "展开全文" in raw or "展开原文" in raw:
        return True
    if raw.endswith(("...", "…", "⋯")):
        return True
    # 超长但以半截字符结尾，通常是列表页截断文本
    return len(raw) >= 140 and not re.search(r"[。！？!?；;）)\]】”\"]$", raw)


def _needs_full_text_hydration(post: dict) -> bool:
    content = str(post.get("content") or "")
    cleaned = _clean_text(content)
    if not cleaned:
        return True
    if _looks_truncated_text(cleaned):
        return True
    return "展开全文" in content or "展开原文" in content


def _remove_expand_hint(text: str) -> str:
    raw = _clean_text(text)
    if not raw:
        return ""
    raw = re.sub(r"(展开全文|展开原文)\s*[cC]?", " ", raw)
    raw = re.sub(r"\s{2,}", " ", raw)
    return raw.strip()


def _remove_expand_hint_preserve(text: str) -> str:
    raw = _clean_text_preserve(text)
    if not raw:
        return ""
    raw = re.sub(r"(展开全文|展开原文)\s*[cC]?", " ", raw)
    return _clean_text_preserve(raw)


def export_posts_csv(posts: Iterable[dict], csv_path: Path) -> None:
    _export_posts_csv(posts, csv_path, EXPORT_COLUMN_MAP)


def export_posts_xlsx(posts: Iterable[dict], xlsx_path: Path) -> None:
    _export_posts_xlsx(posts, xlsx_path, EXPORT_COLUMN_MAP)


def _build_export_row(post: dict) -> dict:
    return _export_build_row(post, EXPORT_COLUMN_MAP)


def build_comment_leaderboards(posts: Iterable[dict], top_n: int = 3) -> dict:
    return _comments_build_comment_leaderboards(posts, top_n=top_n)


def _format_leaderboard_line(
    item: dict,
    include_hot: bool = True,
    include_quality: bool = False,
    include_like_total: bool = True,
    include_post_span: bool = False,
) -> str:
    rank = int(item.get("rank", 0) or 0)
    user_name = _clean_text(str(item.get("user_name", "") or "匿名用户"))
    comment_count = int(item.get("comment_count", 0) or 0)
    commented_post_count = int(item.get("commented_post_count", 0) or 0)
    like_total = int(item.get("comment_likes_total", 0) or 0)
    hot_count = int(item.get("hot_top3_count", 0) or 0)
    line = f"{rank}. @{user_name}：评论 {comment_count} 条"
    if include_post_span:
        line += f"，评论过 {commented_post_count} 条帖子"
    elif include_like_total:
        line += f"，本周评论获赞 {like_total}"
    if include_hot:
        line += f"，热评前三 {hot_count} 次"
    if include_quality:
        line += f"，质量分 {float(item.get('quality_score', 0.0)):.4f}"
    return line


def export_weekly_report_docx(
    posts: Iterable[dict],
    docx_path: Path,
    title: str = "微博超话周报",
    leaderboards: dict | None = None,
    preselected: bool = False,
    max_bytes: int = DOCX_SIZE_LIMIT_BYTES,
) -> list[Path]:
    return _export_weekly_report_docx(
        posts,
        docx_path,
        title=title,
        leaderboards=leaderboards,
        preselected=preselected,
        max_bytes=max_bytes,
    )


def export_weekly_report_sum_docx(
    posts: Iterable[dict],
    docx_path: Path,
    title: str = "微博超话周报",
    leaderboards: dict | None = None,
    preselected: bool = False,
) -> Path:
    return _export_weekly_report_sum_docx(
        posts,
        docx_path,
        title=title,
        leaderboards=leaderboards,
        preselected=preselected,
    )


def export_weekly_report_md(
    posts: Iterable[dict],
    md_path: Path,
    title: str = "微博超话周报",
    leaderboards: dict | None = None,
    preselected: bool = False,
) -> None:
    _export_weekly_report_md(
        posts,
        md_path,
        title=title,
        leaderboards=leaderboards,
        preselected=preselected,
    )


def download_post_images(
    posts: Iterable[dict],
    image_dir: Path,
    cookie: str,
    user_agent: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    max_workers: int | None = None,
    cancel_checker: Callable[[], None] | None = None,
) -> None:
    image_dir.mkdir(parents=True, exist_ok=True)
    ua = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": ua,
        "Cookie": cookie.strip(),
        "Referer": "https://weibo.com/",
    }

    def _new_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(headers)
        return session

    def _download_url_list(
        session: requests.Session,
        urls: list[str],
        target_dir: Path,
        stem: str,
        prefix: str,
    ) -> list[str]:
        target_dir.mkdir(parents=True, exist_ok=True)
        local_paths: list[str] = []
        uniq_urls = _dedup_image_urls(urls)
        for i, url in enumerate(uniq_urls, start=1):
            if cancel_checker:
                cancel_checker()
            ext = _guess_image_ext(url)
            digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            filename = f"{stem}_{prefix}_{i}_{digest}{ext}"
            path = target_dir / filename

            if not path.exists():
                try:
                    resp = session.get(url, timeout=20)
                    if resp.status_code == 200 and resp.content:
                        path.write_bytes(resp.content)
                except Exception:
                    continue
            if path.exists():
                local_paths.append(str(path.resolve()))
        return local_paths

    def _download_one_post(idx: int, post: dict, total: int) -> None:
        if cancel_checker:
            cancel_checker()
        session = _new_session()
        try:
            post_id = str(post.get("post_id") or "")
            stem = post_id or f"post_{idx}"
            user_name = _safe_filename_part(str(post.get("user_name") or "未知作者"))
            post_dir_name = f"{idx:02d}_{user_name}"
            if post_id:
                post_dir_name += f"_{post_id}"
            post_dir = image_dir / post_dir_name
            post_urls = _split_multi_urls(str(post.get("original_image_urls") or ""), sep="|")

            if progress_callback:
                progress_callback(f"下载图片进度 {idx}/{total}: {post_id or '-'}")
            if cancel_checker:
                cancel_checker()

            post_local_paths = _download_url_list(session, post_urls, post_dir, stem=stem, prefix="post")
            post["downloaded_image_count"] = len(post_local_paths)
            post["image_local_paths"] = " | ".join(post_local_paths)

            top_comments = list(post.get("top_comments_data") or [])
            all_comment_local_paths: list[str] = []
            for c_idx, comment in enumerate(top_comments, start=1):
                raw_urls = comment.get("image_urls") or []
                if isinstance(raw_urls, str):
                    comment_urls = _split_multi_urls(raw_urls, sep="|")
                else:
                    comment_urls = _dedup_keep_order(
                        [_to_original_pic_url(str(u)) for u in list(raw_urls) if str(u).strip()]
                    )

                comment_urls = _dedup_image_urls(comment_urls)
                comment_local_paths = _download_url_list(
                    session,
                    comment_urls,
                    post_dir,
                    stem=stem,
                    prefix=f"comment{c_idx}",
                )
                comment["image_urls"] = " | ".join(comment_urls)
                comment["image_local_paths"] = " | ".join(comment_local_paths)
                all_comment_local_paths.extend(comment_local_paths)

            post["top_comments_data"] = top_comments
            post["downloaded_comment_image_count"] = len(all_comment_local_paths)
            post["comment_image_local_paths"] = " | ".join(all_comment_local_paths)
            post["image_local_paths_all"] = " | ".join(post_local_paths + all_comment_local_paths)
            if cancel_checker:
                cancel_checker()
        finally:
            session.close()

    rows = list(posts)
    if not rows:
        return

    worker_count = max(1, min(int(max_workers or 6), len(rows)))
    if worker_count == 1:
        for idx, post in enumerate(rows, start=1):
            if cancel_checker:
                cancel_checker()
            _download_one_post(idx, post, len(rows))
        return

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="image-download") as executor:
        futures = {
            executor.submit(_download_one_post, idx, post, len(rows)): idx
            for idx, post in enumerate(rows, start=1)
        }
        for future in as_completed(futures):
            if cancel_checker:
                cancel_checker()
            idx = futures[future]
            try:
                future.result()
            except Exception as err:
                if progress_callback:
                    progress_callback(f"下载图片失败 {idx}/{len(rows)}: {type(err).__name__}: {err}")


def build_summary(posts: Iterable[dict]) -> dict:
    return _export_build_summary(posts)


def analyze_active_period(posts: Iterable[dict]) -> dict:
    return _export_analyze_active_period(posts)


def write_summary_txt(
    summary: dict,
    txt_path: Path,
    leaderboards: dict | None = None,
    active_period: dict | None = None,
    all_posts_summary: dict | None = None,
    carryover_hours: int = 0,
) -> None:
    _export_write_summary_txt(
        summary,
        txt_path,
        leaderboards=leaderboards,
        active_period=active_period,
        all_posts_summary=all_posts_summary,
        carryover_hours=carryover_hours,
        format_leaderboard_line=_format_leaderboard_line,
    )


def _calc_date_distribution_fit(
    all_dist: dict[str, int],
    selected_dist: dict[str, int],
) -> dict:
    return _export_calc_date_distribution_fit(all_dist, selected_dist)


def normalize_date(text: str) -> str | None:
    return _normalize_date(text)


def _date_key_from_publish_time(text: str, parsed_dt: datetime | None = None) -> str:
    if parsed_dt is not None:
        return parsed_dt.strftime("%Y-%m-%d")
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", str(text or "").strip())
    if m:
        return m.group(1)
    return "未知日期"


def _extract_original_image_urls(item: Tag) -> list[str]:
    return _html_extract_original_image_urls(item)


def _to_absolute_url(url: str) -> str:
    return to_absolute_url(url)


def _to_original_pic_url(url: str) -> str:
    return _image_to_original_pic_url(url)


def _split_url_candidates(text: str) -> list[str]:
    return _image_split_url_candidates(text)


def _split_multi_urls(text: str, sep: str) -> list[str]:
    return _image_split_multi_urls(text, sep=sep)


def _guess_image_ext(url: str) -> str:
    return _image_guess_image_ext(url)


def _extract_sinaimg_host(url: str) -> str:
    return _image_extract_sinaimg_host(url)


def _dedup_keep_order(values: list[str]) -> list[str]:
    return _image_dedup_keep_order(values)


def parse_count(text: str) -> int:
    return _html_parse_count(text)


def _format_comment_for_cell(comment: dict) -> str:
    if not comment:
        return ""
    user = _clean_text(str(comment.get("user_name", "") or "")) or "匿名用户"
    likes = int(comment.get("like_counts", 0) or 0)
    created = _normalize_comment_time(str(comment.get("created_at", "") or ""))
    content = _clean_text(str(comment.get("text", "") or ""))
    has_image = bool(_collect_comment_image_urls(comment))
    if has_image:
        content = _strip_url_like_text(content)
    content = re.sub(r"[\r\n]+", " ", content)
    if not content and has_image:
        content = "（图片评论）"
    if created:
        return f"{user}（赞{likes}，{created}）：{content}"
    return f"{user}（赞{likes}）：{content}"


def _normalize_comment_time(text: str) -> str:
    raw = _clean_text(text)
    if not raw:
        return ""
    try:
        dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw


def _format_posts_date_range(posts: list[dict]) -> str:
    return _report_format_posts_date_range(posts)


def _simplify_hot_comment(text: str) -> str:
    return _report_simplify_hot_comment(text)


def _to_rel_path(base_dir: Path, target: Path) -> str:
    return _report_to_rel_path(base_dir, target)


def _report_divider_line() -> str:
    return "─" * 25


def _select_weekly_posts(posts: Iterable[dict], limit: int = 15) -> list[dict]:
    return _report_select_weekly_posts(posts, limit=limit)


def select_weekly_posts(posts: Iterable[dict], limit: int = 15) -> list[dict]:
    return _select_weekly_posts(posts, limit=limit)


def _should_skip_weekly_post(post: dict) -> bool:
    excluded, _reason = should_exclude_post(post)
    return excluded


def _is_video_post(post: dict) -> bool:
    excluded, reason = should_exclude_post(post)
    return excluded and reason == "视频帖"


def _is_summary_post(content: str) -> bool:
    excluded, reason = should_exclude_post({"content": content})
    return excluded and reason in {"汇总帖", "导航帖"}


def _get_embed_image_paths(post: dict) -> list[str]:
    all_paths = _split_multi_urls(str(post.get("image_local_paths_all") or ""), sep="|")
    if all_paths:
        return all_paths
    post_paths = _split_multi_urls(str(post.get("image_local_paths") or ""), sep="|")
    comment_paths = _split_multi_urls(str(post.get("comment_image_local_paths") or ""), sep="|")
    return _dedup_keep_order(post_paths + comment_paths)


def _iter_report_comments(post: dict) -> list[dict]:
    return _report_iter_report_comments(post)


def _format_hot_comment_text(comment: dict) -> str:
    return _report_format_hot_comment_text(comment)


def _collect_top_comment_image_urls(top_comments: list[dict]) -> list[str]:
    return _image_collect_top_comment_image_urls(top_comments)


def _extract_comment_image_urls(comment: dict) -> list[str]:
    return _collect_comment_image_urls(comment)


def _extract_status_image_urls(status: dict) -> list[str]:
    return _image_extract_status_image_urls(status)


def _collect_comment_image_urls(comment: dict) -> list[str]:
    return _image_collect_comment_image_urls(comment)


def _dedup_image_urls(urls: list[str]) -> list[str]:
    return _image_dedup_image_urls(urls)


def _image_signature(url: str) -> str:
    return _image_image_signature(url)


def _extract_urls_from_data_node(node) -> list[str]:
    return _image_extract_urls_from_data_node(node)


def _looks_like_image_url(url: str) -> bool:
    return _image_looks_like_image_url(url)


def _html_to_text(text: str) -> str:
    return strip_html_text(text)


def _html_to_text_preserve(text: str) -> str:
    return strip_html_text(text, preserve_newlines=True)


def _strip_url_like_text(text: str) -> str:
    return _report_strip_url_like_text(text)


def _strip_specific_topic_tags(text: str) -> str:
    return clean_topic_tags(text)


def _strip_specific_topic_tags_preserve(text: str) -> str:
    return clean_topic_tags(text, preserve_newlines=True)


def _safe_filename_part(text: str, max_len: int = 24) -> str:
    raw = _clean_text(text) or "item"
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    raw = re.sub(r"\s+", "_", raw).strip("._ ")
    return (raw or "item")[:max_len]


def _clean_report_text(text: str) -> str:
    return _report_clean_report_text(text)


def _replace_weibo_emoticons(text: str) -> str:
    return _report_replace_weibo_emoticons(text)


def _replace_unicode_emoji(text: str) -> str:
    return _report_replace_unicode_emoji(text)


def _first_text(elements: list) -> str:
    if not elements:
        return ""
    return elements[0].get_text(" ", strip=True)


def _clean_text(text: str) -> str:
    return normalize_weibo_text(text)


def _clean_text_preserve(text: str) -> str:
    return collapse_blank_lines(text)

