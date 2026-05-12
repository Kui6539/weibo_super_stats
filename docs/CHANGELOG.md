# Changelog

## v0.9.1 - Unreleased

### Changed

- 文档集中到 `docs/`，README 引用路径同步更新。
- 发布打包脚本改为包含 `docs/` 目录。

### Fixed

- Markdown 预览打开时避免在桌面端触发页面自动滚动，防止抓取设置区域上移。
- 帮助文档读取路径指向 `docs/Cookie获取简短教程.md`。

## v0.9.0 - Unreleased

### Added

- WebUI 基础模式 / 高级模式。
- Cookie 辅助读取、测试和清空。
- 开始前预检查。
- 结构化任务状态、任务事件和任务取消。
- 本地 `cache/` 中间结果缓存。
- 基于 `cache/` 的离线重新生成报告。
- Markdown、CSV、summary、DOCX、XLSX 导出器拆分。
- 评论、图片、评分、过滤、URL、时间、文本清理等模块拆分。
- `tests/fixtures/` 离线样本数据。
- 导出、重新生成报告、API 合同、缓存状态、敏感字段回归测试。
- `scripts/run_tests.bat`、`scripts/smoke_test.bat`、`scripts/clean_generated.bat`、`scripts/make_release_zip.bat`。
- `DEVELOPMENT.md`、`ARCHITECTURE.md`、`RELEASE_CHECKLIST.md`。

### Changed

- `crawler.py` 收敛为抓取流程和兼容入口，低风险纯函数迁移到 `modules/` 和 `export/`。
- 导出的周报标题和文件名不再写死特定超话。
- Markdown 预览使用 `markdown-it`。
- 导出结果清单优先读取 `manifest.json`。

### Fixed

- 转发帖中的被转发内容不再参与原帖互动数解析。
- Markdown 预览关闭后再次打开卡在加载状态的问题。
- 亮色主题下进度条对比度不足的问题。
- 日志悬浮气泡位置、动画和本地持久化问题。

### Security

- `cache/` 和 `manifest.json` 写入前过滤 Cookie、Authorization、token、session、password、secret 等敏感字段。
- 事件 payload 和测试输出避免包含完整敏感字段。
