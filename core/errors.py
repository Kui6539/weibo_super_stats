from __future__ import annotations

from typing import Any


class WeiboStatsError(Exception):
    code = "WEIBO_STATS_ERROR"
    message = "工具运行出错"
    suggestion = "请检查输入后重试"

    def __init__(self, message: str | None = None, suggestion: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        if suggestion is not None:
            self.suggestion = suggestion


class ConfigError(WeiboStatsError):
    code = "CONFIG_ERROR"
    message = "配置处理失败"
    suggestion = "请检查配置文件是否可读写，或删除配置文件后重试"


class CookieInvalidError(WeiboStatsError):
    code = "COOKIE_INVALID"
    message = "Cookie 不可用"
    suggestion = "请确认已登录微博网页，或重新获取 Cookie"


class VisitorSystemError(WeiboStatsError):
    code = "VISITOR_SYSTEM"
    message = "微博返回访客验证"
    suggestion = "请在 weibo.com 重新登录后获取完整登录态 Cookie"


class RateLimitedError(WeiboStatsError):
    code = "RATE_LIMITED"
    message = "请求可能被微博限制"
    suggestion = "请降低请求频率，稍后重试"


class ParseError(WeiboStatsError):
    code = "PARSE_ERROR"
    message = "内容解析失败"
    suggestion = "请检查输入链接是否正确，或稍后重试"


class ExportError(WeiboStatsError):
    code = "EXPORT_ERROR"
    message = "导出文件失败"
    suggestion = "请检查导出目录是否可写，关闭已打开的导出文件后重试"


class CacheError(WeiboStatsError):
    code = "CACHE_ERROR"
    message = "缓存处理失败"
    suggestion = "请检查运行目录中的 cache 文件是否完整，或重新执行一次完整任务"


class ReexportError(WeiboStatsError):
    code = "REEXPORT_FAILED"
    message = "重新生成报告失败"
    suggestion = "请确认运行目录包含完整 cache，关闭已打开的 Word/Excel 文件后重试"


class ReexportCacheMissingError(ReexportError):
    code = "REEXPORT_CACHE_MISSING"
    message = "缓存文件不完整，无法重新生成报告"
    suggestion = "请重新执行一次完整任务，或选择包含完整 cache 的运行目录"


class JobCancelled(WeiboStatsError):
    code = "JOB_CANCELLED"
    message = "任务已取消"
    suggestion = "如需继续，请重新开始任务"


def to_error_response(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, WeiboStatsError):
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "suggestion": exc.suggestion,
            },
        }
    return {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "suggestion": "请检查输入参数、Cookie 和网络状态后重试",
        },
    }
