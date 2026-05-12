# 开发说明

本文档面向维护者。普通用户请优先阅读 [README.md](README.md)。

## 环境准备

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

本项目不依赖 Flask、FastAPI、React、Vue 或 Svelte。后端使用标准库 HTTP server，前端使用原生 HTML/CSS/JS。

## 本地启动

```powershell
python app.py
python app.py --no-browser
python app.py --host 127.0.0.1 --port 8765
```

`点我启动.bat` 仍然是面向普通用户的一键入口。

## 运行测试

```powershell
python -m unittest discover -s tests
```

或：

```powershell
scripts\run_tests.bat
```

冒烟检查：

```powershell
scripts\smoke_test.bat
```

测试不应访问真实微博网络，不应依赖真实 Cookie 或浏览器登录状态。

## 测试目录

- `tests/fixtures/`：离线样本数据。
- `tests/unit/`：新增的单元测试。
- `tests/integration/`：新增的集成回归测试。
- `tests/test_*.py`：早期平铺测试，保留兼容。
- `tests/helpers.py`：测试工具函数。

`python -m unittest discover -s tests` 必须能发现所有测试。

## 代码风格

- 优先小步改动，避免推倒重写。
- 不把完整 Cookie、Authorization、token、session、password、secret 写入日志、缓存、manifest、测试输出或前端页面。
- 纯函数优先放到 `modules/` 或 `export/`。
- 导出器不得访问网络。
- 离线重新生成报告不得触发抓取、评论请求或图片下载。

## 新增导出器

1. 在 `export/` 下创建导出模块。
2. 入口函数优先接收 `ExportContext`。
3. 输出路径放在 `ctx.run_dir` 下。
4. 图片缺失时写入 `ctx.warnings`，不要直接失败。
5. 更新 `export/reexport.py` 和相关测试。

## 新增 API

1. 在 `server/handlers.py` 中添加短路由处理。
2. 使用 `server/responses.py` 的 `json_ok` / `json_error`。
3. 错误格式保持：

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

4. 不向前端返回 Python traceback。
5. 不返回完整敏感字段。

## 新增 WebUI 模块

WebUI 使用原生 JS 模块化文件：

- `web/js/api.js`：fetch 封装。
- `web/js/state.js`：前端状态。
- `web/js/form.js`：表单。
- `web/js/cookie.js`：Cookie 区域。
- `web/js/preflight.js`：预检查。
- `web/js/progress.js`：任务状态。
- `web/js/logs.js`：悬浮日志。
- `web/js/candidates.js`：人工筛选。
- `web/js/cache.js`：缓存与重新生成。
- `web/js/preview.js`：Markdown 预览。

CSS 已拆分到 `web/css/`，`web/styles.css` 作为聚合入口。

## 发布脚本

```powershell
scripts\make_release_zip.bat
```

发布前按 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) 执行。
