# weibo_super_stats

本项目是一个本地运行的微博超话周报统计工具，用于抓取指定超话在时间窗口内的帖子数据，辅助人工筛选热帖，并导出适合发布或二次编辑的周报附件。

工具只建议在 `127.0.0.1` 本地使用，不建议部署到公网。

当前版本：`v0.11.0`

## 功能概览

- WebUI 基础模式 / 高级模式。
- Edge / Chrome 调试模式辅助读取微博 Cookie。
- 超话名称自动识别与期数输入：输入超话链接后自动解析名称，支持手动填写或自动计算周报期数，标题实时预览。
- 开始任务前预检查输入、时间范围、导出目录、期数重复和任务占用状态。
- 结构化任务状态、阶段进度、任务取消和终端滚动日志。
- 抓取帖子、补全文本、评论分析、评分排序和人工筛选。
- 导出 Markdown、DOCX、XLSX、CSV、summary。
- 导出适合微博发图的周报长图 JPG，并生成 `preview.html` 供人工检查排版。
- WebUI 内置长图预览面板，支持翻页浏览和缩略图导航。
- 导出微博正文草稿 `weibo_body.txt`，包含评论排行榜和 Top 帖原帖链接。
- 每次任务生成 `cache/`，保存中间结果；缓存独立于输出目录，存放在项目根 `cache/<运行ID>/`。
- 支持基于 `cache/` 离线重新生成报告，不重新请求微博。
- 历史任务中心可扫描 `output/`、浏览历史结果、检查缓存并一键重新生成报告。
- 配置预设支持保存不同超话和导出参数，Cookie 作为全局配置不会随预设切换丢失。
- 输出清理工具支持先预览再确认删除，默认不会自动清理任何文件。

## 运行环境

- Windows 10/11。
- Python 3.10 及以上，建议使用当前稳定版。
- 已登录微博网页账号。

## 快速开始

方式一：双击启动

```text
点我启动.bat
```

方式二：命令行启动

```powershell
python app.py
```

常用参数：

```powershell
python app.py --no-browser
python app.py --host 127.0.0.1 --port 8765
```

首次运行如果缺少依赖，请执行：

```powershell
pip install -r requirements.txt
```

长图导出依赖 Playwright 调用本机浏览器截图。首次安装依赖后，如本机没有可用的 Chromium/Edge 组件，可执行：

```powershell
python -m playwright install chromium
```

## Cookie 获取

推荐方式：

1. 在页面 Cookie 区域选择 Edge 或 Chrome。
2. 点击“打开调试浏览器”。
3. 在调试浏览器中登录微博。
4. 点击“自动读取 Cookie”。
5. 点击“测试 Cookie”确认状态。

备用方式：

- 从微博网页请求头中复制 Cookie。
- 在页面中粘贴请求头或 cURL 片段。
- 点击“识别粘贴内容”。

更详细说明见 [docs/Cookie获取简短教程.md](docs/Cookie获取简短教程.md)。

## 使用流程

1. 填写超话链接或超话 ID。
2. 填写或自动读取微博 Cookie。
3. 设置开始时间、结束时间和导出目录。
4. 如有需要，打开高级模式调整最大页数、评论系数、请求间隔。
5. 点击“开始抓取并导出”。
6. 预检查通过后继续任务。
7. 在候选卡片中人工选择需要入选的帖子。
8. 等待图片下载和文件导出完成。
9. 在导出结果区查看文件清单、Markdown 预览和缓存状态。

## 抓取范围规则

工具只收集设置时间范围内的帖子，并按帖子 ID 去重。分页抓取会在满足以下任一条件时停止：

- 连续 5 页没有发现新的时间范围内帖子。
- 到达最大页数上限，默认最多 80 页。

如果单页里重复出现已抓取过的帖子，只会计入日志统计，不会重复写入候选列表。正文中的 `#warma超话#`、`#Warma超话#`、`#warma[超话]#` 等超话标签会在报告文本中移除。

## 导出内容

每次任务会在导出目录下创建一个时间戳运行目录，常见文件包括：

- `weekly_report.md`
- `weekly_report_01.docx`
- `weekly_report_sum.docx`
- `weibo_posts.xlsx`
- `weibo_posts.csv`
- `weibo_summary.txt`
- `weibo_body.txt`
- `image_report/preview.html`
- `image_report/page_01.jpg`
- `image_report/metadata.json`
- `images/`
- `manifest.json`

导出的标题会跟随当前超话名称变化，不再写死为特定超话。

## 长图与微博正文

`image_report/` 面向微博发图场景：

- `preview.html` 用于浏览器预览分页、字体、图片和表情渲染。
- `page_01.jpg`、`page_02.jpg` 等为最终长图，宽度一致，高度按内容自适应。
- 每页标题为 `XX超话周报 第x期`，会随输入的超话自动识别；标题中的 `——新浪超话` 会被清理掉。
- 超话输入框下方会显示当前识别的超话名称和期数，期数只接受数字，并会应用到 Markdown、DOCX、微博正文和长图标题。
- 帖子正文完整展示，图片按原比例等宽纵向排列。
- 评论区只展示热评内容，不显示点赞量；帖子评论数、转发数等数据放在正文和热评之间。
- 长图会尽量把微博表情标记还原为图片；表情资源统一保存在项目根 `assets/weibo_emoticons/`，不同运行共享。如果本地未命中对应表情，会保留原始 `[表情名]` 文本，方便人工检查。

`weibo_body.txt` 面向微博正文编辑：

- 包含评论数量榜和评论质量榜。
- 附上 15 个 Top 帖的 `@发帖人` 和原帖链接，链接可直接复制到微博正文中使用。
- 不包含真实 Cookie、缓存路径或本地文件路径。

## 本地缓存与重新生成

项目根目录中的 `cache/<运行ID>/` 会保存每次任务的中间结果；旧版本保存在 `output/<运行ID>/cache/` 的缓存仍可被识别：

- 原始帖子：`posts_raw.json`
- 正文补全：`posts_hydrated.json`
- 评分结果：`posts_scored.json`
- 候选帖子：`candidates.json`
- 人工选择：`selected_posts.json`
- 统计信息：`community_stats.json`
- 图片清单：`images_manifest.json`
- 评论缓存：`comments/`

如果导出失败、Word/Excel 文件被占用，或只是修改了报告样式，可以在 WebUI 中使用“检查缓存”和“重新生成报告”。重新生成只读取本地缓存，不会重新请求微博，也不会联网补齐微博表情资源。

## 历史任务、预设与清理

- `weibo_stats_history.json` 会保存历史任务摘要，不保存完整正文、评论、图片 URL 或 Cookie。
- 历史任务中心可以扫描 `output/` 下已有 `manifest.json` 的运行目录。
- 历史任务可直接检查 cache 完整性，并从 cache 离线重新生成报告。
- 输出清理只处理 `output/` 下的报告目录，不会自动删除项目根目录的 `cache/<运行ID>/`。
- 配置文件已升级为 `version=3`：超话、页数、请求间隔、导出目录等保存在 preset 中，Cookie、主题、浏览器选择和日志窗口位置保存在 global 中。
- 输出清理必须先生成预览，再由用户确认删除；只允许处理 `output/` 下的时间戳运行目录。

## 注意事项

- 微博页面和接口变化可能导致抓取失败。
- 请合理设置请求间隔，避免请求过快。
- Cookie 明文保存在本地配置中，工具提供“清空 Cookie”功能。
- 长图 JPG 依赖 Playwright 调用本机 Edge/Chromium 截图；若浏览器组件不可用，会保留 `preview.html` 并给出警告。
- 不要提交本地配置、输出目录、CDP profile 或真实 Cookie。
- 不要提交 `weibo_stats_history.json`，它是本地历史索引。
- 重新生成报告依赖完整 `cache/`，旧运行目录如果没有缓存，需要重新执行一次任务。

## 开发与发布文档

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)：开发环境、测试、扩展说明。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块结构和数据流。
- [docs/CHANGELOG.md](docs/CHANGELOG.md)：版本变更记录。
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)：发布前检查清单。
