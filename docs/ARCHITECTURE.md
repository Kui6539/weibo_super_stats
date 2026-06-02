# 架构说明

本项目是本地单机工具，核心数据流为：

```text
WebUI -> HTTP API -> CrawlJob -> crawler -> cache -> export -> manifest
```

## 入口

- `app.py`：命令行参数、创建本地 HTTP server、打开浏览器。
- `点我启动.bat`：普通用户一键启动入口。

## server/

- `server/http_server.py`：创建 `ThreadingHTTPServer`。
- `server/handlers.py`：HTTP 路由和 API 处理。
- `server/responses.py`：JSON、静态文件、请求体解析工具。

当前 API 包括：

- `/api/defaults`
- `/api/preflight`
- `/api/topic-preview`
- `/api/check-cookie`
- `/api/start`
- `/api/status`
- `/api/select`
- `/api/cancel-job`
- `/api/cache-status`
- `/api/reexport`
- `/api/history`
- `/api/history/scan`
- `/api/history/remove`
- `/api/history/cache-status`
- `/api/history/reexport`
- `/api/presets`
- `/api/presets/save`
- `/api/presets/delete`
- `/api/presets/activate`
- `/api/presets/duplicate`
- `/api/output/summary`
- `/api/output/cleanup-preview`
- `/api/output/cleanup`
- `/api/report-preview`
- `/api/open-result-dir`
- `/api/cookie/auto`
- `/api/cookie/edge-debug`
- `/api/cookie/clear-cdp-cache`
- `/api/cookie/extract`
- `/api/candidate-thumbnail`

## core/

- `core/config.py`：配置读写、迁移、预检查参数构造。
- `core/job.py`：任务状态、结构化事件、缩略图阶段、人工筛选等待、取消信号、失败/取消自动清理。
- `core/events.py`：`JobEvent`、阶段标签、事件脱敏。
- `core/cache.py`：项目根 `cache/<run_id>/` 读写、旧版运行目录 cache 兼容、缓存状态、manifest 读写辅助。
- `core/paths.py`：路径安全、导出目录处理。
- `core/errors.py`：统一错误类型和 JSON 错误结构。
- `core/crawl_types.py`：`CrawlConfig`、`CrawlError`。
- `core/version.py`：版本号。
- `core/history.py`：历史任务索引、output 扫描和历史项归一化。
- `core/recovery.py`：失败原因分类和中文恢复建议。
- `core/output_cleanup.py`：output 统计、清理预览和确认删除。

## modules/

低风险、可测试的纯逻辑逐步迁入 `modules/`：

- `modules/cookie_parser.py`：Cookie 文本、请求头、cURL 片段解析和脱敏。
- `modules/crawler_client.py`：轻量微博请求封装和 Cookie 检测。
- `modules/crawler_scoring.py`：评分公式。
- `modules/crawler_filters.py`：帖子过滤。
- `modules/text_cleaning.py`：正文清理。
- `modules/time_utils.py`：时间解析。
- `modules/weibo_url.py`：超话 ID、微博 URL、图片 URL。
- `modules/topic.py`：超话名解析和报告标题。
- `modules/weibo_emoticons.py`：微博表情 token 提取、共享表情资源准备。
- `modules/weibo_html_parser.py`：外层原帖 HTML 解析。
- `modules/comments/`：评论解析、分析、榜单。
- `modules/images/`：图片收集、路径、下载、候选缩略图、manifest、URL 提取。

## export/

导出和离线重新生成报告相关逻辑：

- `export/context.py`：`ExportContext`。
- `export/markdown_exporter.py`
- `export/csv_exporter.py`
- `export/summary_exporter.py`
- `export/docx_exporter.py`
- `export/excel_exporter.py`
- `export/manifest.py`
- `export/reexport.py`
- `export/report_helpers.py`
- `export/image_report/`：长图数据适配、分页、HTML 预览和 Playwright 截图导出。

导出器只依赖本地数据和本地文件，不应重新抓取微博帖子、评论或图片。长图导出可以补齐缺失的工具级微博表情资源；离线重新生成报告时禁止联网补齐，未命中的表情保留原始 `[表情名]`。

## web/

WebUI 使用静态 HTML/CSS/JS：

- `web/index.html`
- `web/styles.css`
- `web/css/`
- `web/js/`
- `web/vendor/markdown-it.min.js`

前端通过轮询 `/api/status` 获取结构化任务状态，同时保留日志作为详细记录。

## crawler.py 当前定位

`crawler.py` 仍保留为兼容入口和流程编排层：

- 超话抓取调度。
- 长正文补全。
- 评论请求调度。
- 图片下载调度。
- 旧函数名兼容转发。

已迁移出 `crawler.py` 的内容包括：评分、过滤、标题解析、HTML 帖子解析、评论榜单、图片 URL 提取、Markdown/CSV/summary/DOCX/XLSX 导出等。

仍暂留在 `crawler.py` 的逻辑多与真实微博请求、线程池调度、缓存写入时机和任务流程耦合，后续应继续小步迁移。

## 主任务阶段

`core/events.py` 中的阶段顺序为：

```text
init -> crawl -> hydrate -> score -> thumbnails -> selection -> images -> export -> completed
```

- `thumbnails` 位于评分之后、人工筛选之前，用于为 20 条预选帖缓存最多 3 张缩略图。
- 前端任务状态默认先展示完整阶段列表，随后收起为当前进行中的阶段；开始任务时会先展示预检查结果，再展开任务状态。
- 取消或失败会进入清理路径，自动删除尚未完成的 output 运行目录和对应根缓存目录。

## cookie_helper.py 当前定位

`cookie_helper.py` 仍作为兼容入口，底层能力逐步拆到 `modules/cookie_*`：

- Cookie 文本解析。
- Edge / Chrome 调试浏览器读取。
- CDP 调试 profile 清理。
- 浏览器本地 Cookie 存储读取。
- Cookie 可用性检测。

## cache 与 manifest

每次任务会在项目根目录写入独立缓存，运行目录只保留最终报告和 `manifest.json`：

```text
cache/<run_id>/run_config.json
cache/<run_id>/posts_raw.json
cache/<run_id>/posts_hydrated.json
cache/<run_id>/posts_scored.json
cache/<run_id>/candidates.json
cache/<run_id>/selected_posts.json
cache/<run_id>/community_stats.json
cache/<run_id>/images_manifest.json
cache/<run_id>/comments/
cache/<run_id>/candidate_thumbnails/
manifest.json
```

旧版本保存在 `output/<run_id>/cache/` 的缓存仍会被 `CacheStore` 识别。`cache/` 和 `manifest.json` 不应保存登录凭据或会话字段。

取消或失败的未完成任务会自动删除 `output/<run_id>/` 与对应 `cache/<run_id>/`，仅限符合时间戳命名规则且位于安全根目录下的运行目录。

微博表情资源是工具级共享资源，不跟随单次运行复制：

```text
assets/weibo_emoticons/index.json
assets/weibo_emoticons/*.png
assets/weibo_emoticons/*.gif
assets/weibo_emoticons/*.webp
```

长图导出默认只补齐本次周报实际出现的表情；离线重新生成报告时只读取已有资源，不联网下载。
