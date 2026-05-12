# Release Checklist

目标版本：`v0.9.0`

## 自动检查

- [ ] 运行单元和集成测试：

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

- [ ] 检查 `dist/weibo_super_stats_v0.9.0.zip` 不包含：
  - `.git/`
  - `.venv/`
  - `output/`
  - `weibo_stats_config.json`
  - `weibo_stats_config.backup.json`
  - `.edge_cdp_profile/`
  - `.chrome_cdp_profile/`
  - `__pycache__/`
  - `*.pyc`
  - `*.log`

## 手动检查

- [ ] `python app.py` 能启动。
- [ ] `python app.py --no-browser` 能启动。
- [ ] `python app.py --host 127.0.0.1 --port 8765` 能启动。
- [ ] `点我启动.bat` 能启动。
- [ ] WebUI 能打开。
- [ ] 基础模式和高级模式切换正常。
- [ ] Cookie 自动读取、手动识别、测试、清空正常。
- [ ] 预检查有错误时不能开始任务。
- [ ] 真实抓取任务能进入人工筛选。
- [ ] 人工筛选后能导出 MD/DOCX/XLSX/CSV/summary。
- [ ] 导出目录中存在 `cache/` 和 `manifest.json`。
- [ ] 断网后可基于 `cache/` 重新生成报告。
- [ ] Word/Excel 打开导出文件时，重新生成能给出友好错误。
- [ ] 日志气泡和任务状态显示正常。
- [ ] Markdown 预览、刷新和复制正常。

## 发布前确认

- [ ] 不提交真实 Cookie。
- [ ] 不提交 `weibo_stats_config.json`。
- [ ] 不提交 `output/`。
- [ ] 不提交 CDP profile。
- [ ] README、DEVELOPMENT、ARCHITECTURE、CHANGELOG 已更新。
- [ ] CHANGELOG 中版本号与 `core/version.py` 一致。
