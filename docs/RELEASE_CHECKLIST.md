# Release Checklist

目标版本：`v0.11.1`

## 自动检查

- [ ] 运行完整测试：

```powershell
python -m unittest discover -s tests
```

- [ ] 运行脚本版测试：

```powershell
scripts\run_tests.bat
```

- [ ] 运行冒烟检查：

```powershell
scripts\smoke_test.bat
```

- [ ] 生成发布包：

```powershell
scripts\make_release_zip.bat
```

- [ ] 检查 `dist/weibo_super_stats_v0.11.1.zip` 不包含：
  - `.git/`
  - `.venv/`
  - `output/`
  - `weibo_stats_config.json`
  - `weibo_stats_history.json`
  - `.edge_cdp_profile/`
  - `.chrome_cdp_profile/`
  - `__pycache__/`
  - `*.pyc`
  - `*.log`
- [ ] 检查发布包包含 `assets/weibo_emoticons/`。

## 手动检查

- [ ] `python app.py` 能启动。
- [ ] `python app.py --no-browser` 能启动。
- [ ] `python app.py --host 127.0.0.1 --port 8765` 能启动。
- [ ] `点我启动.bat` 能启动。
- [ ] WebUI 能打开。
- [ ] 基础模式和高级模式切换正常。
- [ ] Cookie 自动读取、手动识别、测试、清空正常。
- [ ] “清除 CDP 缓存”只删除 `.edge_cdp_profile/` 和 `.chrome_cdp_profile/`，不会影响常规浏览器配置。
- [ ] 预检查有错误时不能开始任务。
- [ ] 真实抓取任务能进入人工筛选。
- [ ] 评分后出现“下载预选帖缩略图”阶段，任务日志有逐项下载/缓存命中记录。
- [ ] 人工筛选候选卡片能展示最多 3 张缩略图，并标注原帖剩余图片数量。
- [ ] 人工筛选后能导出 MD/DOCX/XLSX/CSV/summary。
- [ ] 项目根目录存在 `cache/<run_id>/`，导出目录中存在 `manifest.json`。
- [ ] 导出/重新生成阶段取消按钮禁用。
- [ ] 断网后可基于 `cache/` 重新生成报告。
- [ ] 取消任务和任务失败后，未完成的 output 运行目录与对应根缓存会被自动清理。
- [ ] 历史任务自动扫描 output 并显示完整和不完整的任务。
- [ ] 历史任务"重新生成"后主界面显示进度、结果和 Markdown 预览。
- [ ] 历史任务"删除"能删除 output 目录。
- [ ] 配置预设可新建、保存、切换、复制和删除。
- [ ] 输出清理预览可滚动，缓存不完整的目录自动列入清理候选。
- [ ] Word/Excel 打开导出文件时，重新生成能给出友好错误。
- [ ] 日志气泡展开/收起动画自然，任务状态先跟随预检查展开/收起，再自动收起到当前阶段。
- [ ] Markdown 预览、刷新和复制正常。
- [ ] 导出结果里的 Markdown 和长图预览按钮都能打开旁侧预览。
- [ ] 任务完成后历史列表和输出清理摘要自动刷新。

## 发布前确认

- [ ] 不提交真实 Cookie。
- [ ] 不提交 `weibo_stats_config.json`。
- [ ] 不提交 `weibo_stats_history.json`。
- [ ] 不提交 `output/`。
- [ ] 不提交 CDP profile。
- [ ] README、DEVELOPMENT、ARCHITECTURE、CHANGELOG 已更新。
- [ ] CHANGELOG 版本号与 `core/version.py` 一致。
