# Changelog

## v0.10.2 - Unreleased

### Added

- 输出清理预览支持勾选删除，显示清理原因和缺失文件。
- 输出清理输出文件完整性检测，返回缺失/已存在/预期文件列表。
- 超话 Cookie 检测支持最多 3 页解析并返回逐页统计。
- 历史任务"重新生成"后在主界面显示导出进度条，完成后展示结果文件列表和 Markdown 预览。
- 历史任务扫描可识别缓存结构不完整的 output 目录（无 manifest.json）。
- 输出清理自动将缓存不完整的目录列为可清理项，不占用"保留最近 N 个"名额。
- 输出清理预览列表中显示"缓存不完整"标签。
- 历史任务和输出清理在任务完成后自动刷新，无需手动扫描。
- `/api/report-preview` 和 `/api/report-asset` 支持 `md_path` 查询参数，可预览非当前任务的报告。
- `/api/open-result-dir` 支持 POST body 中传入 `run_dir`，可打开非当前任务的导出目录。
- 所有 Markdown 窗口标题栏显示相对路径而非绝对路径。

### Changed

- 自动读取 Cookie 后延迟关闭调试浏览器，并自动触发检测。
- 输出清理接口与前端支持 `selected_run_ids`，返回全量清理项目。
- 历史任务列表加载改为自动扫描 output 目录，始终反映最新状态。
- 历史任务"移除"改为"删除"，实际删除 output 目录及文件。
- 输出清理预览区域可滚动（max-height: 320px）。
- 导出/重新生成阶段禁用取消按钮（按钮仍显示但不可点击）。
- 进度条步骤严格按顺序渲染，避免重新生成后新任务阶段错位。
- 进度条仅在节点实际乱序时调整 DOM，避免轮询导致的视觉抖动。
- Markdown 预览窗口、帮助文档窗口和历史预览窗口宽度增大。
- 主布局 max-width 从 1520px 增至 1680px，预览列宽从 520px 增至 580px。

### Fixed

- 从历史任务重新生成后，Markdown 预览和"打开文件所在位置"因无活跃任务而失败的问题。
- 周报预览标题栏按钮在窄窗口下换行错位的问题（flex-wrap: nowrap）。

## v0.9.2 - Unreleased

### Added

- 历史任务索引 `weibo_stats_history.json`，支持扫描 `output/` 重建历史。
- 历史任务 API：查看历史、扫描、移除、检查缓存、从历史重新生成报告。
- 配置预设 `version=3`，将 Cookie 等全局项与超话抓取参数分离。
- 预设 API：保存、删除、激活和复制预设。
- 失败恢复建议模块，用于 Cookie、访客验证、网络、解析、文件占用和 cache 缺失等场景。
- output 清理 API，支持统计、清理预览和确认删除。
- WebUI 历史任务中心、预设控件和输出清理面板。
- 历史、预设、恢复建议、输出清理和历史 API 的 unittest 覆盖。

### Changed

- `core/config.py` 保持旧前端扁平字段兼容，同时内部迁移到 `global + presets`。
- 任务完成和离线重新生成报告后会更新历史索引。
- 发布脚本版本更新为 `0.9.2`，并确保根目录 `README.md` 打包进 release zip。

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
