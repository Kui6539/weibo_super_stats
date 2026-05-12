# weibo_super_stats

本项目是一个本地运行的微博超话周报统计工具，用于抓取指定超话在时间窗口内的帖子数据，辅助人工筛选热帖，并导出适合发布或二次编辑的周报附件。

工具只建议在 `127.0.0.1` 本地使用，不建议部署到公网。

当前版本：`v0.10.0`

## 功能概览

- WebUI 基础模式 / 高级模式。
- Edge / Chrome 调试模式辅助读取微博 Cookie。
- 开始任务前预检查输入、时间范围、导出目录和任务占用状态。
- 结构化任务状态、阶段进度、任务取消和终端滚动日志。
- 抓取帖子、补全文本、评论分析、评分排序和人工筛选。
- 导出 Markdown、DOCX、XLSX、CSV、summary。
- 每次任务生成 `cache/`，保存中间结果。
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

## 导出内容

每次任务会在导出目录下创建一个时间戳运行目录，常见文件包括：

- `weekly_report.md`
- `weekly_report_01.docx`
- `weekly_report_sum.docx`
- `weibo_posts.xlsx`
- `weibo_posts.csv`
- `weibo_summary.txt`
- `images/`
- `cache/`
- `manifest.json`

导出的标题会跟随当前超话名称变化，不再写死为特定超话。

## 本地缓存与重新生成

任务运行目录中的 `cache/` 会保存：

- 原始帖子：`posts_raw.json`
- 正文补全：`posts_hydrated.json`
- 评分结果：`posts_scored.json`
- 候选帖子：`candidates.json`
- 人工选择：`selected_posts.json`
- 统计信息：`community_stats.json`
- 图片清单：`images_manifest.json`
- 评论缓存：`comments/`

如果导出失败、Word/Excel 文件被占用，或只是修改了报告样式，可以在 WebUI 中使用“检查缓存”和“重新生成报告”。重新生成只读取本地缓存，不会重新请求微博。

## 历史任务、预设与清理

- `weibo_stats_history.json` 会保存历史任务摘要，不保存完整正文、评论、图片 URL 或 Cookie。
- 历史任务中心可以扫描 `output/` 下已有 `manifest.json` 的运行目录。
- 历史任务可直接检查 cache 完整性，并从 cache 离线重新生成报告。
- 配置文件已升级为 `version=3`：超话、页数、请求间隔、导出目录等保存在 preset 中，Cookie、主题、浏览器选择和日志窗口位置保存在 global 中。
- 输出清理必须先生成预览，再由用户确认删除；只允许处理 `output/` 下的时间戳运行目录。

## 注意事项

- 微博页面和接口变化可能导致抓取失败。
- 请合理设置请求间隔，避免请求过快。
- Cookie 明文保存在本地配置中，工具提供“清空 Cookie”功能。
- 不要提交本地配置、输出目录、CDP profile 或真实 Cookie。
- 不要提交 `weibo_stats_history.json`，它是本地历史索引。
- 重新生成报告依赖完整 `cache/`，旧运行目录如果没有缓存，需要重新执行一次任务。

## 开发与发布文档

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)：开发环境、测试、扩展说明。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：模块结构和数据流。
- [docs/CHANGELOG.md](docs/CHANGELOG.md)：版本变更记录。
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)：发布前检查清单。
