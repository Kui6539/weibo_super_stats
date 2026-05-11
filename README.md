# 微博超话周报统计工具

一个本地运行的微博超话帖子统计与周报生成工具。最初用于整理 Warma 超话周报，也可以换成其他微博超话链接使用。

它会按指定时间范围抓取超话帖子，统计互动数据，下载帖子图片与热评图片，计算帖子分数，辅助人工筛选本周热帖，并导出适合投稿或二次编辑的 `DOCX`、`MD`、`XLSX`、`CSV` 与统计汇总文件。

## 功能概览

- 本地 HTML 页面操作，支持输入超话链接或超话 ID。
- 支持自定义统计时间段，默认窗口为最近一次已过的 `04:00` 到上周同刻 `04:00`。
- 自动翻页抓取，连续 5 页无时间范围内帖子时停止。
- 支持浏览器 Cookie 自动读取、剪贴板读取、粘贴内容与 cURL 片段自动识别。
- 自动补全被微博列表页截断的正文，尽量保留原文换行、分段与空格。
- 自动清理 `warma超话`、`怒九笑超话` 等固定 tag，包括 `#warma超话[表情]#` 这类变体。
- 自动过滤视频帖、汇总帖、导航帖等不适合进入图文周报的内容。
- 下载帖子原图和热评配图，并按入选帖排名分别放入图片文件夹。
- 导出 Excel 表格时可将图片直接嵌入表格。
- 导出投稿用周报，支持 `DOCX` 和 `MD` 两种格式。
- `DOCX` 会按 10MB 限制自动拆分为多个文件，文件名带序号。
- 周报内作者昵称前自动加 `@`，方便发到微博后识别为用户提及。
- 周报内原帖链接会生成为可点击超链接。
- 生成社区互动榜，包括评论数量榜和评论质量榜。

## 运行环境

- Windows 10/11
- Python 3.10 或更高版本
- Edge 或 Chrome 浏览器
- 一个已登录微博网页版的账号

依赖见 [requirements.txt](./requirements.txt)。

## 快速开始

在项目目录打开 PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

启动后会自动打开本地页面，并在命令行持续滚动输出抓取日志。结束服务时，在命令行按 `Ctrl+C`。

可选参数：

```powershell
.\.venv\Scripts\python app.py --no-browser
.\.venv\Scripts\python app.py --host 127.0.0.1 --port 8765
```

## Cookie 获取

微博数据接口需要登录态，因此需要 Cookie。

工具提供三种方式：

1. 点击页面里的 `打开调试 Edge`，在新打开的 Edge 窗口登录微博，再点击 `自动获取 Cookie`。这是推荐方式，不读取本地 Cookie 数据库。
2. 点击页面里的 `自动获取 Cookie`，程序会优先尝试 CDP 调试端口，再降级读取本机 Edge/Chrome Cookie。
3. 使用 `读取剪贴板` / `识别粘贴内容`，自动识别剪贴板里的 Cookie、请求头或 `Copy as cURL` 片段。
4. 手动打开浏览器开发者工具，从 Network 请求里复制完整 Cookie。

更详细的步骤见 [Cookie获取简短教程.md](./Cookie获取简短教程.md)。

注意：Cookie 等同于登录态，请不要提交到 GitHub，也不要发给他人。

工具会把超话链接或 ID、微博 Cookie、导出目录自动保存到项目根目录的 `weibo_stats_config.json`，下次启动会自动读取。该文件已加入 `.gitignore`，不要手动提交。

## 使用流程

1. 在浏览器正常登录微博网页。
2. 在项目目录运行 `.\.venv\Scripts\python app.py`，等待浏览器打开本地页面。
3. 填入超话链接或 ID。
4. 点击 `打开调试 Edge`，在新窗口登录微博后点击 `自动获取 Cookie`；失败时使用 `读取剪贴板` / `识别粘贴内容` 或手动复制。
5. 设置起始与结束日期时间。
6. 根据需要调整最大翻页页数、话题评论系数、请求间隔和导出目录。
7. 点击 `开始抓取并导出`。
8. 在页面出现的“人工筛选”区域中复核候选帖子。
9. 等待导出完成，在 `output/时间戳/` 文件夹查看结果。

## 评分与筛选规则

帖子基础分：

```text
基础分 = 点赞数 * 0.3
       + 非楼主评论数 * 0.5 * 话题评论系数
       + 楼主回复数 * 0.2
       + 转发数 * 0.1
```

说明：

- 非楼主评论数 = 评论总数 - 楼主回复数。
- 楼主对同一条评论的回复最多计 3 次。
- 话题评论系数最低为 0.5，可在页面调整。
- 最终分会叠加时间权重，尽量平衡新帖与旧帖的曝光时间差异。
- 程序会先生成候选前 20 条，默认勾选前 15 条。
- 用户可以取消默认项，并从后 5 条中替换，最终导出 15 条。

不纳入周报的常见类型：

- 视频帖。
- 汇总、合集、导航、索引类帖子。
- 重复整理型内容。

## 社区榜单

周报开头会生成“本周社区互动榜”。

评论数量榜 Top3：

- 按评论总条数排序。
- 同时展示评论过多少条帖子。
- 上榜昵称前会加 `@`。

评论质量榜 Top3：

- 综合评论获赞、进入热评前三次数和评论数量稳定性排序。
- 公示字段包含评论条数、本周评论获赞、热评前三次数。
- 上榜昵称前会加 `@`。

## 导出内容

每次运行会在导出目录下创建一个时间戳文件夹，例如：

```text
output/20260508_210000/
```

其中包含：

- `weibo_posts.xlsx`：中文列名表格，包含帖子数据、热评与图片预览。
- `weibo_posts.csv`：中文列名 CSV，便于进一步分析。
- `weibo_summary.txt`：本次统计摘要。
- `weekly_report.md`：适合导入编辑器或平台二次排版的 Markdown 周报。
- `weekly_report_01.docx`、`weekly_report_02.docx` 等：按 10MB 自动分割的 Word 周报。
- `images/`：下载的帖子图片和热评图片。

图片目录会按最终入选排名分组：

```text
images/
  01_作者名_帖子ID/
  02_作者名_帖子ID/
  ...
```

## 周报格式

周报包含：

- 帖子选取日期。
- 本周社区互动榜。
- 本周热帖 Top15。
- 每条帖子作者、正文、发送时间、图片、热评、原帖链接。

排版细节：

- 作者昵称显示为 `@昵称`。
- 原帖链接在 `DOCX` 中是可点击超链接。
- 正文尽量保留原文换行、空格和分段。
- 微博表情与 emoji 会转换为更适合跨平台显示的颜文字。
- 帖子正文图片在 Word 中右对齐，约占正文栏宽度的 50%。
- 热评图片在 Word 中右对齐，约占正文栏宽度的 25%。
- 帖子之间只保留空行，方便在发布平台内自行添加分割线。

## 统计摘要

`weibo_summary.txt` 会输出：

- 入选帖子数量。
- 入选帖转发、评论、点赞、总互动量与总分。
- 当周全部帖子按日期分布。
- 入选 Top15 按日期分布。
- 日期分布拟合程度。
- 单小时/两小时高峰时段。
- 单小时/两小时低谷时段。
- 建议固定统计时间。
- 评论数量榜和评论质量榜。

统计摘要中的总量、均值、日期分布拟合、活跃时段和评论榜单计算均由 Python 实现。

## 注意事项

- 本工具不提供账号登录或绕过验证能力，只使用你本机已经登录微博后的 Cookie。
- 微博页面和接口可能变化，若抓取失败，可能需要更新解析规则。
- 请合理设置请求间隔，避免高频请求。
- 请遵守微博平台规则和相关法律法规。
- `output/`、`.venv/`、`__pycache__/` 等目录已在 `.gitignore` 中忽略，不建议提交到 GitHub。

## 开发说明

本工具只建议在本机 `127.0.0.1` 使用，不建议部署到公网。后端仍使用 Python 标准库 HTTP 服务，没有引入 FastAPI、Flask 或大型前端框架。

### 模块结构

```text
app.py                 # 启动入口：参数解析、创建本地服务、打开浏览器
server/
  http_server.py       # ThreadingHTTPServer 创建逻辑
  handlers.py          # WebUI/API 路由和请求处理
  responses.py         # JSON/静态文件响应工具
core/
  config.py            # 配置读写、迁移、预检查参数校验、CrawlConfig 构造
  job.py               # CrawlJob、结构化进度、事件、取消和人工筛选协调
  events.py            # JobEvent、阶段定义、日志级别推断
  paths.py             # 路径安全、目录创建、文件名清理
  errors.py            # 后端统一错误类型
modules/
  crawler_scoring.py   # 评分明细与基础评分计算
  crawler_filters.py   # 视频帖、汇总帖、导航帖过滤判断
  crawler_client.py    # 轻量微博请求封装与 Cookie 检测
  cookie_parser.py     # Cookie 文本、请求头、cURL 片段解析与脱敏
  cookie_edge_debug.py # 调试 Edge 启动、读取和关闭封装
  cookie_browser_store.py # Edge/Chrome 本地 Cookie 存储读取封装
  cookie_validator.py  # Cookie 轻量状态检测入口
  text_cleaning.py     # 微博正文、HTML、话题标签清理
  weibo_url.py         # 微博链接、帖子 ID、图片 URL、超话 ID 处理
  time_utils.py        # 微博时间解析和时间窗口判断
  post_normalizer.py   # 帖子字段补齐和前端序列化
export/
  context.py           # 导出上下文
  manifest.py          # manifest.json 生成与写入
  markdown_exporter.py # Markdown 周报导出
  csv_exporter.py      # CSV 导出
  summary_exporter.py  # summary 文本导出
web/
  styles.css           # CSS 入口，按功能导入 web/css/
  app.js               # 旧入口兼容，加载 web/js/main.js
  css/                 # base/layout/components/forms/progress 等样式分区
  js/                  # api/form/config/cookie/preflight/progress/logs/candidates/cache/preview/task 等脚本分区
crawler.py             # 兼容入口，仍保留主要抓取、解析和导出实现
tests/                 # 标准库 unittest 测试
```

第五期拆分后，`cookie_helper.py` 仍作为兼容入口，对外保留原有函数名；具体的 Cookie 文本解析、调试 Edge、本地浏览器存储读取和轻量检测已迁移到 `modules/`。WebUI 保持无框架实现，`web/js/main.js` 主要负责控制器装配和事件绑定；配置读写、表单、高级模式、Cookie 区域、预检查、结构化进度、日志、人工筛选、Markdown 预览、缓存重新生成、帮助弹窗、主题切换、粒子背景和任务轮询分别迁移到 `web/js/` 下的独立模块。

`crawler.py` 暂时仍保留 HTML 解析、长正文补全、评论分析、图片下载、DOCX 复杂排版和 XLSX 嵌图逻辑。Markdown、CSV、summary 这类低风险导出已迁移到 `export/`，并由 `crawler.py` 保留兼容转发。未拆部分耦合较深，后续应按小步迁移，避免一次性重写导致抓取流程回归。

### 本地启动

```powershell
.\.venv\Scripts\python app.py
.\.venv\Scripts\python app.py --no-browser
.\.venv\Scripts\python app.py --host 127.0.0.1 --port 8765
```

### 运行测试

测试使用标准库 `unittest`，不依赖真实微博网络或真实 Cookie：

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

### 主要 API

- `GET /api/defaults`：读取页面默认配置。
- `POST /api/config`：保存页面配置。
- `POST /api/preflight`：开始前预检查。
- `POST /api/check-cookie`：轻量检测 Cookie 登录态。
- `POST /api/start`：启动抓取任务。
- `GET /api/status`：返回结构化任务状态、阶段、进度、事件、候选和导出结果。
- `POST /api/select`：提交人工筛选结果。
- `POST /api/cancel-job`：请求取消当前任务。
- `GET /api/report-preview`：读取 Markdown 周报预览。
- `POST /api/open-result-dir`：打开本地导出目录。

### 配置文件

`weibo_stats_config.json` 当前使用 `version=2` 的扁平结构，保存超话、Cookie、导出目录、主题和高级模式等本地设置。旧配置会在读取时自动迁移；`scope=cookie` 清空时只清 Cookie，`scope=all` 会备份旧配置为 `weibo_stats_config.backup.json` 后恢复默认值。

### manifest.json

每次导出完成后，时间戳目录会生成 `manifest.json`，记录导出目录、Markdown、DOCX、XLSX、CSV、summary、images、警告信息和失败图片数量。WebUI 的“导出结果清单”优先读取任务结果中的 manifest 数据。

## 本地缓存与重新生成报告

每次任务会在运行目录中创建 `cache/`，用于保存中间结果。缓存只用于本地离线重新生成报告，不会写入 Cookie、Authorization、token、session、password、secret 等登录凭据或会话字段。

典型结构：

```text
output/20260508_210000/
  manifest.json
  cache/
    run_config.json          # 本次运行的非敏感配置
    posts_raw.json           # 翻页抓取后的原始帖子
    posts_hydrated.json      # 正文补全后的帖子
    posts_scored.json        # 评论分析和评分后的帖子
    candidates.json          # 自动生成的候选帖子
    selected_posts.json      # 人工最终选择的帖子
    community_stats.json     # 统计摘要、活跃时段、评论榜单
    images_manifest.json     # 图片下载成功/失败清单
    comments/
      post_123456.json       # 单帖评论分析缓存
```

如果 Word/Excel 文件被占用、导出失败，或修改了报告样式，只要 `cache/` 完整，就可以在 WebUI 的“导出结果”区域填写运行目录，点击“检查缓存”，再点击“重新生成报告”。重新生成只读取本地 JSON 缓存，不会重新请求微博、不重新抓取评论、不重新下载图片。

重新生成会默认覆盖这些项目生成文件：

- `weekly_report.md`
- `weibo_posts.xlsx`
- `weibo_posts.csv`
- `weibo_summary.txt`
- `weekly_report*.docx`
- `weekly_report_sum.docx`

它只删除符合项目命名规则的旧 DOCX，不会删除用户手动放入目录的其他文件。如果写入失败，请先关闭正在打开的 Word/Excel 文件后重试。

缓存缺失时，WebUI 会列出缺少的文件。例如缺少 `selected_posts.json` 或 `posts_scored.json` 时，无法离线重新生成，需要重新完成一次完整任务或选择包含完整 `cache/` 的运行目录。少量图片缺失不会阻止重新生成，系统会记录 warning 并继续生成报告。

新增本地 API：

- `POST /api/cache-status`：检查运行目录的缓存完整性。
- `POST /api/reexport`：基于已有 `cache/` 离线重新生成报告。
