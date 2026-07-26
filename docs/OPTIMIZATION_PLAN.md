# 优化方案

针对 v0.11.1 的一次全仓审计结果与落地路线图。审计覆盖后端 HTTP 层、任务编排、抓取层、导出层、前端、测试工程化、安全隐私七个维度，共确认 64 条中高优先级问题与 22 条打磨项，全部经过独立复核并附代码位置。

本文档按「批次」组织，每个批次对应一个可独立提交的 PR。批次内条目按依赖顺序排列。

## 落地进度

分支 `optimize/security-and-robustness` 已完成批次一至批次六，测试从 154 个增加到 189 个，`ruff check` 全绿。

| 批次 | 状态 | 提交 |
| --- | --- | --- |
| 一 · 本地 API 安全闭环 | 已完成 | `fix(server): close the local API's CSRF, rebinding and traversal holes` |
| 二 · 仓库卫生 | 已完成（`frontend/` 未删除，见下） | `chore(security): ignore credential backups...` |
| 三 · 数据不丢失 | 已完成 | `fix(core): make config/history writes atomic...`、`fix(job): a failed export no longer destroys the crawl` |
| 四 · 抓取健壮性 | 已完成 | `fix(crawler): retry, throttle and stop hiding degraded results` |
| 五 · 测试与 CI | 已完成 | `test: stop leaking cache directories...`、`chore: add CI, ruff config...` |
| 六 · 性能 | 已完成 | `perf(web): stop re-rendering...`、`perf(export): stop rebuilding DOCX per post...` |
| 七 · 可维护性重构 | 未做 | 需要较大改动面，建议单独排期 |
| 八 · 打磨项 | 部分完成 | 见下方各条目 |

批次七（`job.py` / `crawler.py` 拆分、进度改结构化事件、`cookie_helper` 依赖方向）刻意留下：这些是大范围重构，风险收益比不适合和上述修复混在一起提交。

**留给你决定的两件事：**

1. **`frontend/` 目录未删除**，只加进了 `.gitignore`。它确认是零源码空壳（`src/` 下五个子目录全空、无 `package.json`、159 MB `node_modules`），但删除不可逆，所以没有替你做。要清掉直接 `rmdir /s /q frontend`。
2. **`assets/weibo_emoticons` 的 vendor 决策未做**（批次二 2.4）。现状「半缓存半资产」维持原样，需要你在两个选项间选一个。

另外已顺手清理了项目根 `cache/` 下 160 个测试泄漏的 `tmp*` 目录（187 → 27）。剩下 27 个全部是时间戳运行目录，一律未动；其中 `20260511_010101`、`20260512_010101`、`20260512_020202` 三个看起来是旧测试残留的孤儿（output 下无对应目录），你可以自行确认后删除。

## 结论

项目结构清晰、分层意识良好（`modules/` 纯逻辑、`export/` 无网络、cache/reexport 离线恢复设计都很扎实），测试 154 个用例 11 秒全绿且完全离线。主要问题集中在三处：

1. **本地 HTTP 服务缺少最基本的来源与路径护栏**，三个独立缺陷可以串成一条真实可利用的攻击链，能读走含 `SUB`/`SUBP` 的微博登录态。
2. **失败路径过于激进**：导出阶段任何一次文件被占用，都会连同已抓取的 cache 一起删除，用户几十分钟的抓取成果归零，而 reexport 的离线恢复设计因此完全用不上。
3. **抓取层零重试、限速覆盖不全**，一次瞬时网络抖动即整单失败；限流导致的降级又被裸 `except` 吞掉，用户拿到残缺报告却毫无感知。

其余是可维护性与性能打磨，不紧急但成本很低。

## 路线图

| 批次 | 主题 | 条目数 | 累计成本 | 优先级 |
| --- | --- | --- | --- | --- |
| 一 | 本地 API 安全闭环 | 6 | 半天 | P0 |
| 二 | 仓库卫生与 `frontend/` 处置 | 4 | 30 分钟 | P0 |
| 三 | 数据不丢失 | 6 | 1 天 | P1 |
| 四 | 抓取健壮性与报告质量 | 7 | 1~2 天 | P1 |
| 五 | 测试隔离、安全回归与 CI | 6 | 1 天 | P1 |
| 六 | 性能 | 9 | 1~2 天 | P2 |
| 七 | 可维护性与去重 | 12 | 按需 | P2/P3 |
| 八 | 打磨项 | 15+ | 按需 | P3 |

如果只做五件事：批次一 → 批次二 → 批次三 → 批次四 → 批次五。前两个批次合计不到一天，堵住的是不可逆损失（凭据泄漏、数据被删）。

---

## 批次一：本地 API 安全闭环（P0）

这六条单独看都不致命，组合起来构成完整攻击链：恶意网页 → DNS rebinding 绕过同源 → 读 `/api/defaults` 拿明文 Cookie，或读 `/api/report-preview` 拿任意本地文件。全部改动集中在 `server/handlers.py` 入口、`server/responses.py` 和 `core/config.py`，适合一个 PR 完成。

### 1.1 `md_path` 无目录白名单，构成任意本地文件读取

`handle_report_preview` 把查询参数 `md_path` 直接当路径，只判断 `exists()/is_file()` 就全文返回（`server/handlers.py:504-516`）。`handle_report_asset` 更进一步，用这个未校验的路径的父目录作为 `resolve_report_asset_path` 的 base（`server/handlers.py:522-532` → `:855-865` 的 `base = report_path.parent.resolve()`），于是那套「基于 base 的越界拦截」被彻底架空。

可直接复现：

```
GET /api/report-preview?md_path=<项目根>/weibo_stats_config.json
→ 含完整 SUB/SUBP 的配置文件被当 Markdown 全文返回

GET /api/report-asset?md_path=C:/Windows/win.ini&path=system.ini
→ 读取任意目录下的任意文件字节
```

项目里其他路径入口（`resolve_run_dir_from_payload:794-804`、`resolve_history_report_dir`、`resolve_static_path`、`handle_candidate_thumbnail`）都做了白名单，唯独这两个漏掉。

**改法**：抽一个 `confine_to_allowed_roots(path, roots)` 辅助函数，对 `md_path` 施加与 `resolve_run_dir_from_payload` 一致的约束（必须落在 `ROOT_DIR` 或配置的 output 目录下），并追加两条断言：父目录名匹配 `^\d{8}_\d{6}$`、后缀必须是 `.md`。更彻底的做法是把前端 `web/js/preview.js:30` 的 `md_path` 换成 `run_id`，服务端统一走 `core/history.py:227` 的 `resolve_history_report_dir`。成本：small。

### 1.2 全部 API 无 Origin/Host 校验，可 CSRF、可 DNS rebinding

`do_GET`（`server/handlers.py:88-132`）与 `do_POST`（`:134-235`）在路由前没有任何 Host、Origin、Referer、Sec-Fetch-Site 校验，也没有 `do_OPTIONS`。`parse_json_body`（`server/responses.py:47-53`）只读 `Content-Length`，不校验 `Content-Type`——意味着 `text/plain` 的「简单请求」可以绕过 CORS 预检直接产生副作用：

```js
fetch('http://127.0.0.1:8765/api/output/cleanup', {
  method: 'POST', mode: 'no-cors',
  headers: {'Content-Type': 'text/plain'},
  body: '{"confirm":true,"keep_recent":0,"include_warnings":true,"include_failed":true}'
})
```

这一条就会删掉 output 下的运行目录（`handlers.py:487-499` → `core/output_cleanup.py:175-192`）。同类可达接口还有 `/api/history/remove`（删真实目录）、`/api/clear-config`（重置配置）、`/api/config`（覆盖已存 Cookie 与 output_dir）、`/api/cookie/edge-debug`（拉起调试浏览器）。

而 `handle_cookie_auto`（`:588-609`）会把真实微博 Cookie 写进响应体——一旦 DNS rebinding 成功使攻击者页面与 `127.0.0.1:8765` 同源，Cookie 与 1.1 的任意文件内容都能被直接读走。

**改法**：三步，都在标准库范围内，不引入框架。

1. `do_GET`/`do_POST` 最前面加 `_reject_unless_local(self)`：Host 头必须 ∈ `{127.0.0.1:port, localhost:port, [::1]:port}`，否则 403。
2. POST 额外要求 Origin 缺失或等于本机 origin、`Sec-Fetch-Site` ∈ `{same-origin, none}`、`Content-Type` 以 `application/json` 开头。
3. `app.py` 启动时用 `secrets.token_urlsafe(32)` 生成会话 token 注入 `web/index.html`，`web/js/api.js` 统一加 `X-Weibo-Stats-Token` 头，服务端比对。

成本：medium。这是本地服务的标准加固，不涉及公网部署，不违反「只运行在 127.0.0.1」的定位。

### 1.3 `GET /api/defaults` 明文返回完整 Cookie

`app_defaults()` 先把 cookie 置空（`core/config.py:374`），随后 `defaults.update({k: v for k, v in saved.items() if v})`（`:394`）又把真实 cookie 覆盖回去。同一份配置在 `get_presets_payload()` 里是被刻意 `pop` 掉、只保留 `has_cookie`/`cookie_length` 的（`:457-461`）——说明脱敏意图存在，只是这条路径漏了。

**改法**：与 `/api/presets` 对齐，`app_defaults()` 固定 `cookie: ""`，额外返回 `has_cookie`/`cookie_length`；前端 `#cookie` textarea 用 placeholder 显示「已保存 Cookie（长度 N），留空表示沿用」；`web/js/form.js` 提交时若用户未改动就不传 cookie 字段，服务端在 payload cookie 为空时回落读已存配置。Cookie 从此只进不出。成本：medium。

### 1.4 `/api/open-result-dir` 的 `run_dir` 无白名单

`handle_open_result_dir`（`:574-586`）把 payload 的 `run_dir` 直接 `Path()` 化，只判断 `exists()/is_dir()` 就交给 `os.startfile`（`:848-852`）。同文件的 `handle_history_open_dir`（`:392-396`）走的是 `resolve_history_report_dir` 白名单，说明约束是有意设计的，这个入口漏了。当前 `is_dir()` 挡住了「startfile 执行任意文件」的最坏情况，但这是隐式保护，没有注释也没有测试——将来若为支持「打开单个报告文件」放宽判断，就直接变成任意文件执行。

**改法**：改用 `resolve_run_dir_from_payload`，并在 `open_local_path` 内保留 `if not path.is_dir(): raise ValueError("只允许打开目录")` 作为显式不变量。成本：small。

### 1.5 `resolve_run_dir_from_payload` 白名单过宽

`allowed_roots = [ROOT_DIR.resolve(), configured_output]`（`:801`）只做 `is_relative_to` 判断，无目录名格式校验。而 `/api/reexport` 会往 `run_dir` 里写 `weekly_report.md`、`weibo_posts.xlsx`、`manifest.json` 等固定名文件（`export/reexport.py:67-79`）。也就是说 `run_dir="web"` 或 `run_dir="core"` 在白名单上合法，目前只是因为 `CacheStore` 找不到对应 cache 才失败——这是偶然安全，不是设计安全。

**改法**：返回前追加断言：`path.name` 匹配 `^\d{8}_\d{6}$`，且 `path.parent` 等于 configured_output 或 `ROOT_DIR/"output"`。把 `core/job.py:52` 的 `RUN_DIR_RE` 提到 `core/paths.py` 供 handlers、job、output_cleanup 三处共用。成本：small。

### 1.6 请求体无大小上限 + 缺基础安全头 + 异常文本回传

三条小修补，一并处理：

- `parse_json_body` 按 `Content-Length` 一次性 `read()`，无上限（`server/responses.py:47-53`）。声明 `Content-Length: 4294967296` 的 POST 会让工作线程持续分配内存。加 `MAX_BODY_BYTES = 2 * 1024 * 1024`，超限抛 `ValueError`（会被 `handlers.py:232` 转成 400）。
- `send_bytes`（`server/responses.py:56-67`）只发三个头。补 `X-Content-Type-Options: nosniff`（`/api/report-asset` 服务的是从微博下载的、按后缀猜类型的用户可控字节）、`Referrer-Policy: no-referrer`（预览加载微博远程图时会把含 `md_path`/`run_id` 的本地 URL 作为 Referer 发出去）、HTML 响应追加 CSP。
- `handle_unknown_error`（`:661`）把 `f"{type(err).__name__}: {err}"` 当 suggestion 返回；`core/job.py:979-984` 也把同样的字符串写进 `job.error` 经 `/api/status` 渲染到页面。Windows 下 `PermissionError` 的 `str()` 通常含 `C:\Users\<真实用户名>\...`，用户截图求助时就把本机路径一起发出去了。改为：完整信息只 `console_log` 到本地终端，响应只给固定中文提示 + 异常类型名。

成本：均为 small。

### 1.7 附带：`--host` 无非回环护栏

`app.py:14` 的 `--host` 是自由字符串，`python app.py --host 0.0.0.0` 会在零鉴权前提下把整套 API 暴露给局域网。CLAUDE.md 写了「只建议运行在 127.0.0.1」，但代码层面没有任何护栏。

**改法**：默认不变，仅加护栏——`ipaddress.ip_address(args.host).is_loopback` 为假时要求同时传 `--allow-remote`，否则退出并打印中文说明；即使传了也打一条醒目告警。这与 1.2 的 Host 头校验互补：Host 校验挡浏览器侧 rebinding，绑定校验挡误配置。成本：small。

---

## 批次二：仓库卫生与 `frontend/` 处置（P0，30 分钟）

成本以分钟计，防的是「Cookie 备份文件进 git 历史」这种一旦发生就永久不可逆的事故。

### 2.1 含 Cookie 的配置备份文件未被 `.gitignore` 覆盖

`clear_config('all')` 会把完整配置（`global.cookie` 是真实登录态）`copy2` 到 `weibo_stats_config.backup.json`（`core/config.py:217-218`）；`_backup_broken_config` 复制到 `weibo_stats_config.broken.json`（`:601-608`）。而 `.gitignore:16-18` 只有 `weibo_stats_config.json`、`weibo_stats_history.json`、`weibo_stats_history.broken.json`——实测 `git check-ignore` 对这两个备份文件返回未忽略。一次 `git add -A` 就把真实 Cookie 提交进仓库。

**改法**：`.gitignore` 的 `weibo_stats_config.json` 改为加一行 `weibo_stats_config.*.json`；备份前先把 `global.cookie` 置空再写盘；补一条测试，对 `core/config.py` 里所有 `with_name(...)` 产生的文件名调 `git check-ignore` 断言 returncode 为 0，这样以后新增备份文件名会立刻被抓到。

### 2.2 `frontend/` 是零源码的废弃脚手架，建议整体删除

实测：`frontend/src/{components,hooks,lib,pages,styles}` 与 `frontend/public` **全部为空目录**（文件数 0），`node_modules` 有 116 个顶层包共 **159 MB**，而根目录**连 `package.json` 都没有**——即使想恢复这个实验也无法复现安装。它没有任何可保留的代码资产，继续留着有三个坏处：与 CLAUDE.md「无前端构建链」约束长期矛盾、`git status` 永远有未跟踪噪音、159 MB 无谓占盘。

**改法**：直接删除整个 `frontend/`（删除前请确认这不是你正在起步的新工作）。删除后 `.gitignore` 仍补 `node_modules/` 通配作为兜底。

### 2.3 `.gitignore` 补 `debug/`、`.vscode/`、`node_modules/`

三者都存在于工作区且实测未被忽略。`debug/` 当前为空，但目录名暗示它会用来放抓取现场的原始 HTML/JSON，那类文件极可能含真实帖子与请求头。

审计确认的好消息：`git ls-files` 里**没有任何敏感文件被跟踪**，config/history/cache/output 的忽略是完整的，`tests/fixtures` 有专项测试守护。上述三条是仅存的 git 卫生缺口。

### 2.4 表情缓存的 vendor 决策

`assets/weibo_emoticons` 下 420 个 png/gif（约 5 MB）全部被 git 跟踪，但 CLAUDE.md 把它定位为「工具级共享缓存」（可用环境变量覆盖、导出时会增量补齐）。后果是用户每次任务触发新表情下载后 `git status` 就出现未暂存变更。这里需要一个显式决策，因为这批文件让发布 zip 开箱即含离线表情（`scripts/make_release_zip.bat:24` 会拷贝 `assets/`）：

- **(a) 承认为有意 vendor 的静态资源**（推荐，改动最小）：在 `docs/DEVELOPMENT.md` 注明「表情资源随仓库分发，增量下载的新文件需手动决定是否提交」，`.gitattributes` 标 binary。
- **(b) 视为纯缓存**：`git rm -r --cached assets/weibo_emoticons` + `.gitignore` 追加，发布脚本保留拷贝逻辑以维持离线开箱体验。

无论选哪个，现状「半缓存半资产」是最差的。

---

## 批次三：数据不丢失（P1）

### 3.1 导出阶段任何失败都连坐删除 cache（最伤用户信任的一条）

`_run()` 对 `JobCancelled`/`CrawlError`/任意异常统一调用 `_cleanup_incomplete_artifacts`（`core/job.py:971-984`），它会删除整个 run_dir **和项目根 `cache/<run_id>/`**（`:1094-1128`）。唯一豁免条件是 run_dir 下存在 `status` 为 completed/reexported 的 `manifest.json`（`:1147-1157`），而 manifest 是流程最后一步才写（`:944-945`）。

于是这个高频场景成立：用户开着上次的 `weibo_posts.xlsx`，导出时 `workbook.save()` 抛 `PermissionError` → 落入通用 except → 已完成抓取、评论分析、人工筛选、图片下载的全部数据被 `shutil.rmtree` 删除。此时 cache 中其实已有满足 reexport 最低要求的 `run_config.json` + `selected_posts.json` + `posts_scored.json`（筛选提交时已写入 `:783`），却一并没了，用户只能对微博重新发起完整抓取——既浪费时间又增加触发风控的风险。

对比 `export/reexport.py:135-138` 已把 `PermissionError` 转成中文提示且不删数据——主流程反而是破坏性的。取消（`JobCancelled`）时删除是合理的，失败时删除 cache 与整个 reexport 离线恢复设计直接矛盾。

**改法**（三选一，建议 1+2）：

1. 每个导出器包一层 try/except，`PermissionError`/`OSError` 记入 warnings 并继续其余导出（`core/job.py:839-922` 目前 9 个导出器串行调用，无任何单项隔离）。
2. 全部导出结束后即使有失败也写出 manifest（status 置 `export_failed` 或带 warnings 的 completed），使清理规则不再判定目录「未完成」。
3. 最低限度：except 分支中判断 `self.stage` 已达 export 时跳过 `_cleanup_incomplete_artifacts`，提示用户用 `/api/reexport` 离线补导。

同步更新 `core/recovery.py:46-51` 的 file_locked 建议为「关闭占用文件后用历史任务重新生成」，并补 `tests/integration/test_export_bundle.py` 的「xlsx 被锁定」用例。成本：medium。

### 3.2 reexport 用单个 try 包裹全部导出器

`reexport_from_cache` 把 excel/csv/summary/weibo_body/docx/markdown/long_images 七类导出放在同一个 try 块（`export/reexport.py:92-138`），任一抛 `PermissionError` 就中断整个流程，既不生成后续格式也不更新 manifest。用户只是开着 xlsx，想重新生成 Markdown 也会失败。

**改法**：每个 export 分支独立 try/except，失败追加 warning 继续；全部结束后仍写 manifest，返回值带 `failed_export_types`；仅当请求的类型全部失败才抛 `ReexportError`。成本：medium。

### 3.3 配置与历史 JSON 写入非原子且无并发保护

`save_config`（`core/config.py:174`）和 `save_history`（`core/history.py:38`）直接 `write_text` 整体覆盖，进程写一半崩溃会留下截断 JSON；下次 `load_config` 走异常分支备份坏文件并**静默回退到默认配置**（`core/config.py:109-111`）——用户的 Cookie 和全部预设就这么没了。

同时服务是 `ThreadingHTTPServer`（`server/http_server.py:24`），`save_user_config`（`core/config.py:178-204`）和 `add_history_item_from_manifest`（`core/history.py:42-49`）都是无锁的 load→改→save；任务完成时工作线程写历史（`core/job.py:947`）与 handler 线程（`server/handlers.py:247,256`）并发，是经典的丢失更新竞态。

项目里其实已有现成的正确实现——`core/cache.py:230-239` 的 `_atomic_write_json`（临时文件 + replace），只是配置/历史没复用。

**改法**：把 `_atomic_write_json` 提为通用工具（`core/atomic_io.py`），config/history 改用它；两个模块各加一个模块级 `threading.Lock` 包住所有 load→改→save 序列。补一条并发测试。成本：small。

### 3.4 Ctrl+C 退出时运行中任务被硬杀，绕过全部清理

`CrawlJob` 线程以 `daemon=True` 启动（`core/job.py:248`），而 `app.py:27-32` 收到 `KeyboardInterrupt` 后只做 `server_close()` 就退出——daemon 线程随进程立即消失，`finally`/`except` 都不执行。意味着 v0.11.1 刚做的「取消/失败自动清理未完成 output 与 cache」在进程级退出场景下完全不生效：留下无 manifest 的 `output/<run_id>/` 与 `cache/<run_id>/`，若恰好死在 `write_stage` 的 JSON 写入途中还会留下截断文件，影响后续 reexport 与清理判定。

**改法**：`KeyboardInterrupt` 分支调用 `JobManager` 的 `request_cancel` 并 `thread.join(timeout=10)` 再退出，超时才放弃；`console_log` 提示「正在等待当前任务安全停止」。成本：small。

### 3.5 磁盘只进不出：清理不联动删除根 cache

三条证据链：`cleanup_output` 确认删除时只 `rmtree` output 下的 run_dir（`core/output_cleanup.py:186-191`），对应的根 `cache/<run_id>`（含候选缩略图、每帖评论 JSON、全部阶段缓存，单次任务可达数十 MB）原样保留；历史删除同样只删 report_dir（`server/handlers.py:370`）；清理预览展示的 size 只统计 output（`core/output_cleanup.py:222-223`），用户看到的「可释放空间」系统性偏小。被删过 output 的任务缓存从此成为无入口触达的孤儿目录。

**实测项目根 `cache/` 当前有 187 个子目录**（其中 160 个是测试泄漏的 `tmp*`，见 5.1）。

**改法**：`cleanup_output` 与 `handle_history_remove` 删除 output 后同步删除 `CacheStore(run_dir).project_cache_dir`——仅当它位于 `ROOT_DIR/cache` 下且目录名匹配 `RUN_DIR_RE` 时；`_summarize_run_dir` 把 cache 尺寸并入统计；output summary 增加「孤儿 cache 目录」计数，清理预览可勾选一并清除。成本：medium。

### 3.6 `cleanup_output` 单目录删除失败中断整批

`shutil.rmtree(..., ignore_errors=False)` 无 per-dir 异常处理（`core/output_cleanup.py:186-192`），Windows 下任一目录有文件被占用就抛 `OSError` 中断循环：排在前面的已删、后面的没删，异常冒泡后用户只看到一条笼统错误，不知道实际删了哪些。对照 `core/job.py:1189-1199` 的 `_delete_dir` 是逐目录捕获并汇总 errors 的。

**改法**：循环体内 try/except，失败目录记入 errors 继续，响应返回 `deleted_dirs` 与 `errors` 两个列表，message 汇总「已删除 N 个，M 个失败（文件可能被占用）」。成本：small。

---

## 批次四：抓取健壮性与报告质量（P1）

这组决定任务成功率与报告质量的下限，是用户可感知的最大体验问题。

### 4.1 翻页与评论请求完全没有重试

`_fetch_super_index_page`（`crawler.py:307-319`）与 `_fetch_chaohua_page`（`:321-345`）都是单次 `session.get`，无重试。翻到第 40 页时一次瞬时 `ConnectionError` 会一路抛到 `job._run()` 的兜底 except，任务 failed 并自动清理已抓取成果（叠加 3.1 后果更严重）。

而 `modules/crawler_client.py:223-243` 的 `WeiboClient._request` **已经实现了完善的重试 + 退避 + 访客识别 + 401/403 分类**，却只被 Cookie 检测使用，主抓取链路完全没复用。

**改法**：给 `WeiboSuperTopicCrawler` 增加 `_request(method, url, **kwargs)`，移植 `crawler_client.py:223-243` 的 2 次重试 + `1.5s * attempt` 退避；四个请求点统一走它；超时统一为 `(5, 20)` 连接/读取分离（当前 `crawler.py` 全是标量 `timeout=20`，与 `WeiboClient` 不一致）。成本：medium。

### 4.2 并发请求零限速，失败被裸 except 吞掉

`pause_seconds` 只在超话翻页循环 sleep 一次（`crawler.py:269`）。而评论精查阶段默认 `comment_workers=6` 线程并发、每帖最多 8 页、页间无任何 sleep（`:735-756`）；正文补全 `text_workers=6` 线程、每帖连发 3~4 个接口。**最重的请求阶段反而完全不受用户配置的限速约束**，短时间可打出数百请求，反爬风险最高。

更麻烦的是 `_enrich_score_fields` 用裸 `except Exception` 吞掉 `_analyze_comments` 的所有异常且不打日志（`:568-572`）——评论接口返回访客验证页时 `resp.json()` 抛 `ValueError` 也被吞掉。结果是 Cookie 中途失效或被限流后，**任务照常「成功」完成，但所有帖子 `author_replies=0`、无热评，用户拿到降级报告却毫无感知**。`core/errors.py:36` 定义的 `RateLimitedError` 在全仓库没有任何 raise 点。

**改法**：

1. 实现跨线程共享的最小间隔限速器（`threading.Lock` + 上次请求时间戳），由 `pause_seconds` 驱动，注入评论精查、正文补全、图片下载的所有请求点。
2. `_enrich_score_fields` 的 except 至少 `self._log` 一条 warning 并累计失败计数，失败率超阈值（如 30%）时抛 `RateLimitedError`/`CookieInvalidError`，让 `core/recovery.py` 的分类恢复建议真正生效。
3. `_analyze_comments` 对 `resp.text` 做访客检测，区分「无更多评论」与「被拦截」。

成本：medium。

### 4.3 访客检测是弱化的硬编码字符串，且抛错类型不对

`crawler.py:315-316` 只匹配 `'<title>Sina Visitor System</title>'` 单一标记，微博改标题即失效；而 `modules/crawler_client.py:246-257` 的 `looks_like_weibo_visitor` 有 5 个标记的完整检测。且命中后抛的是 `CrawlError` 而非 `VisitorSystemError`，`core/recovery.py` 按错误类型生成的恢复建议在主抓取失败场景拿不到准确类型。

**改法**：改调 `looks_like_weibo_visitor`，命中时抛 `VisitorSystemError`（已是 `WeiboStatsError` 子类，映射路径已存在）。成本：small。

### 4.4 每个帖子新建一个 Session，连接池完全失效

`_enrich_score_fields_with_private_session`（`crawler.py:523-533`）、`_hydrate_one_post_with_private_session`（`:861-866`）、`_download_one_post`（`:1342-1345`）都是每帖新建 Session 用完即关。45 个帖子就是 45 次 TCP+TLS 握手起步，也增加了服务端可见的连接指纹异常。

**改法**：用 `threading.local()` 缓存 per-thread Session——线程池最多 12 个线程只需要 12 个 Session，executor shutdown 后统一关闭。成本：small。

### 4.5 图片下载单图失败无重试且失败明细静默丢弃

主链路用的是 `crawler.py:1287-1423` 的实现，单图失败走 `except Exception: continue`（`:1332-1337`），不重试、不记录失败 URL，失败数只能靠 `job.py:800-801` 用「期望数 - 实际数」倒推，manifest 里给不出具体哪张图、什么原因失败。

而 `modules/images/downloader.py:63-75` 是另一套结构更清晰、返回逐图 `{url, ok, error}` 的实现，但无并发、无 Cookie 头、无取消支持，主链路完全没用，只被测试引用——**两套代码都要维护，行为还不一致**。

**改法**：以 `modules/images/downloader.py` 为目标合并——补 Cookie 头、`ThreadPoolExecutor` 并发与 `cancel_checker`（参照 `candidate_thumbnails.py:76-85` 的现成模式），单图失败增加 1 次重试，返回逐图结果由 job 写入 manifest 的 `failed_images`；`crawler.py` 的版本收缩为转发壳。成本：medium。

### 4.6 未知 `[xxx]` 文本被强制替换成默认颜文字，破坏正文

`replace_weibo_emoticons` 用正则匹配任意 `[1-24字符]` token，查表未命中时不保留原文，而是一律替换为 `(｡･ω･｡)`（`export/report_helpers.py:172` 的 `mapping.get(key, ...)`）。帖子里的 `[公告]`、`[抽奖规则]`、`[视频]` 会在 DOCX/Markdown/weibo_body 中被替换成颜文字——**内容失真**。对照长图渲染 `renderer.py:130-134` 对未命中表情是原样保留的，两者行为矛盾。另外 `weibo_body_exporter.py:90` 对用户昵称也走 `clean_report_text`，含方括号的昵称同样被改写。

**改法**：`mapping.get(key)` 未命中返回 `match.group(0)` 原样保留；昵称清理改用 `normalize_weibo_text`。补一条「`[公告]` 不被替换」的断言。成本：small。

### 4.7 汇总帖过滤关键词过宽，误杀带链接的正常热帖

`_is_summary_post`（`modules/crawler_filters.py:28-46`）只要正文命中「网页链接」「整理了」「合集」「汇总」「周报」「索引」任一模式就硬排除。**微博会把外链渲染成字面文本「网页链接」**，因此任何附带链接的普通高互动帖都会被剔除；「整理了」「周报」在日常语境也常见。被误杀的帖子不会进入 20 条候选（`core/job.py:704`），用户在人工筛选阶段无法救回，且没有任何日志说明。

**改法**：「网页链接」「整理了」不再单独成立，要求与「合集/汇总/索引/导航」同时出现或出现在前 30 字内；对「互动量进前 20 但被过滤」的帖子输出 warning 日志，让用户能发现误杀。成本：small。

---

## 批次五：测试隔离、安全回归与 CI（P1）

必须先做隔离（否则 CI 跑一次污染一次），再把批次一的安全不变量用穿越用例固化，最后用 CI 锁住前四批的改动。三条都是 small，合并为一个 PR。

### 5.1 测试污染真实 `cache/` 与 `output/`，已泄漏 160 个临时目录

`tests/test_cache_status.py:12-14` 构造 `CacheStore(Path(tmp))` 时既没传 `cache_root` 也没设 `WEIBO_STATS_CACHE_ROOT`，写入落到真实项目根 `cache/`。**实测项目 `cache/` 下已积累 160 个 `tmp*` 泄漏目录**，外加 `20260512_020202`、`20260511_010101`、`20260512_010101` 等 fixture 残留。`tests/test_history_api_contract.py:26-31` 和 `tests/integration/test_api_contract.py:110-112` 还直接在仓库真实 `output/` 里建目录。

这违反了 CLAUDE.md 和 `docs/DEVELOPMENT.md` 自己规定的「测试不写入用户真实 output」，且泄漏目录会被 output 清理/历史扫描当成真实数据干扰用户。`tests/helpers.py:36-47` 其实已有正确的 `make_temp_run_dir()`，只是这些测试没用。

**改法**：`tests/__init__.py` 加全局兜底（未设 `WEIBO_STATS_CACHE_ROOT` 时指向 `tempfile.mkdtemp()` 并注册 atexit 清理）；三个测试改用 `make_temp_run_dir()` 或显式传 `cache_root`；手工清理现有泄漏目录。成本：small。

### 5.2 路径穿越无 HTTP 层回归测试

`resolve_report_asset_path`、`resolve_static_path`、`resolve_run_dir_from_payload` 是本工具的核心安全边界，目前只有 `core/paths.safe_resolve` 有一个纯函数用例（`tests/test_paths.py:11-15`），HTTP 层没有任何 `../`、`..%2f`、绝对路径、Windows 盘符形式的穿越用例。

**改法**：复用 `tests/integration/test_api_contract.py` 已有的本地 server 基建，对 `/api/report-asset?path=../weibo_stats_config.json`、`/api/candidate-thumbnail?run_id=..`、静态路由 `/../app.py`、`C:/Windows/win.ini` 等断言 4xx 且响应体不含目标内容。每个用例约 5 行，收益是把最重要的安全不变量永久固化。成本：small。

### 5.3 `core/job.py` 任务编排核心零测试

`core/job.py` 1239 行，是 CLAUDE.md 明确标注的「任务编排最核心文件」，但 `grep` 全 tests 目录，`/api/start`、`/api/select`、`/api/cancel-job` 三个端点**零引用**。`_run()` 的完整状态机、`submit_selection()` 的数量校验、`JobManager` 的单任务约束、`snapshot()` 的 `/api/status` 字段契约（前端四个 controller 都依赖）都没有回归保护——而这正是项目改动最频繁的区域。

**改法**：参照 `tests/test_chaohua_api_fallback.py:41-50` 已有的 `NoopCrawler` 模式，新增 `tests/test_job_run.py`：注入 `FakeCrawler`（返回 fixture 帖子，不发网络请求），配合 `make_temp_run_dir()` 离线跑通 `_run()` 到 `awaiting_selection`，断言 snapshot 契约字段齐全、`submit_selection` 数量校验、`JobManager` 拒绝并发任务。可直接用现有 `fixtures/sample_posts_*.json` 驱动。成本：medium。

### 5.4 最小 CI

仓库无 `.github/` 目录。而测试套件是理想的 CI 负载：实测 154 个用例、8.5 秒全绿、完全离线、Playwright 缺失时优雅降级。当前发布质量完全依赖 `docs/RELEASE_CHECKLIST.md` 的人工勾选。

**改法**：约 25 行的 `.github/workflows/ci.yml`——`on: [push, pull_request]`，矩阵 `windows-latest × Python 3.10/3.13`，步骤为 setup-python（带 pip cache）→ `pip install -r requirements.txt` → `python -m unittest discover -s tests`。不需要 `playwright install chromium`。可选加一个 `ubuntu-latest` job 提早暴露路径分隔符/编码问题。成本：small。

### 5.5 引入 ruff（+ 渐进 mypy）

项目没有 `pyproject.toml`/`ruff.toml`/`mypy.ini` 中的任何一个，代码风格约束只存在于 CLAUDE.md 的文字描述里。有意思的是 `scripts/clean_generated.bat:10-11` 已经在清理 `.ruff_cache`——说明曾有引入意图但从未落地。代码本身已大量使用 `from __future__ import annotations` 和类型注解，边际成本很低，而 10400 行后端代码没有静态检查。

**改法**：最小 `pyproject.toml`——`[tool.ruff]` 配 `lint.select = ["E","F","I","UP"]`、exclude output/cache/dist；`[tool.mypy]` 先只对 `core/` 和 `server/` 开 `check_untyped_defs`。`ruff check` 加进 5.4 的 CI。pre-commit 对单机 Windows 开发者价值有限，可暂缓。成本：small。

### 5.6 版本号三处硬编码 + 依赖未锁 + smoke_test 输出误导

- 版本号 `0.11.1` 同时硬编码在 `core/version.py:3`、`scripts/make_release_zip.bat:6`、`docs/RELEASE_CHECKLIST.md:3`，而检查清单只要求核对前者与 CHANGELOG，**没覆盖发布脚本**。一旦忘改就会打出文件名与内容版本不一致的 zip。改法：`make_release_zip.bat` 从 `core/version.py` 读取（注意该脚本目前不调用 python，需先加探测）。
- `requirements.txt:1-8` 全部只有 `>=` 下界无锁文件。对双击 `点我启动.bat` 的普通用户，某依赖发布不兼容大版本就会安装即坏。改法：`pip freeze` 生成 `requirements.lock.txt` 随发布包分发。
- `playwright` 是最重的依赖（轮子 ~40 MB + 浏览器 ~150 MB），但只服务长图 JPG 一个功能，且已是函数内延迟导入 + 缺失时优雅降级（`exporter.py:76-89`）。改法：移到 `requirements-image.txt`，可把普通用户首次安装体积减少约一半。
- `scripts/smoke_test.bat:10` 的 `[print('OK', name) or importlib.import_module(name) ...]` 求值顺序是先 print 后 import，导致失败时最后一行恰是失败模块的「OK core.job」，排障时严重误导。改法：改成普通循环。

成本：均为 small。

---

## 批次六：性能（P2）

### 6.1 DOCX 分卷是 O(n²) 磁盘写放大

`export_weekly_report_docx` 为判断 10 MB 分卷边界，**每追加一条帖子就从零重建整个文档**（重新读取并嵌入之前所有帖子的全部图片），save 到 `_trial` 文件测 size 再删除（`export/docx_exporter.py:72-84`）；分卷落盘时再完整重建一次（`:86-96`），收尾又一次（`:101-111`）。15 条帖子意味着 16~20 次完整文档构建与保存，单次导出瞬时磁盘写入可达上百 MB。主流程和 reexport 各执行一次，叠加 `weekly_report_sum.docx` 后更明显。

**改法**：DOCX 体积几乎由图片字节数决定（图片在 zip 中基本不再压缩），改为增量估算——累计「固定文本开销 + 每帖图片 `st_size` 之和」，超过 `limit * 0.95` 时才做一次真实 save 校验。可把试写从 O(n) 次全量 save 降到每卷 1~2 次。成本：medium。

### 6.2 长图导出默认全量下载微博表情库

`ImageReportConfig.download_all_emoticons` 默认 `True`（`models.py:20`），`export_image_report` 在非 reexport 场景调 `ensure_weibo_emoticon_assets(download_all=True)`，`weibo_emoticons.py:67` 会把 requested 置为**整个索引**（数百到上千个表情），用 8 线程在导出阶段批量下载。首次运行任务时导出阶段被这批下载显著拖慢，而实际渲染只需要命中的少量表情。

**改法**：默认改 `False`，只按 `used_names` 增量补齐（exporter 已传该参数）；表情下载失败的 warnings 做聚合避免刷屏。成本：small。

### 6.3 静态资源整文件读入内存 + 一律 no-store

`send_static_file` 用 `read_bytes()` 整读（`server/responses.py:42-44`），长图 JPG 可能数 MB。`send_bytes:60` 对**所有**响应恒定写 `Cache-Control: no-store`，连 css/js/图片/缩略图都禁缓存，也没有 ETag/Last-Modified/304。

**改法**：静态文件改 `shutil.copyfileobj` 流式写出；`web/` 资源与运行目录图片设置 Last-Modified/ETag 支持 304；仅 `/api/*` 保留 no-store。成本：medium。

### 6.4 HTTP/1.0 无 keep-alive

`AppRequestHandler` 只设了 `server_version`，没设 `protocol_version`（`server/handlers.py:86`），沿用 `BaseHTTPRequestHandler` 默认的 HTTP/1.0——响应后立即关闭连接。前端每秒轮询一次，加上候选阶段最多 60 张缩略图和静态资源，每个请求都完整走一遍 TCP 建连 + 新起线程。

修复条件已具备：`send_bytes:61` 对所有响应都写了 `Content-Length`（keep-alive 前提）。**加一行 `protocol_version = "HTTP/1.1"` 即可**。成本：一行。

### 6.5 `/api/status` 每秒返回全量快照

`snapshot()` 每次序列化最近 300 条 logs + 300 条 events + 全部 20 个候选（含 `content_full` 全文），并在**持锁状态下**做 `Path.exists` 文件系统调用和 recovery 建议构建（`core/job.py:365-390`）；`JobEvent.to_dict`（`core/events.py:49`）每次再跑一遍 `sanitize_event_payload`，而 payload 在事件构造时已脱敏过（`job.py:341`）——等于每秒对 300 个事件做重复递归清洗。logs/events 超限裁剪还用 list 切片重建。

**改法**：去掉 `to_dict` 的重复 sanitize；`/api/status` 支持 `since` 参数只返回增量；candidates 仅在 `awaiting_selection` 时返回；logs/events 改 `collections.deque(maxlen=...)`；`Path.exists` 移出锁。成本：medium。

### 6.6 前端每次轮询全量重渲染四个区块

轮询节奏本身设计合理（运行中 1 s、等待筛选 2.5 s、页面隐藏 5 s、失败退避、结束停表），但没有任何变更检测：`renderJob` 无条件调用 progress/logs/candidates/cache 四个 render（`web/js/task.js:30-34`），其中 `logs.js:54-62` 用 `innerHTML` 全量重建最多 300 行日志——每秒重建 300 个 DOM 节点并**销毁用户的文本选区**。

候选列表更糟：`awaiting_selection` 期间每 2.5 s 全量重建 20 张卡片（含缩略图 img），**勾选一个 checkbox 或点一次「展开全文」也触发整表重建**（`candidates.js:163-186`），键盘用户焦点每 2.5 秒被强制丢弃，无法用 Tab 连续操作。而候选数据在等待筛选期间服务端根本不会变。

**改法**：`renderJob` 用 `job.id + status + updated_at + events.length` 做缓存键，相同则直接 return；`logs.js` 记录已渲染条数只 append 新增行；候选勾选改为对目标卡片打补丁而非整表重建（`progress.js:79-106` 的 keyed 增量更新已示范该模式）。成本：small~medium。

### 6.7 历史列表初始加载走全量磁盘扫描

`historyController.load()` 与 `scan()` 发送**完全相同**的 `POST /api/history/scan`（`web/js/history.js:7-38`），意味着每次页面打开、每次任务结束、每次删除后都触发后端遍历 output 下所有运行目录并逐个读 manifest；而 `GET /api/history` 提供的轻量索引接口前端无人调用。历史积累到几十上百个目录后，每次页面加载的扫描延迟线性增长。

**改法**：`load()` 改为 `GET /api/history` 读索引，仅在用户显式点「扫描 output」时才走 scan。成本：small。

### 6.8 编辑 Cookie 的每次输入都触发后端识别请求

`events.js:300-302` 对 superTopic、cookie、windowStart、windowEnd 四个字段的 input 事件都调 `scheduleRefresh()`（520 ms 防抖），refresh 会把**完整表单（含整段 Cookie）**POST 给 `/api/topic-preview`，而该接口可能向微博发起真实识别请求。用户粘贴/编辑一大段 Cookie 的过程中会连续触发多次——浪费且有触发风控的风险。而 windowStart/windowEnd 变化只影响期数计算，根本不需要重新识别超话名。

**改法**：superTopic 保持现状；cookie 改为 blur 后刷新一次；时间窗口变化用已缓存的 `lastTopicName` 前端重算标题（`topic_preview.js:86-94` 已具备该能力），不发请求。成本：small。

### 6.9 其余性能项

- `output_summary` 对每个运行目录做 **3 次**全树 rglob（`core/output_cleanup.py:20` 一次 + `:222-223` 两次）。改为局部变量复用，约 5 行。
- 粒子背景用 `top` 属性做下落动画（`web/css/base.css:94-106`），`top` 是布局属性无法合成器加速，页面整个使用期间每帧都做布局计算；`updateRepel`（`particles.js:40-55`）每帧对 130 个粒子先读 `getBoundingClientRect` 再写 CSS 变量，读写交错构成典型 layout thrashing。改为纯 transform + 一次性计算坐标。
- 八类导出全串行（`core/job.py:838-922`）。优先做 6.1，若仍需提速可用 2 个 worker 并行「DOCX 链」与「长图链」（一个 CPU+磁盘、一个等浏览器进程），其余轻量导出保持串行。注意 `ExportContext.warnings` 需线程安全。
- `WeiboClient.download_file` 的流式下载被 `_request` 破坏：`_request` 对每个响应无条件访问 `response.text[:200000]` 做访客检测（`crawler_client.py:234`），而 `download_file` 传了 `stream=True`——访问 `.text` 会把整个响应体读入内存使流式失效，且图片二进制无 charset 时触发编码探测。当前主链路未踩坑，但 `modules/images/downloader.py:16-17` 明确支持传入 client，接入即触发。改法：`_request` 增加 `check_visitor` 参数，或仅对 `text/`、`application/json` 响应做检测。

---

## 批次七：可维护性与去重（P2/P3）

### 7.1 进度靠正则解析中文日志（前后端各一套）

后端 `_parse_progress_message`（`core/job.py:538-599`）用六组中文正则从 crawler 的日志字符串反推 stage 和进度；前端 `progress.js:291-348` 的 fallback 分支又硬编码了约 20 处针对后端中文日志的正则。`crawler.py` 里任何文案微调都会让进度条**静默失效且无测试报错**——典型的字符串协议反模式。

项目里已有正确范式：`core/job.py:1047-1064` 的 `_candidate_thumbnail_log` 消费结构化 dict 事件。

**改法**：给 crawler 增加 `progress_event` 回调（`{stage, current, total, message}`），各进度点直接发结构化事件，`_crawler_log` 只负责纯日志；前端确认 `subtasks` 在所有活跃状态恒非空后，把 fallback 收缩为一条通用兜底步骤，删除全部日志正则。成本：medium。

### 7.2 `job.py` 职责过多，且存在同名双实现

`core/job.py` 1239 行混合了至少四类可独立职责：候选序列化（`:103-156`）、图片 manifest 构建（`:159-210`）、导出编排（`:813-950`，9 个导出器顺序调用约 140 行）、失败/取消清理（`:1094-1199`）。更糟的是 `modules/images/manifest.py:8-27` 还有另一个签名和 schema 都不同的 `build_images_manifest`，产线从未使用（只有它自己的测试在用），且其 `write_images_manifest` 还写旧版 `run_dir/cache/` 路径，与项目根 cache 新架构相悖——极易误导后续改动。

**改法**：分三步小步拆分，每步跑全量测试。(1) `build_images_manifest` 及 `count_*` 移入 `modules/images/manifest.py`，删除旧实现，统一 schema；(2) 导出编排抽成 `export/pipeline.py` 的表驱动结构（`[(label, callable, path), ...]` 循环 + 统一 `check_cancelled` 和进度上报）；(3) 清理助手移到 `core/artifact_cleanup.py`。成本：large。

### 7.3 路由改字典分发 + `do_GET` 补异常兜底

`do_GET` 约 11 个分支、`do_POST` 约 29 个分支的线性 `if path == ...`（`server/handlers.py:88-224`）。且 `do_POST` 有完整 5 段 except 链，`do_GET` **一个 try 都没有**——GET handler 抛异常会冒泡到 `socketserver.handle_error`：客户端拿到连接重置（无任何 JSON 错误体），含绝对路径的完整 traceback 打到控制台。可复现：`GET /api/report-preview?md_path=<任意二进制文件>` → `read_text(utf-8)` 抛 `UnicodeDecodeError` → except 分支 `read_text(utf-8-sig)` 二次抛出且无人接管。

**改法**：抽 `_dispatch(path, handler)` 公共方法统一异常兜底，两个方法都改用字典分发表。这样新增 API 只需加一行映射，批次一的 Origin/Host 守卫也只需写一处。成本：medium（与 1.2 合并做更划算）。

### 7.4 `crawler.py` 残留死代码与可迁出纯逻辑

1676 行中约 700 行已是纯转发壳，但仍混着大量无网络依赖的纯函数，另有一批确认无调用的死代码：

- **死代码（零风险删除）**：`_skip_space`/`_find_json_object_end`（`:1016-1044`，是 `weibo_html_parser.py:155-183` 的未使用副本）、`_parse_publish_datetime_with_format`（`:1092`）、`_report_divider_line`（`:1549`）、`_first_text`（`:1664`）。
- **建议迁出**：截断判定族（`:1141-1193`，正文补全质量的核心启发式，目前完全没有独立单测）→ 新建 `modules/text_hydration.py`；详情页 HTML/JSON blob 提取（`:1051-1085`）→ `weibo_html_parser.py`；`_recalibrate_time_weight` 的纯搜索部分（`:625-719`）→ `modules/crawler_scoring.py`。

成本：large（分三步，每步保留旧名转发）。

### 7.5 五组重复实现，需要收敛到单点

| 重复内容 | 位置 | 风险 |
| --- | --- | --- |
| 时间权重公式 | `crawler.py:1131-1138`（可变 strength）与 `crawler_scoring.py:53-59`（硬编码 0.06） | 改一处忘另一处，评分与校准静默发散 |
| 评论解析 | `crawler.py:764-810` 手写 50 行 与 `modules/comments/parser+analyzer`（仅测试引用） | 作者回复判定口径已不同：crawler 版只比对 `user.id` 且每楼封顶 3 次 |
| 期数计算与日期解析 | `weibo_body_exporter.py:12,102-116` 与 `image_report/adapter.py:13,118-147` | 微博正文草稿与长图期数不一致，而两者是同一条微博一起发的 |
| Excel/CSV 列定义 | `crawler.py:86` 与 `excel_columns.py:5-23`、`csv_exporter.py:8-26` | 加列需双改，否则首导与重导的 Excel 列不一致 |
| 多值路径拆分 | `docx_images.py:45-50`、`excel_images.py:51-56`、`reexport.py:363-368` 三份 + `report_helpers.split_multi_values` 第四个变体 | 换行分隔的图片路径在 Markdown 解析不出、Excel 能解析 |

另有互动数解析能力不一致：`weibo_html_parser.parse_count` 只支持「万」，`weibo_chaohua_api._parse_count` 支持「亿/万/逗号」——旧版路径遇到亿级计数会解析成 1。

**改法**：逐一收敛到单点定义 + 旧名转发。每条 small。

### 7.6 首次导出与 reexport 走不同入口，warnings 丢失

主流程 `job.py:839` 的 `export_posts_xlsx` 在 `excel_exporter.py:41-47` 现场构造一次性 `ExportContext`，图片嵌入失败写入的 warnings 随即被丢弃；`job.py:858-864` 的 DOCX 导出不传 ctx，`docx_images.py:28/42` 记录的「图片缺失/插入失败」同样进不了 manifest。而 reexport 传共享 ctx，警告能进 manifest——**同一问题两条链路行为不同**。另外 reexport 的 summary 榜单不传格式化函数（`reexport.py:99-106`），落到 `_fallback_leaderboard_line`，导致重新生成的 `weibo_summary.txt` 质量榜丢失获赞数/热评次数。

**改法**：`job.py` 提前构造 `ExportContext`（现在在 891 行、Excel/DOCX 之后才建），统一改调 `export_excel(ctx)`/`export_docx(ctx)`；把 `crawler._format_leaderboard_line` 迁到 `report_helpers.py` 供两边引用。成本：medium。

### 7.7 前端结构清理

- `main.js:369-388` 给 taskController 注入了 `presetController`、`topicPreviewController`，而 `task.js:2-19` 的解构列表里根本没有这两项——**死注入**，说明依赖清单已与实际漂移。
- `main.js:166-193` 保留了与 `api.js:1-23` 完全重复的 fallback `api()`/`formatApiError()`，`WeiboApi` 恒存在，这段**永不执行**。
- `state.js` 只有 3 行空壳，而 CLAUDE.md 称它承担共享状态；controller 间通信同时存在「构造器回调注入」与「window CustomEvent」两套机制。建议在 state.js 实现一个 20 行的 `on/emit` 事件总线，让它名副其实。
- `web/app.js` 内容是 `import("/js/main.js")` 且**无任何文件引用它**——若未来被误引入，main.js 会被以 module 身份第二次执行，重复绑定全部事件。直接删除。
- `events.js:22-64` 前半段是非可选访问链，后半段又混用 `?.`。一旦 `index.html` 改版漏掉一个前半段的 id，`bind()` 在该行抛 TypeError，**其后全部绑定（含开始任务、取消、日志）一并失效且页面无任何可见报错**。改法：`main.js` 收集完 DOM 后遍历三个对象对 null 值 `console.error`（约 8 行，立即暴露 id 漂移）；`bind()` 按功能域拆分并逐个 try/catch。

成本：均为 small。

### 7.8 `cookie_helper.py` 依赖方向倒置

CLAUDE.md 将其定位为「兼容入口」，但全部 740 行实现都在根模块，而 `modules/cookie_edge_debug.py:19-30` 反过来在函数体内 `import cookie_helper` 的**私有函数** `_try_get_cookie_header_from_cdp`——模块层依赖根层的下划线 API，方向与分层约定相反。同时文件内嵌了完整手写 WebSocket 协议栈（握手/掩码/分帧约 140 行，`:470-611`）与 CDP 编排、browser-cookie3 回退、profile 清理混在一起，`_fetch_json` 直连 urlopen 无注入点，导致 CDP 路径没有任何单元测试。

**改法**：把 `_CdpWebSocket` 与帧编解码迁到 `modules/cookie_cdp_ws.py`（纯协议逻辑，可用内存 socket 单测），顺势消除反向私有依赖；给 CDP 发现函数增加 `fetch_json` 参数使其可用假数据单测。成本：medium。

---

## 批次八：打磨项（P3）

按价值排序，都是 small：

1. **`app_defaults` 用 truthiness 合并，False 被静默丢弃**（`core/config.py:394`）。基础 defaults 没有 `download_images`/`export_types` 键，用户把 `download_images` 设为 False 后 `/api/defaults` 完全缺失该键，前端回退自己的默认值——**用户偏好被静默还原**。未来任何「默认 True、用户关闭」的布尔配置都会踩同一个坑。
2. **日志零持久化**。`console_log` 只 print，任务日志只在内存且截断 1000 条，manifest 不含日志，全仓没有任何代码写 `.log` 文件（`.gitignore:19` 的 `*.log` 规则形同虚设）。用户遇到抓取失败关掉命令行窗口，唯一的现场就全部蒸发。建议：任务进入终态时把完整 logs 经脱敏后写入 `cache/<run_id>/job_log.txt`——与 3.1「保住 cache」互相成就，cache 在、日志在，才谈得上引导用户走 reexport 恢复。
3. **`mask_cookie_for_log()` 是死代码**。CLAUDE.md 把它列为写日志必用的三件套之一，但全仓无任何生产调用点。风险链路真实存在：`cookie_helper.py:183-201` 把 browser_cookie3 的原始异常字符串拼进错误，经 `handlers.py:225-227` 回传前端；`CrawlJob.add_log` 也无正则兜底。建议在 `add_log` 入口加一层 `re.sub(r"(SUB|SUBP|SCF|WBPSESS|ALF|SSOLoginState)=[^;\s\"']+", r"\1=***", ...)`，并给 `sanitize_event_payload` 补值级过滤（现在只按 key 过滤，值里藏 Cookie 是漏的）。
4. **完整 Cookie 被发送到 sinaimg 图片 CDN**（`crawler.py:1302-1306`、`candidate_thumbnails.py:204-216`）。sinaimg 校验的是 Referer 而非 Cookie，向额外域名发送登录凭证是不必要的暴露面。按 host 决定是否附带即可。
5. **历史 reexport 伪造 job 快照与轮询互踩**。`history.js:194-231` 用 `renderJob` 渲染伪造的 `{status:"exporting"}` 对象，被 `task.js:27-29` 记为 `currentRenderedJob`，而 `isActive` 认为 exporting 是活跃状态——用户切换标签页再切回会触发轮询，后端无真实任务时返回 `job=null`，`renderJob(null)` 把进行中的 reexport 进度整个清空。改法：伪造对象加 `local:true` 标记，轮询调度遇到它直接跳过。
6. **日志「清空显示」游标在 300 条滑动窗口下永久失效**。`clearView` 以数组长度为游标（`logs.js:516-524`），日志超 300 条后数组长度恒为 300，`slice(300)` 永远为空——此后该任务所有新日志都不再显示，气泡计数也归零。改法：游标改记最后一条 event 的 `created_at` 而非下标。
7. **`awaiting_selection` 无超时会永久占住单任务槽位**。用户关掉标签页后任务永远停在等待筛选，重开页面只得到一句「已有任务正在运行」，不说明阶段也不提示可取消（`core/job.py:1218-1225`）。改法：冲突错误信息带上当前任务的阶段与开始时间；等待循环用 `_selection_event.wait()` 替代 0.5 秒轮询（`request_cancel` 已 set 该事件，轮询是冗余的）。
8. **导出阶段实际不可取消**。`export_image_report`（Playwright 启动 + 逐页截图，最耗时的一步）内部没有取消点，前端因此在 exporting 状态直接禁用了取消按钮。图片下载路径已正确传了 `cancel_checker`，导出路径没对齐。改法：给 `export_image_report` 加 `cancel_checker`，在每页截图之间调用，然后放开前端取消按钮。
9. **Playwright 截图循环无逐页容错**。任一页失败会冒泡到兜底 except 整体返回空列表，此时前几页 JPG 已写到磁盘却不进 `page_paths`——磁盘文件与 metadata 不一致，且旧 JPG 与新 preview.html 混存。改法：per-page try/except，失败页记 warning 继续；渲染前先清理旧的 `page_*.jpg`。
10. **DOCX 试写临时文件异常残留且不被任何清理规则匹配**。`_weekly_report_trial.docx` 的前导下划线让 `cleanup_old_generated_docx` 和 `reexport._remove_generated_docx` 的 glob（`weekly_report*.docx`）都匹配不到，异常时残留会永远留在输出目录出现在用户眼前。改法：try/finally 确保删除，或写到系统临时目录。
11. **输出目录解析基准不一致**。`normalize_output_dir` 相对路径基于 `Path.cwd()`（`core/paths.py:56-61`），而历史扫描与 output 清理基于 `ROOT_DIR`。用户从其他目录运行 `python D:\...\app.py` 时，任务写到 `<cwd>/output`，历史扫描却只看 `<项目根>/output`——刚跑完的任务在历史面板「消失」。另外 `validate_config_payload` 的文案建议用户把导出目录放桌面，而 output 清理明确拒绝项目 output 之外的目录，产品行为自相矛盾。
12. **`POST /api/history/scan` 整表覆盖历史索引**（`core/history.py:79`），不做合并；且 `_resolve_output_root` 的 allowed_roots 含 `ROOT_DIR` 本身，`output_dir="."` 会把项目根下任何含 manifest.json 的子目录写进历史。改法：allowed_roots 去掉 ROOT_DIR；scan 改为按 run_id 合并而非覆盖。
13. **`CacheStore` 接受 manifest 中任意绝对路径**（`core/cache.py:184-189`）作为 cache 目录，无归属校验。manifest 位于用户可见目录、可被手工编辑或由第三方分发的历史目录携带。删除路径已有校验，读写路径没有。
14. **manifest 相对化失败时回落写绝对路径**（`export/manifest.py:93-95`），泄露本机目录结构与 Windows 用户名，而 manifest 属于用户可能对外分享的报告目录内容。改法：回落改用 `os.path.relpath`，仅跨盘符时才保留原值。
15. **模态对话框无焦点管理**。preflight、历史详情、历史预览三个 `aria-modal="true"` 的对话框打开时都不移动焦点也无焦点圈闭，键盘用户按 Tab 仍会落在被遮罩的背景控件上。只有帮助弹窗做对了（`help.js:26`）。另外进度堆栈与后端日志区都标了 `aria-live="polite"` 且每秒重建——读屏用户会被持续播报淹没，反而淹没了真正重要的状态变化。改法：抽一个 15 行的 `openDialog()` 工具；移除两处 aria-live，改在 statusPill 上加 `role="status"`。
16. **启动脚本三个问题**。`点我启动.bat:54-60` 每次启动都执行 `pip upgrade` + `pip install`，有网时白白增加 5~20 秒，**断网时 pip 返回非零直接 goto :error，工具完全无法离线启动**——但依赖装好后本工具除抓取外并不需要外网；`:7-19` 只探测 py/python 是否存在，不校验版本 ≥ 3.10，3.8/3.9 用户会在 venv 建好、依赖装完后才死于语法错误；长图依赖的 `playwright install chromium` 既不检测也不提示，新用户首次导出长图必然只得到 preview.html。改法：用 requirements.txt 内容哈希写 `.venv\.deps_ok` 标记，哈希未变则跳过 pip；pip 失败时若 venv 已可 import requests 则降级为警告继续；前置校验 Python 版本；检测 chromium 缺失时输出安装提示。
17. **CDP Cookie 读取有副作用**。读取时若调试浏览器没有可用页面，会 `PUT /json/new` 静默打开一个新标签页（`cookie_helper.py:393-404`）——用户点「自动获取 Cookie」却发现浏览器多了个窗口。另外 `clear_cdp_debug_cache` 默认对 9222/9223 都执行 `Browser.close`，若开发者恰好用 9222 跑着自己的调试 Chrome 会被直接关闭。
18. **依赖升级风险：browser-cookie3 通道可能已基本失效**。Chrome/Edge 127+ 对 Cookie 启用 App-Bound Encryption，`browser_cookie3` 0.19.x 无法解密（上游近乎停更），这条回退通道在多数已更新的 Windows 机器上会解密失败或返回空——而错误被 `_try_loader` 捕获后用户只看到「没读到 Cookie」。建议该通道失败时明确提示「新版浏览器已加密本地 Cookie 存储，请改用调试浏览器方式」，并在 README 把 CDP 通道标为唯一推荐路径。
19. **重复测试文件**。`tests/test_cache_status.py` 与 `tests/integration/test_cache_status.py` 三个用例语义完全重叠，integration 版还多了敏感字段断言且用了正确的隔离——平铺版是纯冗余，且正是它在写真实 `cache/`。删除平铺版，并在 DEVELOPMENT.md 明确「新增测试一律进 unit/ 或 integration/，平铺文件只减不增」。

---

## 明确不建议投入的方向

- **国际化**：工具定位就是中文微博超话用户，CLAUDE.md 亦要求 UI 文案保持中文，i18n 只增加维护面。
- **引入前端框架或构建链**：批次七提到的前端问题（全局命名空间、25 个顺序敏感的 script 标签）用浏览器原生 ES modules 就能解决，不需要打包器。建议在下一次前端较大改动时顺带迁移，而不是单独动。
- **PyInstaller 打包**：仅作可选长期方向观察。playwright 与 browser-cookie3 的打包兼容成本高，而优化 `点我启动.bat`（跳过重复 pip）足以覆盖 90% 的启动体验问题。

## 验证方法

每个批次落地后：

```powershell
python -m unittest discover -s tests    # 154 用例，约 11 秒，完全离线
scripts\smoke_test.bat
```

批次一落地后额外手工验证：从另一个源（例如 `file://` 打开的本地 HTML）发起对 `127.0.0.1:8765` 的 POST，确认被 403 拒绝；`GET /api/report-preview?md_path=<项目根>/weibo_stats_config.json` 确认返回 404 而非配置内容。
