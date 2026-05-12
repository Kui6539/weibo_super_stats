from __future__ import annotations

from typing import Any


def classify_error(error: Any) -> str:
    text = _error_text(error)
    lowered = text.lower()
    if "cookie" in lowered or "登录" in text:
        return "cookie"
    if "访客" in text or "visitor" in lowered or "sina visitor" in lowered:
        return "visitor"
    if "timeout" in lowered or "超时" in text or "频率" in text or "rate" in lowered:
        return "network"
    if "解析" in text or "parse" in lowered:
        return "parse"
    if "word" in lowered or "excel" in lowered or "permission" in lowered or "占用" in text:
        return "file_locked"
    if "cache" in lowered or "缓存" in text:
        return "cache"
    if "图片" in text or "image" in lowered:
        return "images"
    return "unknown"


def build_recovery_suggestions(error: Any, job: Any = None, manifest: dict[str, Any] | None = None) -> list[dict[str, str]]:
    category = classify_error(error)
    suggestions = {
        "cookie": [
            ("测试 Cookie", "先点击“测试 Cookie”，确认当前登录态是否可用。"),
            ("重新获取 Cookie", "打开调试浏览器并登录微博后重新自动获取 Cookie。"),
        ],
        "visitor": [
            ("完成微博验证", "在调试浏览器中完成微博访客验证或重新登录后再试。"),
            ("改用手动导入", "如果自动读取仍拿到访客 Cookie，请从已登录页面请求头手动复制 Cookie。"),
        ],
        "network": [
            ("降低请求频率", "把请求间隔调大后重试，例如 1.5 秒或 2 秒。"),
            ("稍后重试", "微博短时间限制或网络波动时，等待一段时间再运行。"),
        ],
        "parse": [
            ("检查页面变化", "微博页面或接口可能改版，请保留日志用于更新解析规则。"),
            ("减少时间范围", "可先缩短统计时间范围，确认是否只有部分页面异常。"),
        ],
        "file_locked": [
            ("关闭占用文件", "关闭正在打开的 Word 或 Excel 文件后重新生成报告。"),
            ("从缓存重新生成", "如果抓取已完成，可以从 cache 离线重新生成报告。"),
        ],
        "cache": [
            ("检查缓存完整性", "使用“检查缓存”确认 selected_posts 和 posts_scored 是否存在。"),
            ("重新执行完整任务", "缓存不完整时，需要重新完成抓取和人工筛选。"),
        ],
        "images": [
            ("继续文本导出", "少量图片失败不会影响 Markdown、CSV、summary 等文本报告。"),
            ("稍后重试图片", "图片地址可能临时不可访问，可稍后重新运行完整任务。"),
        ],
        "unknown": [
            ("查看任务日志", "检查终端与任务日志中的最近错误，确认失败阶段。"),
            ("保留输出目录", "不要删除 output 中的运行目录，便于从已有 cache 恢复。"),
        ],
    }
    rows = [{"title": title, "message": message} for title, message in suggestions[category]]
    if manifest and manifest.get("reexport_count"):
        rows.append({"title": "已有重新生成记录", "message": "该任务曾从缓存重新生成过报告，可继续尝试只生成未成功的格式。"})
    if job and getattr(job, "status", "") == "awaiting_selection":
        rows.append({"title": "等待人工筛选", "message": "请完成或取消人工筛选，任务才能继续进入导出阶段。"})
    return rows


def recovery_suggestions_for_status(job_status: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(job_status, dict):
        return []
    status = str(job_status.get("status") or "")
    if status == "failed":
        return build_recovery_suggestions(job_status.get("error") or job_status.get("progress", {}).get("message") or "")
    if status == "cancelled":
        return [{"title": "任务已取消", "message": "已生成的 cache 和临时文件会保留，可检查 output 目录后决定是否重新开始。"}]
    return []


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        return " ".join(str(error.get(key) or "") for key in ("code", "message", "suggestion"))
    return str(error or "")
