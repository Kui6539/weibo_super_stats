from __future__ import annotations

from typing import Any


def check_cookie_state(cookie: str, super_topic: str | None = None) -> dict[str, Any]:
    if not str(cookie or "").strip():
        return {"login_state": "invalid", "message": "Cookie 为空"}

    try:
        from modules.crawler_client import WeiboClient

        return WeiboClient(cookie=str(cookie or "")).check_cookie(super_topic=super_topic)
    except Exception as err:
        return {
            "login_state": "network_error",
            "message": "Cookie 检测失败",
            "suggestion": f"请确认网络正常并重新获取 Cookie 后重试。错误类型：{type(err).__name__}",
        }
