from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from cookie_helper import CookieFetchError, extract_cookie_from_text, get_weibo_cookie_header
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
    select_weekly_posts,
    write_summary_txt,
)


class WeiboStatsApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("微博超话帖子统计工具")
        self.root.geometry("1220x860")
        self.root.minsize(1000, 700)

        self.super_topic_var = tk.StringVar(
            value="https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index"
        )
        self.cookie_var = tk.StringVar()
        self.max_pages_var = tk.StringVar(value="80")
        self.topic_comment_factor_var = tk.StringVar(value="1.0")
        self.pause_var = tk.StringVar(value="1.0")

        now = datetime.now()
        end_dt_default = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if now < end_dt_default:
            end_dt_default -= timedelta(days=1)
        start_dt = end_dt_default - timedelta(days=7)
        self.start_year_var = tk.StringVar(value=str(start_dt.year))
        self.start_month_var = tk.StringVar(value=f"{start_dt.month:02d}")
        self.start_day_var = tk.StringVar(value=f"{start_dt.day:02d}")
        self.start_hour_var = tk.StringVar(value=f"{start_dt.hour:02d}")

        self.end_year_var = tk.StringVar(value=str(end_dt_default.year))
        self.end_month_var = tk.StringVar(value=f"{end_dt_default.month:02d}")
        self.end_day_var = tk.StringVar(value=f"{end_dt_default.day:02d}")
        self.end_hour_var = tk.StringVar(value=f"{end_dt_default.hour:02d}")
        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "output"))

        self.cookie_entry: ttk.Entry | None = None
        self.fetch_cookie_btn: ttk.Button | None = None
        self.start_btn: ttk.Button | None = None
        self.progress: ttk.Progressbar | None = None
        self.log_text: tk.Text | None = None
        self.start_day_combo: ttk.Combobox | None = None
        self.end_day_combo: ttk.Combobox | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text="微博超话帖子统计", font=("Microsoft YaHei UI", 19, "bold"))
        title.pack(anchor=tk.W, pady=(0, 12))

        form = ttk.Frame(main)
        form.pack(fill=tk.X)
        form.grid_columnconfigure(1, weight=1)

        self._add_labeled_entry(form, 0, "超话链接或ID", self.super_topic_var, 98)

        ttk.Label(form, text="微博 Cookie").grid(row=1, column=0, sticky=tk.W, pady=6)
        self.cookie_entry = ttk.Entry(form, textvariable=self.cookie_var, width=72, show="*")
        self.cookie_entry.grid(row=1, column=1, sticky=tk.EW, pady=6, padx=(10, 6))

        cookie_btn_row = ttk.Frame(form)
        cookie_btn_row.grid(row=1, column=2, columnspan=2, sticky=tk.W, pady=6)
        self.fetch_cookie_btn = ttk.Button(cookie_btn_row, text="自动获取Cookie", command=self.auto_fetch_cookie)
        self.fetch_cookie_btn.pack(side=tk.LEFT)
        ttk.Button(cookie_btn_row, text="剪贴板导入", command=self.import_cookie_from_clipboard).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        years = [str(y) for y in range(datetime.now().year - 5, datetime.now().year + 2)]
        months = [f"{m:02d}" for m in range(1, 13)]
        hours = [f"{h:02d}" for h in range(0, 24)]

        ttk.Label(form, text="起始日期时间").grid(row=2, column=0, sticky=tk.W, pady=6)
        start_row = ttk.Frame(form)
        start_row.grid(row=2, column=1, sticky=tk.W, pady=6, padx=(10, 6))
        ttk.Combobox(start_row, textvariable=self.start_year_var, values=years, state="readonly", width=6).pack(side=tk.LEFT)
        ttk.Label(start_row, text="年").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Combobox(start_row, textvariable=self.start_month_var, values=months, state="readonly", width=4).pack(side=tk.LEFT)
        ttk.Label(start_row, text="月").pack(side=tk.LEFT, padx=(2, 4))
        self.start_day_combo = ttk.Combobox(start_row, textvariable=self.start_day_var, state="readonly", width=4)
        self.start_day_combo.pack(side=tk.LEFT)
        ttk.Label(start_row, text="日").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Combobox(start_row, textvariable=self.start_hour_var, values=hours, state="readonly", width=4).pack(side=tk.LEFT)
        ttk.Label(start_row, text="时（整点）").pack(side=tk.LEFT, padx=(2, 0))

        ttk.Label(form, text="结束日期时间").grid(row=3, column=0, sticky=tk.W, pady=6)
        end_row = ttk.Frame(form)
        end_row.grid(row=3, column=1, sticky=tk.W, pady=6, padx=(10, 6))
        ttk.Combobox(end_row, textvariable=self.end_year_var, values=years, state="readonly", width=6).pack(side=tk.LEFT)
        ttk.Label(end_row, text="年").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Combobox(end_row, textvariable=self.end_month_var, values=months, state="readonly", width=4).pack(side=tk.LEFT)
        ttk.Label(end_row, text="月").pack(side=tk.LEFT, padx=(2, 4))
        self.end_day_combo = ttk.Combobox(end_row, textvariable=self.end_day_var, state="readonly", width=4)
        self.end_day_combo.pack(side=tk.LEFT)
        ttk.Label(end_row, text="日").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Combobox(end_row, textvariable=self.end_hour_var, values=hours, state="readonly", width=4).pack(side=tk.LEFT)
        ttk.Label(end_row, text="时（整点）").pack(side=tk.LEFT, padx=(2, 0))

        self.start_year_var.trace_add("write", lambda *_: self._refresh_day_values(is_start=True))
        self.start_month_var.trace_add("write", lambda *_: self._refresh_day_values(is_start=True))
        self.end_year_var.trace_add("write", lambda *_: self._refresh_day_values(is_start=False))
        self.end_month_var.trace_add("write", lambda *_: self._refresh_day_values(is_start=False))
        self._refresh_day_values(is_start=True)
        self._refresh_day_values(is_start=False)

        self._add_labeled_entry(form, 4, "最大翻页页数（安全上限）", self.max_pages_var, 14)
        self._add_labeled_entry(form, 5, "话题评论系数（>=0.5）", self.topic_comment_factor_var, 14)
        self._add_labeled_entry(form, 6, "请求间隔（秒）", self.pause_var, 14)

        ttk.Label(form, text="导出目录").grid(row=7, column=0, sticky=tk.W, pady=6)
        ttk.Entry(form, textvariable=self.output_dir_var, width=72).grid(
            row=7, column=1, sticky=tk.EW, pady=6, padx=(10, 6)
        )
        ttk.Button(form, text="选择", command=self._choose_output_dir).grid(row=7, column=2, sticky=tk.W, pady=6)

        hint = ttk.Label(
            main,
            text=(
                "提示：建议先点“自动获取Cookie”从已登录浏览器读取。\n"
                "时间范围仅保留“自定义日期时间”（可选，不用手动输入）。\n"
                "默认区间为：最近一次已过的04:00 到上周同时刻04:00。\n"
                "你可以按任意日期区间抓取，便于比较不同时间段拟合程度。\n"
                "抓取后会弹出前20条人工勾选窗口，默认勾选前15条。"
            ),
            foreground="#555555",
        )
        hint.pack(anchor=tk.W, pady=(8, 8))

        button_row = ttk.Frame(main)
        button_row.pack(fill=tk.X, pady=(0, 8))
        self.start_btn = ttk.Button(button_row, text="开始抓取并导出", command=self.start_crawl)
        self.start_btn.pack(side=tk.LEFT)
        ttk.Button(button_row, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(main, text="运行日志").pack(anchor=tk.W)
        self.log_text = tk.Text(main, height=23, wrap=tk.WORD, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.StringVar,
        width: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=6)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky=tk.EW, pady=6, padx=(10, 6))

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择导出目录", initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if selected:
            self.output_dir_var.set(selected)

    def _clear_log(self) -> None:
        if not self.log_text:
            return
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def log(self, msg: str) -> None:
        if not self.log_text:
            return
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"

        def _append() -> None:
            if not self.log_text:
                return
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, _append)

    def auto_fetch_cookie(self) -> None:
        if self.fetch_cookie_btn:
            self.fetch_cookie_btn.configure(state=tk.DISABLED)
        self.log("正在自动读取浏览器 Cookie...")
        threading.Thread(target=self._cookie_worker, daemon=True).start()

    def import_cookie_from_clipboard(self) -> None:
        try:
            text = self.root.clipboard_get()
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("读取失败", f"无法读取剪贴板：{err}")
            return
        cookie = extract_cookie_from_text(text)
        if not cookie:
            messagebox.showerror("导入失败", "剪贴板内容中未识别到 Cookie。")
            return
        self.cookie_var.set(cookie)
        self.log("已从剪贴板导入 Cookie。")
        messagebox.showinfo("成功", "Cookie 已导入。")

    def _cookie_worker(self) -> None:
        try:
            cookie = get_weibo_cookie_header()
            self.root.after(0, lambda: self.cookie_var.set(cookie))
            self.log("Cookie 读取成功，已自动填入。")
            self.root.after(0, lambda: messagebox.showinfo("成功", "Cookie 已自动填入。"))
        except CookieFetchError as err:
            self.log(f"Cookie 读取失败：{err}")
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "自动获取失败",
                    (
                        f"{err}\n\n建议：\n"
                        "1) 在普通浏览器窗口登录 weibo.com\n"
                        "2) 保持登录状态有效\n"
                        "3) 失败时改用剪贴板导入"
                    ),
                ),
            )
        except Exception as err:  # noqa: BLE001
            self.log(f"Cookie 读取失败：{type(err).__name__}: {err}")
            self.root.after(0, lambda: messagebox.showerror("自动获取失败", f"{type(err).__name__}: {err}"))
        finally:
            self.root.after(0, self._finish_cookie_fetch_ui)

    def _finish_cookie_fetch_ui(self) -> None:
        if self.fetch_cookie_btn:
            self.fetch_cookie_btn.configure(state=tk.NORMAL)

    def start_crawl(self) -> None:
        try:
            max_pages = int(self.max_pages_var.get().strip())
            topic_comment_factor = float(self.topic_comment_factor_var.get().strip())
            pause_seconds = float(self.pause_var.get().strip())
            if max_pages <= 0 or pause_seconds < 0 or topic_comment_factor < 0.5:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "参数错误",
                "最大翻页页数需为正数，请求间隔需非负，话题评论系数需 >= 0.5。",
            )
            return

        if not self.super_topic_var.get().strip():
            messagebox.showerror("参数错误", "请填写超话链接或ID。")
            return
        if not self.cookie_var.get().strip():
            messagebox.showerror("参数错误", "请先填写 Cookie。")
            return

        try:
            window_start = self._build_datetime_from_picker(is_start=True)
            window_end = self._build_datetime_from_picker(is_start=False)
            if window_end <= window_start:
                raise ValueError("结束时间必须晚于开始时间")
        except ValueError as err:
            messagebox.showerror("参数错误", f"日期时间设置错误：{err}")
            return

        if self.start_btn:
            self.start_btn.configure(state=tk.DISABLED)
        if self.progress:
            self.progress.start(10)

        self.log("开始任务...")
        self.log(f"自定义日期区间：{window_start.strftime('%Y-%m-%d %H:%M')} -> {window_end.strftime('%Y-%m-%d %H:%M')}")

        days_window = max(1, int((window_end - window_start).days) + 1)

        cfg = CrawlConfig(
            super_topic=self.super_topic_var.get().strip(),
            cookie=self.cookie_var.get().strip(),
            max_pages=max_pages,
            days_window=days_window,
            topic_comment_factor=topic_comment_factor,
            pause_seconds=pause_seconds,
            window_start=window_start,
            window_end=window_end,
            carryover_hours=0,
        )
        threading.Thread(target=self._crawl_worker, args=(cfg,), daemon=True).start()

    def _crawl_worker(self, cfg: CrawlConfig) -> None:
        try:
            crawler = WeiboSuperTopicCrawler(cookie=cfg.cookie, progress_callback=self.log)
            posts_all = crawler.crawl(cfg)

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
            self.log(f"进入人工筛选：候选 {len(candidates)} 条（默认勾选前15条）")
            selected_posts = self._request_manual_post_selection(candidates, pick_count=15)
            if selected_posts is None:
                raise CrawlError("已取消人工筛选，任务中止。")
            self.log(f"人工筛选完成：最终导出 {len(selected_posts)} 条。")

            output_dir = Path(self.output_dir_var.get().strip() or "output")
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = output_dir / ts
            run_dir.mkdir(parents=True, exist_ok=True)
            image_dir = run_dir / "images"

            self.log("正在下载帖子/评论图片...")
            download_post_images(
                posts=selected_posts,
                image_dir=image_dir,
                cookie=cfg.cookie,
                progress_callback=self.log,
            )

            summary = build_summary(selected_posts)
            all_posts_summary = build_summary(posts_all)
            leaderboards = build_comment_leaderboards(posts_all, top_n=3)

            xlsx_path = run_dir / "weibo_posts.xlsx"
            csv_path = run_dir / "weibo_posts.csv"
            txt_path = run_dir / "weibo_summary.txt"
            report_docx_path = run_dir / "warma_weekly_report.docx"
            report_md_path = run_dir / "warma_weekly_report.md"

            export_posts_xlsx(selected_posts, xlsx_path)
            export_posts_csv(selected_posts, csv_path)
            write_summary_txt(
                summary,
                txt_path,
                leaderboards=leaderboards,
                active_period=active_period,
                all_posts_summary=all_posts_summary,
                carryover_hours=cfg.carryover_hours,
            )
            report_docx_paths = export_weekly_report_docx(
                selected_posts,
                report_docx_path,
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
            self.log(f"MD 已保存：{report_md_path}")
            self.log(f"汇总已保存：{txt_path}")
            self.log(f"本次导出目录：{run_dir}")

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "完成",
                    (
                        f"抓取完成，共 {summary['total_posts']} 条帖子。\n\n"
                        f"Excel:\n{xlsx_path}\n\n"
                        f"CSV:\n{csv_path}\n\n"
                        f"DOCX:\n{chr(10).join(str(p) for p in report_docx_paths)}\n\n"
                        f"MD:\n{report_md_path}\n\n"
                        f"图片目录:\n{image_dir}\n\n"
                        f"汇总:\n{txt_path}\n\n"
                        f"导出目录:\n{run_dir}"
                    ),
                ),
            )
        except CrawlError as err:
            self.log(f"任务失败：{err}")
            self.root.after(0, lambda: messagebox.showerror("抓取失败", str(err)))
        except Exception as err:  # noqa: BLE001
            self.log(f"任务失败：{type(err).__name__}: {err}")
            self.root.after(0, lambda: messagebox.showerror("抓取失败", f"{type(err).__name__}: {err}"))
        finally:
            self.root.after(0, self._finish_task_ui)

    def _days_in_month(self, year: int, month: int) -> int:
        if month == 12:
            nxt = datetime(year + 1, 1, 1)
        else:
            nxt = datetime(year, month + 1, 1)
        cur = datetime(year, month, 1)
        return (nxt - cur).days

    def _refresh_day_values(self, is_start: bool) -> None:
        year_var = self.start_year_var if is_start else self.end_year_var
        month_var = self.start_month_var if is_start else self.end_month_var
        day_var = self.start_day_var if is_start else self.end_day_var
        day_combo = self.start_day_combo if is_start else self.end_day_combo
        if day_combo is None:
            return
        try:
            year = int(year_var.get())
            month = int(month_var.get())
            if month < 1 or month > 12:
                month = 1
        except Exception:  # noqa: BLE001
            return
        max_day = self._days_in_month(year, month)
        day_values = [f"{d:02d}" for d in range(1, max_day + 1)]
        day_combo.configure(values=day_values)
        current_day = day_var.get().strip()
        if current_day not in day_values:
            day_var.set(day_values[-1])

    def _build_datetime_from_picker(self, is_start: bool) -> datetime:
        if is_start:
            year = int(self.start_year_var.get())
            month = int(self.start_month_var.get())
            day = int(self.start_day_var.get())
            hour = int(self.start_hour_var.get())
        else:
            year = int(self.end_year_var.get())
            month = int(self.end_month_var.get())
            day = int(self.end_day_var.get())
            hour = int(self.end_hour_var.get())
        return datetime(year, month, day, hour, 0)

    def _request_manual_post_selection(self, candidates: list[dict], pick_count: int = 15) -> list[dict] | None:
        holder: dict[str, list[dict] | None] = {"value": None}
        done = threading.Event()

        def _open_dialog() -> None:
            try:
                holder["value"] = self._show_post_review_dialog(candidates, pick_count)
            finally:
                done.set()

        self.root.after(0, _open_dialog)
        done.wait()
        return holder["value"]

    def _show_post_review_dialog(self, candidates: list[dict], pick_count: int) -> list[dict] | None:
        rows = list(candidates)[:20]
        target = min(pick_count, len(rows))
        if target <= 0:
            return []

        dlg = tk.Toplevel(self.root)
        dlg.title("人工筛选帖子（前20选15）")
        dlg.geometry("1060x780")
        dlg.minsize(920, 650)
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(
            dlg,
            text=f"请勾选要导出的帖子：候选 {len(rows)} 条，最终需保留 {target} 条。",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor=tk.W, padx=12, pady=(12, 6))
        ttk.Label(
            dlg,
            text="默认勾选前15条。你可以取消其中某条，再勾选后5条中的帖子进行替换。",
            foreground="#555555",
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))

        count_var = tk.StringVar(value=f"已勾选：{target}/{target}")
        ttk.Label(dlg, textvariable=count_var).pack(anchor=tk.W, padx=12, pady=(0, 6))

        container = ttk.Frame(dlg)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        vars_: list[tk.BooleanVar] = []
        for idx, post in enumerate(rows, start=1):
            frame = ttk.Frame(inner, padding=(6, 6))
            frame.pack(fill=tk.X, expand=True, anchor=tk.W)

            checked = idx <= target
            var = tk.BooleanVar(value=checked)
            vars_.append(var)

            head = f"{idx:02d}. {post.get('user_name', '未知作者')} | {post.get('publish_time', '')}"
            ttk.Checkbutton(frame, text=head, variable=var).pack(anchor=tk.W)

            preview = self._post_preview_text(post)
            tk.Message(
                frame,
                text=preview,
                width=960,
                anchor="w",
                justify=tk.LEFT,
                font=("Microsoft YaHei UI", 10),
            ).pack(anchor=tk.W, padx=(22, 0), pady=(2, 4))
            ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 0))

        def _update_count(*_args) -> None:
            selected = sum(1 for v in vars_ if v.get())
            count_var.set(f"已勾选：{selected}/{target}")

        for v in vars_:
            v.trace_add("write", _update_count)

        result: dict[str, list[dict] | None] = {"value": None}

        def _confirm() -> None:
            selected_idx = [i for i, v in enumerate(vars_) if v.get()]
            if len(rows) >= target and len(selected_idx) != target:
                messagebox.showerror("数量不符", f"请恰好勾选 {target} 条帖子。", parent=dlg)
                return
            if not selected_idx:
                messagebox.showerror("数量不符", "请至少勾选 1 条帖子。", parent=dlg)
                return
            result["value"] = [rows[i] for i in selected_idx[:target]]
            dlg.destroy()

        def _cancel() -> None:
            result["value"] = None
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(btn_row, text="确认导出", command=_confirm).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="取消", command=_cancel).pack(side=tk.LEFT, padx=(8, 0))

        dlg.wait_window()
        return result["value"]

    def _post_preview_text(self, post: dict, max_chars: int = 420) -> str:
        content = re.sub(r"\s+", " ", str(post.get("content", "") or "")).strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        return content

    def _finish_task_ui(self) -> None:
        if self.progress:
            self.progress.stop()
        if self.start_btn:
            self.start_btn.configure(state=tk.NORMAL)


def main() -> None:
    root = tk.Tk()
    app = WeiboStatsApp(root)
    root.mainloop()
    del app


if __name__ == "__main__":
    main()
