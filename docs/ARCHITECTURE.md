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
- `/api/check-cookie`
- `/api/start`
- `/api/status`
- `/api/select`
- `/api/cancel-job`
- `/api/cache-status`
- `/api/reexport`
- `/api/report-preview`
- `/api/open-result-dir`

## core/

- `core/config.py`：配置读写、迁移、预检查参数构造。
- `core/job.py`：任务状态、结构化事件、人工筛选等待、取消信号。
- `core/events.py`：`JobEvent`、阶段标签、事件脱敏。
- `core/cache.py`：`cache/` 读写、缓存状态、manifest 读写辅助。
- `core/paths.py`：路径安全、导出目录处理。
- `core/errors.py`：统一错误类型和 JSON 错误结构。
- `core/crawl_types.py`：`CrawlConfig`、`CrawlError`。
- `core/version.py`：版本号。

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
- `modules/weibo_html_parser.py`：外层原帖 HTML 解析。
- `modules/comments/`：评论解析、分析、榜单。
- `modules/images/`：图片收集、路径、下载、manifest、URL 提取。

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

导出器只依赖本地数据和本地文件，不应访问微博网络。

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

## cookie_helper.py 当前定位

`cookie_helper.py` 仍作为兼容入口，底层能力逐步拆到 `modules/cookie_*`：

- Cookie 文本解析。
- Edge / Chrome 调试浏览器读取。
- 浏览器本地 Cookie 存储读取。
- Cookie 可用性检测。

## cache 与 manifest

每次任务运行目录包含：

```text
cache/run_config.json
cache/posts_raw.json
cache/posts_hydrated.json
cache/posts_scored.json
cache/candidates.json
cache/selected_posts.json
cache/community_stats.json
cache/images_manifest.json
cache/comments/
manifest.json
```

`cache/` 和 `manifest.json` 不应保存登录凭据或会话字段。
