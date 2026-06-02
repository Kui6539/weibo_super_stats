# CLAUDE.md

这是给 Claude Code 的项目工作指南。目标是让你打开仓库后能快速判断：项目是什么、目录在哪里、接口在哪里、数据怎么流动、改什么文件、怎么验证、哪些东西不能碰。

## 快速定位

先读这些文件：

1. `README.md`：用户视角、功能、运行方式、输出内容。
2. `docs/ARCHITECTURE.md`：当前架构边界和数据流。
3. `docs/DEVELOPMENT.md`：开发、测试、扩展约定。
4. `AGENT.md`：通用 agent 参考手册。
5. 当前任务涉及的源码文件。

项目特征：

- Windows 本地 Python 工具。
- 后端使用 Python 标准库 HTTP server。
- 前端是静态 HTML/CSS/JS。
- 没有 Flask、FastAPI、React、Vue、Svelte。
- 没有前端构建步骤。
- 工具只建议运行在 `127.0.0.1`，不要默认按公网服务设计。

核心链路：

```text
web/index.html + web/js/*
  -> server/handlers.py
  -> core/job.py
  -> crawler.py
  -> cache/<run_id>
  -> export/*
  -> manifest.json + history
```

## 常用命令

安装和启动：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
python app.py --no-browser
python app.py --host 127.0.0.1 --port 8765
```

测试：

```powershell
python -m unittest discover -s tests
scripts\run_tests.bat
scripts\smoke_test.bat
```

长图截图依赖 Playwright：

```powershell
python -m playwright install chromium
```

常用检索：

```powershell
rg "handle_start" server/handlers.py
rg "class CrawlJob" core/job.py
rg "export_image_report" export
rg --files
```

## 目录总览

```text
.
  app.py
  crawler.py
  cookie_helper.py
  requirements.txt
  点我启动.bat
  core/
  server/
  modules/
  export/
  web/
  tests/
  docs/
  scripts/
  output/                 # 生成结果，不是源码
```

## 根目录文件

- `app.py`：CLI 入口。解析 `--host`、`--port`、`--no-browser`，调用 `server.http_server.create_server()`，启动本地 HTTP server，必要时打开浏览器。
- `crawler.py`：微博抓取兼容层和调度层。仍保留真实微博请求、超话翻页、旧版 FM.view 和新版超话 API 切换、长正文补全、评论请求、图片下载调度、旧函数名兼容转发。
- `cookie_helper.py`：Cookie 获取兼容入口。封装 Edge/Chrome 调试浏览器、CDP WebSocket、本地浏览器 Cookie store、CDP profile 清理、`browser-cookie3` 回退逻辑。
- `requirements.txt`：运行依赖，包括 `requests`、`beautifulsoup4`、`lxml`、`browser-cookie3`、`openpyxl`、`pillow`、`python-docx`、`playwright`。
- `点我启动.bat`：普通用户双击启动入口。
- `weibo_stats_config.json`：本地配置，可能包含 Cookie。不要提交。
- `weibo_stats_history.json`：本地历史索引。不要提交。
- `output/`：生成报告、图片和 manifest 的目录。默认不要修改或提交。
- `cache/`：项目根缓存目录，新任务保存为 `cache/<run_id>/`。不要提交。

## 后端目录

### `server/`

- `server/http_server.py`
  - `create_server(host, port)`：创建 `ThreadingHTTPServer`。
  - `_try_create_server(host, port)`：尝试绑定端口。
- `server/handlers.py`
  - `AppRequestHandler`：所有 HTTP 路由。
  - `do_GET()`：GET API 和静态资源。
  - `do_POST()`：POST API。
  - `handle_*()`：具体接口处理。
  - `build_preflight()`：启动前预检查。
  - `check_cookie_state()`：Cookie 检测接口包装。
  - `resolve_run_dir_from_payload()`：解析并限制运行目录。
  - `resolve_report_asset_path()`：限制报告资源路径。
  - `resolve_static_path()`：限制静态文件路径。
- `server/responses.py`
  - `json_ok()`：成功 JSON。
  - `json_error()`：统一错误 JSON。
  - `send_json()`：底层 JSON 发送。
  - `send_static_file()`：静态文件。
  - `parse_json_body()`：读取 JSON 请求体。
  - `content_type_for()`：按后缀返回 content-type。

新增后端 API 的基本步骤：

1. 在 `AppRequestHandler.do_GET()` 或 `do_POST()` 中添加路径分支。
2. 添加 `handle_xxx()` 方法。
3. 解析 body 用 `parse_json_body(self)`。
4. 成功返回用 `json_ok(self, data, **data)` 或 `send_json()`。
5. 可预期错误用 `json_error()` 或抛 `WeiboStatsError` 子类。
6. 不向前端返回 Python traceback。
7. 补 `tests/integration/test_api_contract.py` 或对应测试。

### `core/`

- `core/cache.py`
  - `CacheStore`：项目根 `cache/<run_id>/` 读写，并兼容旧版 `output/<run_id>/cache/`。
  - `sanitize_for_cache()`：移除 Cookie、Authorization、token、password 等敏感字段。
  - `read_manifest()` / `write_manifest_json()`：manifest 读写辅助。
- `core/config.py`
  - 配置文件路径：`weibo_stats_config.json`。
  - 当前配置版本：`CONFIG_VERSION = 3`。
  - 配置结构：`global + presets`。
  - `app_defaults()`：前端默认值。
  - `build_crawl_config()`：把前端 payload 转成 `CrawlConfig` 和 output dir。
  - `validate_config_payload()`：预检查。
  - `save_preset()`、`delete_preset()`、`activate_preset()`、`duplicate_preset()`：预设操作。
- `core/crawl_types.py`
  - `CrawlConfig`：抓取配置数据类。
  - `CrawlError`：抓取层业务错误。
- `core/errors.py`
  - `WeiboStatsError` 基类。
  - `ConfigError`、`CookieInvalidError`、`VisitorSystemError`、`RateLimitedError`、`ParseError`、`ExportError`、`CacheError`、`ReexportError`、`JobCancelled`。
  - `to_error_response()`：异常转 API 错误结构。
- `core/events.py`
  - `STAGE_LABELS`、`STAGE_ORDER`。
  - `JobEvent`。
  - `sanitize_event_payload()`。
  - `infer_log_level()`。
- `core/history.py`
  - `load_history()` / `save_history()`。
  - `scan_output_history()`：扫描 output 下有 manifest 的运行目录。
  - `history_item_from_manifest()`：manifest 转历史项。
  - `resolve_history_report_dir()`：从 run_id 安全解析目录。
- `core/job.py`
  - `CrawlJob`：后台任务主类。
  - `JobManager`：当前任务管理。
  - `create_job()`、`cancel_current_job()`、`serialize_job()`。
  - 这是任务编排最核心文件，改动前先读 `_run()`。
- `core/output_cleanup.py`
  - `output_summary()`。
  - `cleanup_preview()`：只预览。
  - `cleanup_output()`：确认删除。
  - 只能清理 output 下时间戳运行目录。
- `core/paths.py`
  - `safe_resolve()`、`is_relative_to()`、`normalize_output_dir()`、`make_run_dir()`。
- `core/recovery.py`
  - 按错误类型和任务状态生成中文恢复建议。
- `core/version.py`
  - 版本号。

## 抓取和业务逻辑目录

### `modules/`

- `modules/cookie_parser.py`：从普通文本、请求头、cURL 中提取 Cookie；标准化 Cookie；脱敏展示。
- `modules/cookie_browser_store.py`：读取 Edge/Chrome 浏览器本地 Cookie store。
- `modules/cookie_edge_debug.py`：启动/关闭 Edge/Chrome 调试浏览器；读取调试浏览器 Cookie；检查调试端口。
- `modules/cookie_validator.py`：检测 Cookie 是否可用。
- `modules/crawler_client.py`：`WeiboClient`，封装微博请求、Cookie 检测、访客验证识别、超话页面基础判断。
- `modules/crawler_filters.py`：过滤不适合周报的帖子，比如视频帖、总结帖。
- `modules/crawler_scoring.py`：帖子评分公式，包含点赞、评论、作者回复、转发和时间权重。
- `modules/post_normalizer.py`：帖子字段补齐、标准化、前端序列化。
- `modules/text_cleaning.py`：HTML 转文本、微博私有字符清理、超话标签清理、正文规范化。
- `modules/time_utils.py`：微博时间解析、日期标准化、时间范围判断。
- `modules/topic.py`：超话名归一化、报告标题、从页面提取超话名。
- `modules/weibo_chaohua_api.py`：新版超话 API 参数、翻页参数、JSON 帖子解析。
- `modules/weibo_emoticons.py`：微博表情名称提取、表情索引缓存、项目级共享表情资源准备。
- `modules/weibo_html_parser.py`：旧版 FM.view 页面解析、帖子 DOM 解析、计数和图片提取。
- `modules/weibo_url.py`：超话 ID 解析、微博正文链接、图片 URL 标准化。

### `modules/comments/`

- `parser.py`：解析微博评论接口响应，提取普通评论、热评、作者回复。
- `analyzer.py`：统计作者回复、非作者评论、评论摘要。
- `ranking.py`：评论数量榜、评论质量榜、质量分计算。

### `modules/images/`

- `collect.py`：从帖子和热评中收集图片项。
- `candidate_thumbnails.py`：为人工筛选候选帖下载最多 3 张缩略图，写入 `cache/<run_id>/candidate_thumbnails/`。
- `downloader.py`：单图下载、单帖下载、入选帖子批量下载。
- `manifest.py`：图片 manifest 构造、读写。
- `paths.py`：图片目录名、文件名、安全路径片段。
- `url_extract.py`：原图 URL 转换、候选 URL 拆分、去重、正文和评论图片提取。

## 导出目录

### `export/`

- `export/context.py`：`ExportContext`，所有导出器共享上下文。
- `export/csv_exporter.py`：CSV 导出和导出行构造。
- `export/excel_columns.py`：Excel 列和值格式化。
- `export/excel_exporter.py`：XLSX workbook、sheet 写入、保存。
- `export/excel_images.py`：Excel 图片嵌入和图片尺寸计算。
- `export/docx_exporter.py`：周报 DOCX 和汇总 DOCX。
- `export/docx_images.py`：DOCX 中插入帖子图片和评论图片。
- `export/docx_splitter.py`：按大小拆分 DOCX。
- `export/docx_styles.py`：DOCX 中文字体、段落、超链接、换行保留。
- `export/markdown_exporter.py`：`weekly_report.md`。
- `export/summary_exporter.py`：统计摘要、活跃时段、`weibo_summary.txt`。
- `export/weibo_body_exporter.py`：微博正文草稿 `weibo_body.txt`。
- `export/report_helpers.py`：导出共享工具：正文清理、评论格式化、候选选择、相对路径。
- `export/manifest.py`：`manifest.json` 构造。
- `export/reexport.py`：从本地 `cache/` 离线重新生成报告。

导出层约束：

- 导出器只读本地数据和本地文件。
- 导出器不能访问微博网络。
- reexport 不能重新抓取、不能重新请求评论、不能重新下载图片。
- 图片缺失优先写入 warnings，避免无谓中断整个导出。

### `export/image_report/`

- `models.py`：`ImageReportConfig`、`ImageAsset`、`CommentBlock`、`PostBlock`、`PageBlock`、`ImageReportData`、`ImageReportResult`。
- `adapter.py`：从 `ExportContext` 构造长图数据；计算期数、日期范围、图片尺寸。
- `paginator.py`：按估算高度分页和平衡页高。
- `renderer.py`：渲染 `preview.html`。
- `exporter.py`：长图导出入口，写 `preview.html`、调用 Playwright 截 JPG、写 `metadata.json`。

## 前端目录

### `web/`

- `web/index.html`：页面结构和控件 ID。
- `web/styles.css`：CSS 聚合入口，只 import `web/css/*.css`。
- `web/Background.png`：背景图。
- `web/vendor/markdown-it.min.js`：Markdown 预览依赖。

### `web/js/`

- `main.js`：收集 DOM、创建 controller、初始化顺序。
- `api.js`：fetch 封装和错误格式化。
- `form.js`：读取表单，生成后端 payload。
- `topic_preview.js`：超话名称识别、期数输入和标题预览。
- `config.js`：配置加载和自动保存。
- `presets.js`：预设加载、保存、激活、复制、重命名、删除。
- `task.js`：预检查、启动任务、轮询 `/api/status`、提交筛选、取消任务。
- `progress.js`：状态文案、阶段进度、任务步骤。
- `candidates.js`：候选卡片、筛选、排序、勾选。
- `cache.js`：结果文件列表、cache 状态、重新生成。
- `history.js`：历史任务、扫描 output、历史预览、历史 reexport、删除历史。
- `output_cleanup.js`：output 统计、清理预览、确认清理。
- `cookie.js`：Cookie 展示、调试浏览器、自动读取、剪贴板、粘贴识别、检测、清空。
- `preflight.js`：预检查 inline 区域、弹窗、折叠状态缓存。
- `preview.js`：Markdown 预览、报告图片资产 URL 处理、复制 Markdown。
- `logs.js`：浮动日志、筛选、复制、下载、拖拽位置。
- `events.js`：统一事件绑定。
- `theme.js`：主题切换。
- `help.js`：帮助文档弹窗。
- `toast.js`：提示和客户端日志。
- `utils.js`：DOM、HTML 转义、busy 状态、剪贴板。
- `particles.js`：背景粒子。
- `state.js`：预留共享状态。

前端初始化顺序在 `web/js/main.js`：

1. 初始化主题和粒子。
2. `configController.initDefaults()`。
3. 恢复预检查折叠状态。
4. 加载预设。
5. 加载历史。
6. 加载 output summary。
7. 刷新当前任务状态。
8. 加载帮助文档。

### `web/css/`

- `base.css`：全局变量、基础样式。
- `layout.css`：页面布局。
- `components.css`：按钮、面板、徽章、弹窗等组件。
- `forms.css`：表单和 Cookie 区域。
- `progress.css`：进度和阶段。
- `candidates.css`：候选卡片。
- `preview.css`：Markdown 和历史预览。
- `cache.css`：结果文件和 cache 状态。
- `history.css`：历史任务和 output 清理。
- `themes.css`：明暗主题覆盖。

## API 总览

所有 API 在 `server/handlers.py`。

成功响应通常由 `json_ok()` 生成，既有 `data`，也可能带兼容用顶层字段：

```json
{
  "ok": true,
  "data": {},
  "field": "compat"
}
```

错误响应：

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "中文错误",
    "suggestion": "中文建议"
  }
}
```

### GET API

| Path | Handler | 用途 | 关键参数 |
| --- | --- | --- | --- |
| `/api/defaults` | `handle_get_config` | 默认配置、保存配置、默认时间窗口 | 无 |
| `/api/presets` | `handle_get_presets` | 预设列表和激活预设 | 无 |
| `/api/history` | `handle_history` | 历史任务索引 | 无 |
| `/api/status` | `handle_status` | 当前任务快照，前端轮询核心接口 | 无 |
| `/api/report-preview` | `handle_report_preview` | 当前或指定 Markdown 预览 | `md_path` 可选 |
| `/api/report-asset` | `handle_report_asset` | 当前报告中图片资产 | `path`，`md_path` 可选 |
| `/api/candidate-thumbnail` | `handle_candidate_thumbnail` | 读取候选帖缩略图 | `run_id`、`path` |
| `/api/history/asset` | `handle_history_asset` | 历史报告图片资产 | `run_id`、`path` |
| `/api/help-doc` | `handle_help_doc` | Cookie 教程 Markdown | 无 |
| `/Background.png` | special case | 背景图 | 无 |
| static | `resolve_static_path` | `web/` 静态文件 | URL path |

### POST API

| Path | Handler | 用途 | 常见 payload |
| --- | --- | --- | --- |
| `/api/preflight` | `handle_preflight` | 启动前预检查 | 表单 payload |
| `/api/topic-preview` | `handle_topic_preview` | 识别超话名称并计算标题期数 | `super_topic`、`cookie?`、`issue?`、`window_end?` |
| `/api/check-cookie` | `handle_check_cookie` | 检测 Cookie 登录态 | `cookie`、`super_topic` |
| `/api/clear-config` | `handle_clear_config` | 清空 Cookie 或重置配置 | `scope: "cookie" | "all"` |
| `/api/start` | `handle_start` | 保存配置并创建任务 | 表单 payload |
| `/api/select` | `handle_select` | 提交候选选择 | `indexes: number[]` |
| `/api/cancel-selection` | `handle_cancel_selection` | 取消等待筛选 | `{}` |
| `/api/cancel-job` | `handle_cancel_job` | 取消当前任务 | `{}` |
| `/api/config` | `handle_save_config` | 保存配置 | 配置 payload |
| `/api/cache-status` | `handle_cache_status` | 检查运行目录 cache | `run_dir` |
| `/api/reexport` | `handle_reexport` | 当前运行目录离线重新生成 | `run_dir`、`selected_post_ids?`、`export_types?` |
| `/api/history/scan` | `handle_history_scan` | 扫描 output | `output_dir?` |
| `/api/history/remove` | `handle_history_remove` | 删除历史，可选删除文件 | `run_id`、`delete_files?`、`confirm?` |
| `/api/history/cache-status` | `handle_history_cache_status` | 检查历史任务 cache | `run_id` |
| `/api/history/reexport` | `handle_history_reexport` | 历史任务离线重新生成 | `run_id`、`selected_post_ids?`、`export_types?` |
| `/api/history/open-dir` | `handle_history_open_dir` | 打开历史目录 | `run_id` |
| `/api/history/preview` | `handle_history_preview` | 历史 Markdown 预览 | `run_id` |
| `/api/presets/save` | `handle_presets_save` | 保存预设 | `preset_id`/`id`、`preset` |
| `/api/presets/delete` | `handle_presets_delete` | 删除预设 | `preset_id`/`id` |
| `/api/presets/activate` | `handle_presets_activate` | 激活预设 | `preset_id`/`id` |
| `/api/presets/duplicate` | `handle_presets_duplicate` | 复制预设 | `source_id`、`new_id?`、`name?` |
| `/api/output/summary` | `handle_output_summary` | output 统计 | `output_dir?` |
| `/api/output/cleanup-preview` | `handle_output_cleanup_preview` | 清理预览，不删除 | 清理规则 |
| `/api/output/cleanup` | `handle_output_cleanup` | 确认清理 | 清理规则 + `confirm: true` |
| `/api/cookie/auto` | `handle_cookie_auto` | 自动读取 Cookie | `browser: "edge" | "chrome"` |
| `/api/cookie/edge-debug` | `handle_cookie_edge_debug` | 打开调试浏览器 | `browser: "edge" | "chrome"` |
| `/api/cookie/clear-cdp-cache` | `handle_cookie_clear_cdp_cache` | 清理工具内置 CDP profile | `{}` |
| `/api/cookie/extract` | `handle_cookie_extract` | 从文本提取 Cookie | `text` |
| `/api/open-result-dir` | `handle_open_result_dir` | 打开结果目录 | `run_dir?` |

## 前端表单 payload

`web/js/form.js` 的 `readForm()` 会发送：

```json
{
  "super_topic": "",
  "issue": "6",
  "cookie": "",
  "window_start": "2026-06-01T04:00",
  "window_end": "2026-06-08T04:00",
  "max_pages": "80",
  "topic_comment_factor": "1.0",
  "pause_seconds": "1.0",
  "likes_weight": "0.3",
  "comment_weight": "0.5",
  "author_reply_weight": "0.2",
  "repost_weight": "0.1",
  "output_dir": "output",
  "theme": "dark",
  "advanced_mode": false
}
```

`core/config.py` 的 `build_crawl_config()` 会把其中一部分转为 `CrawlConfig`：

- `super_topic`
- `issue`
- `cookie`
- `max_pages`
- `topic_comment_factor`
- `pause_seconds`
- `likes_weight`
- `comment_weight`
- `author_reply_weight`
- `repost_weight`
- `window_start`
- `window_end`
- `output_dir`

`theme` 和 `advanced_mode` 主要用于保存前端偏好。

## 配置结构

配置文件：`weibo_stats_config.json`。

当前版本：`CONFIG_VERSION = 3`。

结构：

```json
{
  "version": 3,
  "active_preset": "default",
  "presets": {
    "default": {
      "name": "默认预设",
      "super_topic": "",
      "max_pages": "80",
      "topic_comment_factor": "1.0",
      "likes_weight": "0.3",
      "comment_weight": "0.5",
      "author_reply_weight": "0.2",
      "repost_weight": "0.1",
      "pause_seconds": "1.0",
      "output_dir": "output",
      "export_types": ["markdown", "docx", "excel", "csv", "summary"],
      "download_images": true
    }
  },
  "global": {
    "cookie": "",
    "theme": "dark",
    "advanced_mode": "false",
    "log_position": {"mode": "bubble", "left": 18, "top": 86},
    "cookie_browser": "edge"
  }
}
```

原则：

- Cookie 始终在 `global`，不要放进 preset。
- 预设只保存超话和导出参数。
- 读配置时走 `load_config()` / `load_saved_config()`。
- 写配置时走 `save_config()` / `save_user_config()`。
- 兼容旧配置时走 `migrate_config()`。

## 关键数据结构

### `CrawlConfig`

位置：`core/crawl_types.py`。

字段：

- `super_topic`
- `cookie`
- `max_pages`
- `pause_seconds`
- `days_window`
- `topic_comment_factor`
- `likes_weight`
- `comment_weight`
- `author_reply_weight`
- `repost_weight`
- `comment_page_limit`
- `text_workers`
- `comment_workers`
- `window_start`
- `window_end`
- `carryover_hours`

### job snapshot

位置：`core/job.py` 的 `CrawlJob.snapshot()`。

`/api/status` 返回的前端依赖字段：

- `id`
- `status`
- `stage`
- `stage_label`
- `progress`
- `subtasks`
- `started_at`
- `created_at`
- `updated_at`
- `logs`
- `events`
- `candidates`
- `required_pick_count`
- `result`
- `error`
- `cancel_requested`
- `recovery_suggestions`

不要随意删除、改名或改变含义。前端 `web/js/task.js`、`progress.js`、`logs.js`、`candidates.js`、`cache.js` 都依赖这些字段。

### 任务状态

- `running`：正在执行。
- `awaiting_selection`：已生成候选，等待人工筛选。
- `exporting`：用户已提交筛选，正在下载图片或导出。
- `completed`：完成。
- `failed`：失败。
- `cancelled`：取消。

### 阶段 stage

定义在 `core/events.py`：

- `idle`
- `init`
- `crawl`
- `hydrate`
- `score`
- `thumbnails`
- `selection`
- `images`
- `export`
- `completed`
- `failed`
- `cancelled`

新增阶段时要同步：

- `core/events.py`
- `core/job.py`
- `web/js/progress.js`
- 相关测试

### candidate

候选帖子由 `core/job.py` 的 `serialize_candidate()` 给前端：

- `index`
- `rank`
- `user_name`
- `publish_time`
- `content`
- `content_excerpt`
- `content_full`
- `score`
- `score_detail`
- `likes`
- `comments`
- `reposts`
- `post_url`
- `image_count`
- `image_preview_paths`：优先为 `/api/candidate-thumbnail` 可读取的缩略图 URL，最多 3 个。

前端提交 `/api/select` 时发送的是 candidate `index`，不是 post_id。

### cache

典型文件：

```text
cache/<run_id>/run_config.json
cache/<run_id>/posts_raw.json
cache/<run_id>/posts_hydrated.json
cache/<run_id>/posts_scored.json
cache/<run_id>/candidates.json
cache/<run_id>/selected_posts.json
cache/<run_id>/community_stats.json
cache/<run_id>/images_manifest.json
cache/<run_id>/comments/post_<post_id>.json
cache/<run_id>/candidate_thumbnails/*.jpg
```

`CacheStore.STAGE_FILES` 决定 stage 到文件的映射。写入时使用 `CacheStore.write_stage()`。

默认缓存根目录是项目根 `cache/`；测试或特殊运行可通过环境变量 `WEIBO_STATS_CACHE_ROOT` 覆盖。

reexport 最低要求：

- `cache/<run_id>/run_config.json`
- `cache/<run_id>/selected_posts.json`
- `cache/<run_id>/posts_scored.json` 或 `cache/<run_id>/posts_hydrated.json`

### `ExportContext`

位置：`export/context.py`。

字段：

- `run_dir`
- `selected_posts`
- `all_posts`
- `config`
- `stats`
- `images_manifest`
- `warnings`
- `failed_images`
- `reexport`

新增导出器优先接收 `ExportContext`。

### manifest

位置：`export/manifest.py`。

`manifest.json` 用于：

- 前端结果展示。
- 历史任务索引。
- cache 状态检查。
- reexport 继承旧文件列表。
- output 清理判断。

主要字段：

- `schema_version`
- `run_id`
- `created_at`
- `updated_at`
- `tool`
- `super_topic`
- `super_topic_name`
- `report_title`
- `super_topic_id`
- `window_start`
- `window_end`
- `selected_count`
- `total_posts`
- `candidate_count`
- `status`
- `files`
- `cache`
- `warnings`
- `failed_image_count`
- `failed_images`
- `reexport_count`
- `last_reexport_at`
- `stats`

不要把 Cookie、Authorization、token、浏览器 profile 或本地敏感请求头写入 manifest。

## 主任务流程

主流程在 `core/job.py` 的 `CrawlJob._run()`：

1. `init`：创建 output 目录和时间戳 run 目录。
2. 初始化项目根 `cache/<run_id>/`，写 `run_config.json`。
3. `crawl`：创建 `WeiboSuperTopicCrawler`。
4. 抓取超话分页，旧版 FM.view 不可用时切换新版超话 API。
5. 补全文本、请求评论、分析评论、评分，期间写阶段缓存。
6. `score`：计算活跃时段，选择候选。
7. `thumbnails`：为 20 条预选帖下载最多 3 张缩略图，写入 `cache/<run_id>/candidate_thumbnails/`。
8. `selection`：序列化候选，状态变为 `awaiting_selection`，等待 `/api/select`。
9. 用户提交选择后，状态变为 `exporting`，阶段进入 `images`。
10. 下载帖子图片和热评图片。
11. 写根缓存中的 `images_manifest.json` 和更新 `selected_posts`。
12. `export`：生成 XLSX、CSV、summary、DOCX、Markdown、微博正文、长图报告。
13. 写 `manifest.json`。
14. 写历史索引。
15. 状态变为 `completed`。

失败路径：

- `JobCancelled` -> 自动清理未完成 output/cache -> `cancelled`
- `CrawlError` -> 自动清理未完成 output/cache -> `failed`
- 其他异常 -> 自动清理未完成 output/cache -> `failed`，错误文本中包含异常类型

## 输出目录结构

典型输出：

```text
output/20260601_184009/
  weekly_report.md
  weekly_report_01.docx
  weekly_report_sum.docx
  weibo_posts.xlsx
  weibo_posts.csv
  weibo_summary.txt
  weibo_body.txt
  image_report/
    preview.html
    page_01.jpg
    metadata.json
  images/
  manifest.json
```

对应缓存位于：

```text
cache/20260601_184009/
  run_config.json
  posts_raw.json
  posts_hydrated.json
  posts_scored.json
  candidates.json
  selected_posts.json
  community_stats.json
  images_manifest.json
  comments/
    post_<post_id>.json
```

微博表情资源是工具级共享资源，不跟随单次输出目录：

```text
assets/weibo_emoticons/
  index.json
  *.png / *.gif / *.webp
```

输出相关注意：

- `preview.html` 是人工检查长图排版用的。
- `page_01.jpg` 等是最终微博发图长图。
- `weibo_body.txt` 是微博正文草稿。
- 项目根 `cache/<run_id>/` 是离线重新生成报告的基础；旧版 `output/<run_id>/cache/` 仍兼容读取。
- 项目根 `assets/weibo_emoticons/` 供所有周报复用；可用 `WEIBO_STATS_EMOTICON_DIR` 覆盖。
- `manifest.json` 是历史、结果展示和清理判断的基础。

## 常见改动路径

### 新增 API

改：

- `server/handlers.py`
- 必要时 `server/responses.py`
- 前端对应 controller
- `tests/integration/test_api_contract.py`

注意：

- 路由写在 `do_GET()` 或 `do_POST()`。
- 不要在 API 中泄漏 traceback。
- 路径参数涉及本地文件时必须限制在允许目录中。

### 新增配置项

改：

- `core/config.py` 的 `DEFAULT_PRESET` 或 `DEFAULT_GLOBAL`
- `PRESET_KEYS`
- `load_saved_config()`
- `save_user_config()`
- `app_defaults()`
- `web/js/form.js`
- `web/js/config.js` 或相关 UI
- `tests/test_config.py` / `tests/test_presets_config.py`

判断放哪里：

- 超话、页数、权重、导出目录、导出格式：preset。
- Cookie、主题、日志位置、浏览器选择：global。

### 改任务阶段或进度

改：

- `core/events.py`
- `core/job.py`
- `web/js/progress.js`
- `web/js/logs.js` 如涉及日志展示
- job snapshot 相关测试

注意：

- `/api/status` 是前端核心契约。
- `SNAPSHOT_LIMIT` 限制返回日志和事件数量。
- 事件 payload 要脱敏。

### 改抓取逻辑

优先看：

- `crawler.py`
- `modules/crawler_client.py`
- `modules/weibo_html_parser.py`
- `modules/weibo_chaohua_api.py`
- `modules/time_utils.py`
- `modules/text_cleaning.py`

原则：

- 真实请求调度可以留在 `crawler.py`。
- 可测试纯逻辑尽量迁到 `modules/`。
- 保留旧函数名转发，避免破坏旧测试和导出入口。

### 改评分或候选

改：

- `modules/crawler_scoring.py`
- `modules/crawler_filters.py`
- `export/report_helpers.py`
- `crawler.py` 中候选选择兼容入口
- `tests/test_scoring.py`
- `tests/test_filters.py`

注意：

- 候选默认取 20 条。
- 最终默认要求选择 `min(15, len(candidates))` 条。
- `/api/select` 要求恰好选择目标数量，候选不足时至少一条。

### 改评论处理

改：

- `modules/comments/parser.py`
- `modules/comments/analyzer.py`
- `modules/comments/ranking.py`
- `crawler.py` 评论请求调度
- `tests/test_comments_*.py`

注意：

- 评论缓存放在 `cache/<run_id>/comments/post_<post_id>.json`，旧版运行目录 cache 仍兼容。
- 评论榜用于 summary、Markdown、DOCX、微博正文。

### 改图片处理

改：

- `crawler.py` 的 `download_post_images()`
- `modules/images/*`
- `core/job.py` 的 `build_images_manifest()`
- `export/image_report/*`
- `export/docx_images.py`
- `export/excel_images.py`
- `tests/test_images_*.py`

注意：

- 图片下载可以失败，但应尽量记录 warnings 和 failed rows。
- reexport 不应重新下载图片。

### 新增或修改导出格式

改：

- 对应 `export/*_exporter.py`
- `export/context.py` 如需要共享新上下文
- `core/job.py` 的导出流程
- `export/reexport.py`
- `export/manifest.py`
- 前端 `web/js/cache.js` / `history.js` 如要展示新文件
- 导出相关测试

注意：

- 导出器不得重新抓取微博帖子、评论或图片；长图表情资源只允许在非 reexport 场景补齐缺失资源。
- 文件应写入 `ctx.run_dir`。
- 路径写入 manifest 时尽量用相对路径。

### 改长图报告

改：

- `export/image_report/models.py`
- `export/image_report/adapter.py`
- `export/image_report/paginator.py`
- `export/image_report/renderer.py`
- `export/image_report/exporter.py`
- `tests/test_image_report_export.py`

注意：

- `preview.html` 即使 JPG 失败也应保留。
- JPG 依赖 Playwright 浏览器。
- 微博表情资源可能产生 warnings。

### 改离线重新生成

改：

- `export/reexport.py`
- `core/cache.py`
- `export/manifest.py`
- `web/js/cache.js`
- `web/js/history.js`
- `tests/test_reexport.py`
- `tests/test_reexport_exports.py`
- `tests/integration/test_reexport_bundle.py`

硬约束：

- 不重新请求微博。
- 不重新请求评论。
- 不重新下载图片。
- 只读本地 cache 和本地图片。

### 改历史任务

改：

- `core/history.py`
- `server/handlers.py` 的 history API
- `web/js/history.js`
- `tests/test_history_*.py`

注意：

- 历史索引不保存完整正文、评论、图片 URL 或 Cookie。
- 删除真实文件必须二次确认。

### 改 output 清理

改：

- `core/output_cleanup.py`
- `server/handlers.py` 的 output API
- `web/js/output_cleanup.js`
- `tests/test_output_cleanup.py`
- `tests/test_web_history_cleanup_wiring.py`

硬约束：

- 先 preview，再 cleanup。
- cleanup 必须要求 `confirm: true`。
- 只能处理 output 下时间戳运行目录。

### 改前端 UI

改：

- `web/index.html`
- 对应 `web/js/*.js`
- 对应 `web/css/*.css`

注意：

- 控件 ID 在 `main.js` 中被集中收集。
- 新按钮需要在 `events.js` 绑定。
- API 请求优先走 `window.WeiboApi.request()` 或 `main.js` 的 `api()` 包装。
- 文案保持中文。

## 测试地图

全部测试：

```powershell
python -m unittest discover -s tests
```

重点测试：

- `tests/integration/test_api_contract.py`：API 契约。
- `tests/integration/test_cache_status.py`：cache status。
- `tests/integration/test_export_bundle.py`：完整导出 bundle。
- `tests/integration/test_reexport_bundle.py`：reexport bundle。
- `tests/test_cache_store.py`：CacheStore。
- `tests/test_config.py`：配置。
- `tests/test_presets_config.py`：预设配置。
- `tests/test_manifest.py`：manifest。
- `tests/test_reexport.py`、`tests/test_reexport_exports.py`：重新生成。
- `tests/test_output_cleanup.py`：output 清理。
- `tests/test_history_*.py`：历史。
- `tests/test_images_*.py`：图片。
- `tests/test_comments_*.py`：评论。
- `tests/test_scoring.py`：评分。
- `tests/test_filters.py`：过滤。
- `tests/test_weibo_url.py`：URL。
- `tests/test_time_utils.py`：时间。
- `tests/test_text_cleaning.py`：文本清理。
- `tests/test_image_report_export.py`：长图导出。
- `tests/unit/test_sensitive_sanitize.py`：敏感信息脱敏。
- `tests/unit/test_fixtures_no_sensitive.py`：fixture 不含敏感信息。

测试规则：

- 不依赖真实微博网络。
- 不依赖真实 Cookie。
- 不依赖真实登录浏览器。
- 不写入用户真实 output，使用临时目录或 fixture。
- 修改共享契约时补集成测试。

## 排障提示

### 启动后页面打不开

看：

- `app.py`
- `server/http_server.py`
- 控制台打印的 URL
- 端口是否被占用

### API 返回 404

看：

- `server/handlers.py` 的 `do_GET()` / `do_POST()`
- 前端请求路径是否一致
- 静态路径是否在 `web/` 下

### 任务卡在等待筛选

这是正常阶段：`status = awaiting_selection`。前端需要通过 `/api/select` 提交 candidate indexes。

看：

- `web/js/candidates.js`
- `web/js/task.js`
- `core/job.py submit_selection()`

### reexport 失败

看：

- `CacheStore.has_required_for_reexport()`
- `cache/<run_id>/run_config.json`
- `cache/<run_id>/selected_posts.json`
- `cache/<run_id>/posts_scored.json` 或 `cache/<run_id>/posts_hydrated.json`
- `export/reexport.py`

### 长图没有 JPG

看：

- 是否安装 Playwright 浏览器组件。
- `export/image_report/exporter.py`
- `image_report/preview.html` 是否已生成。
- warnings 中是否有浏览器启动失败。

### Word/Excel 写入失败

常见原因是文件正被打开。相关错误通常在导出阶段被转换成中文提示。

看：

- `export/reexport.py`
- `core/job.py`
- `export/docx_exporter.py`
- `export/excel_exporter.py`

### Cookie 自动读取失败

看：

- `cookie_helper.py`
- `modules/cookie_edge_debug.py`
- `modules/cookie_browser_store.py`
- 调试浏览器是否已登录微博。
- Edge/Chrome 是否可被定位。

## 安全红线

不要提交、打印或写入公开文件：

- 真实微博 Cookie。
- `SUB`、`SUBP`、`SCF`、`WBPSESS`。
- Authorization header。
- token、password、secret。
- `weibo_stats_config.json`。
- `weibo_stats_history.json`。
- 根目录 `cache/`。
- CDP/debug browser profile。
- 用户生成的 `output/`，除非用户明确要求。

写 cache、manifest、event、log 时使用：

- `core.cache.sanitize_for_cache()`
- `core.events.sanitize_event_payload()`
- `modules.cookie_parser.mask_cookie_for_log()`

## 代码风格和边界

- 优先小步修改。
- 先用 `rg` 找现有模式。
- 中文 UI 文案保持中文。
- 不引入 Flask/FastAPI/React/Vue/Svelte/构建链，除非用户明确要求。
- 不把可测试纯逻辑继续塞进 `crawler.py`。
- 导出器和 reexport 不能访问微博网络。
- 删除真实文件必须保留 preview 和 confirm。
- 路径相关逻辑必须限制在允许目录中。
- 保持 `/api/status` 的 job snapshot 兼容。
- 修改用户可见行为时同步 `README.md` 或 `docs/`。

## MCP 使用

- OpenAI API、ChatGPT Apps SDK、Codex、模型、SDK 和官方文档问题：先用 `openaiDeveloperDocs`。
- 第三方库或框架当前文档：用 `context7`。
- 浏览器交互、UI 验证、前端调试：本地 URL 可用后用 `playwright`。
- shell、文件编辑、测试、git、GitHub：优先使用内置工具。
