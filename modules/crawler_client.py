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
from modules.weibo_html_parser import extract_feed_html_from_page, parse_posts_from_html
from modules.weibo_url import parse_super_topic_id

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

    def check_cookie(self, super_topic: str | None = None) -> dict[str, Any]:
        if not self.cookie:
            return {
                "login_state": "invalid",
                "message": "Cookie 为空",
                "suggestion": "请先自动获取 Cookie，或从已登录微博网页手动复制 Cookie。",
            }
        topic_id = parse_super_topic_id(str(super_topic or ""))
        if topic_id:
            return self._check_super_topic_pages(topic_id)

        try:
            url = "https://weibo.com/"
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

    def _check_super_topic_pages(self, topic_id: str) -> dict[str, Any]:
        if "SUB=" not in self.cookie and "MLOGIN=1" not in self.cookie:
            return {
                "login_state": "unknown",
                "checked_pages": 0,
                "parsed_posts": 0,
                "page_results": [],
                "message": "Cookie 可能不是完整登录态",
                "suggestion": "未检测到关键登录字段 SUB。建议重新自动读取，或手动复制 weibo.com 请求里的完整 Cookie。",
            }

        url = f"https://weibo.com/p/{topic_id}/super_index"
        page_results: list[dict[str, Any]] = []
        network_errors = 0
        for page in range(1, 4):
            try:
                response = self._request(
                    "GET",
                    url,
                    params={"page": str(page)},
                    headers={"Referer": "https://weibo.com/"},
                )
                parsed_posts, valid_posts = _count_posts_in_super_page(response.text)
                page_results.append(
                    {"page": page, "parsed_posts": parsed_posts, "valid_posts": valid_posts, "status": "ok"}
                )
                if valid_posts > 0:
                    return {
                        "login_state": "valid",
                        "checked_pages": page,
                        "parsed_posts": valid_posts,
                        "raw_posts": parsed_posts,
                        "page_results": page_results,
                        "message": f"Cookie 可用，检测第 {page} 页解析到 {valid_posts} 条有效帖子。",
                        "suggestion": "可以继续开始抓取。",
                    }
            except VisitorSystemError:
                return {
                    "login_state": "visitor",
                    "checked_pages": page,
                    "parsed_posts": 0,
                    "page_results": page_results + [{"page": page, "parsed_posts": 0, "valid_posts": 0, "status": "visitor"}],
                    "message": "微博返回访客验证",
                    "suggestion": "请在调试浏览器中完成微博验证或重新登录后，再读取 Cookie。",
                }
            except CookieInvalidError:
                return {
                    "login_state": "invalid",
                    "checked_pages": page,
                    "parsed_posts": 0,
                    "page_results": page_results + [{"page": page, "parsed_posts": 0, "valid_posts": 0, "status": "invalid"}],
                    "message": "Cookie 可能无权限",
                    "suggestion": "请重新登录微博网页后再获取 Cookie。",
                }
            except WeiboStatsError as err:
                network_errors += 1
                page_results.append({"page": page, "parsed_posts": 0, "valid_posts": 0, "status": "network_error", "error": str(err)})
            except Exception as err:
                page_results.append({"page": page, "parsed_posts": 0, "valid_posts": 0, "status": "parse_error", "error": type(err).__name__})

        if network_errors >= 3:
            return {
                "login_state": "network_error",
                "checked_pages": 3,
                "parsed_posts": 0,
                "page_results": page_results,
                "message": "连续检测 3 页都请求失败",
                "suggestion": "请确认网络可访问微博网页后重试。",
            }
        return {
            "login_state": "invalid",
            "checked_pages": 3,
            "parsed_posts": 0,
            "page_results": page_results,
            "message": "连续检测 3 页均未解析到有效帖子或帖子互动数据均为 0",
            "suggestion": "请在调试浏览器中打开目标超话，确认能看到帖子且点赞/评论/转发数据正常显示后，再重新读取 Cookie。",
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


def _count_posts_in_super_page(page_html: str) -> tuple[int, int]:
    try:
        feed_html = extract_feed_html_from_page(page_html)
        posts = parse_posts_from_html(feed_html)
    except Exception:
        return 0, 0
    parsed_posts = [post for post in posts if str(post.get("post_id") or "").strip()]
    valid_posts = [post for post in parsed_posts if _post_has_valid_interaction_data(post)]
    return len(parsed_posts), len(valid_posts)


def _post_has_valid_interaction_data(post: dict[str, Any]) -> bool:
    for key in ("likes", "comments", "reposts", "engagement_total"):
        try:
            if int(float(post.get(key) or 0)) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False

