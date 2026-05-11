from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from core.errors import (
    CookieInvalidError,
    ParseError,
    VisitorSystemError,
    WeiboStatsError,
)

WEIBO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class WeiboClient:
    def __init__(
        self,
        cookie: str = "",
        timeout: tuple[int, int] | int = (5, 20),
        retry: int = 2,
        pause_seconds: float = 0,
    ) -> None:
        self.cookie = cookie
        self.timeout = timeout
        self.retry = max(0, int(retry))
        self.pause_seconds = max(0.0, float(pause_seconds or 0))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": WEIBO_USER_AGENT})
        if cookie:
            self.session.headers.update({"Cookie": cookie})

    def get_html(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        response = self._request("GET", url, params=params, headers=headers)
        text = response.text
        if looks_like_weibo_visitor(text, response.url):
            raise VisitorSystemError()
        return text

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        response = self._request("GET", url, params=params, headers=headers)
        if looks_like_weibo_visitor(response.text, response.url):
            raise VisitorSystemError()
        try:
            data = response.json()
        except ValueError as err:
            raise ParseError("微博接口返回的 JSON 无法解析", "请稍后重试，或检查 Cookie 是否有效") from err
        if not isinstance(data, dict):
            raise ParseError("微博接口返回格式异常", "请稍后重试")
        return data

    def download_file(self, url: str, path: Path) -> Path:
        response = self._request("GET", url, stream=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    fh.write(chunk)
        return path

    def check_cookie(self, super_topic: str | None = None) -> dict[str, str]:
        if not self.cookie:
            return {
                "login_state": "invalid",
                "message": "Cookie 为空",
                "suggestion": "请先自动获取 Cookie，或从已登录微博网页手动复制 Cookie。",
            }
        url = "https://weibo.com/"
        if super_topic and str(super_topic).startswith("100808"):
            url = f"https://weibo.com/p/{super_topic}/super_index"
        try:
            response = self._request("GET", url, headers={"Referer": "https://weibo.com/"})
        except VisitorSystemError:
            return {
                "login_state": "visitor",
                "message": "微博返回访客验证",
                "suggestion": "请在 weibo.com 重新登录后获取 Cookie，不要使用访客态 Cookie。",
            }
        except WeiboStatsError:
            return {
                "login_state": "network_error",
                "message": "网络错误",
                "suggestion": "请确认网络可访问微博网页后重试。",
            }
        if looks_like_weibo_visitor(response.text[:200000], response.url):
            return {
                "login_state": "visitor",
                "message": "微博返回访客验证",
                "suggestion": "请在 weibo.com 重新登录后获取 Cookie，不要使用访客态 Cookie。",
            }
        if response.status_code in {401, 403}:
            return {
                "login_state": "invalid",
                "message": "Cookie 可能无权限",
                "suggestion": "请重新登录微博网页后再获取 Cookie。",
            }
        if "SUB=" in self.cookie and response.status_code < 400:
            return {
                "login_state": "valid",
                "message": "Cookie 可用",
                "suggestion": "可以继续开始抓取。",
            }
        return {
            "login_state": "unknown",
            "message": "Cookie 可能失效",
            "suggestion": "未检测到关键登录字段 SUB。建议手动复制 weibo.com/ajax 请求里的完整 Cookie。",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retry + 1):
            if self.pause_seconds and attempt > 0:
                time.sleep(self.pause_seconds)
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as err:
                last_error = err
                time.sleep(min(1.5 * (attempt + 1), 5))
                continue
            if looks_like_weibo_visitor(response.text[:200000], response.url):
                raise VisitorSystemError()
            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    raise CookieInvalidError()
                last_error = WeiboStatsError(f"微博请求失败，HTTP {response.status_code}")
                time.sleep(min(1.5 * (attempt + 1), 5))
                continue
            return response
        raise WeiboStatsError("网络请求失败", "请确认网络可访问微博网页后重试") from last_error


def looks_like_weibo_visitor(text: str, url: str = "") -> bool:
    lowered = (text + "\n" + url).lower()
    return any(
        marker.lower() in lowered
        for marker in (
            "Sina Visitor System",
            "passport.weibo.com/visitor",
            "微博返回访客验证",
            "visitor/genvisitor",
            "访问验证",
        )
    )

