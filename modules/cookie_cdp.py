"""Reads weibo login cookies out of a browser's DevTools endpoint.

This is the recommended path for getting a cookie, because Chrome and Edge 127+
encrypt their on-disk cookie store with App-Bound Encryption and the
browser_cookie3 fallback can no longer decrypt it on most updated machines. A
browser launched with --remote-debugging-port will hand its cookies over
directly.

Two ways in, tried in order:

* ``Network.getCookies`` on a page target, scoped to the weibo URLs. Preferred,
  because it returns exactly the cookies that page would send.
* ``Storage.getCookies`` on the browser target, which returns everything and is
  filtered here. Used when no page target exists.

Every function that reaches the network takes a ``fetch_json`` parameter so the
discovery logic can be tested with canned responses -- it used to call urlopen
directly, which is why this path had no tests at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.request import Request, urlopen

from modules.cookie_cdp_ws import CdpWebSocket

CDP_ENV_VAR = "WEIBO_COOKIE_CDP_URL"

CDP_BROWSER_PORTS = {"edge": 9222, "chrome": 9223}

CDP_DEFAULT_ENDPOINTS = (
    "http://127.0.0.1:9222",
    "http://127.0.0.1:9223",
)

# Cookies are requested for both hosts because the login token is set on the
# apex domain while some flows land on www.
WEIBO_COOKIE_URLS = ("https://weibo.com/", "https://www.weibo.com/")

# Without this the tool would happily return a cookie jar that cannot log in.
WEIBO_LOGIN_COOKIE_NAMES = {"SUB"}

DISCOVERY_TIMEOUT_SECONDS = 1.5
NEW_TAB_TIMEOUT_SECONDS = 2.5

FetchJson = Callable[[Any, float], Any]


def fetch_json(url_or_request: Any, timeout: float) -> dict | list:
    with urlopen(url_or_request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_cookie_from_cdp(
    browser: str | None = None,
    *,
    endpoints: list[str] | None = None,
    fetch: FetchJson = fetch_json,
    connect=None,
) -> tuple[str, str | None]:
    """Try each candidate endpoint; return ``(cookie, error)``.

    A cookie is returned with no error, or an empty string with every endpoint's
    failure joined together, so the caller can tell the user what to fix.
    """
    label = browser_label(browser)
    errors: list[str] = []
    for endpoint in endpoints if endpoints is not None else cdp_endpoints(browser):
        cookie, err = read_cookie_from_endpoint(endpoint, label, fetch=fetch, connect=connect)
        if cookie:
            return cookie, None
        if err:
            errors.append(f"{endpoint}: {err}")
    if errors:
        return "", "；".join(errors)
    return "", "未配置 CDP 调试端口"


def cdp_endpoints(browser: str | None = None) -> list[str]:
    """Where to look for a debug endpoint, most specific first."""
    configured = os.environ.get(CDP_ENV_VAR, "").strip()
    if configured:
        return [configured.rstrip("/")]
    if browser:
        port = CDP_BROWSER_PORTS.get(_normalize(browser), CDP_BROWSER_PORTS["edge"])
        return [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    return [endpoint.rstrip("/") for endpoint in CDP_DEFAULT_ENDPOINTS]


def read_cookie_from_endpoint(
    endpoint: str,
    label: str = "浏览器",
    *,
    fetch: FetchJson = fetch_json,
    connect=None,
) -> tuple[str, str | None]:
    try:
        version = fetch(f"{endpoint}/json/version", DISCOVERY_TIMEOUT_SECONDS)
    except Exception as exc:
        return "", f"未连接到调试端口（{type(exc).__name__}: {exc}）"
    if not isinstance(version, dict):
        return "", "CDP json/version 返回格式异常"

    target_errors: list[str] = []
    for ws_url in page_websockets(endpoint, fetch=fetch):
        cookie, err = cookies_from_page_target(ws_url, connect=connect)
        if cookie:
            return cookie, None
        if err:
            target_errors.append(err)

    browser_ws = str(version.get("webSocketDebuggerUrl") or "")
    if not browser_ws:
        browser_err = "json/version 未提供 browser websocket"
    else:
        cookie, browser_err = cookies_from_browser_target(browser_ws, connect=connect)
        if cookie:
            return cookie, None

    # Only the last couple of target errors are worth showing; a browser with
    # many tabs would otherwise bury the actionable advice.
    details = [detail for detail in (*target_errors[-2:], browser_err) if detail]
    suffix = "（" + "；".join(details) + "）" if details else ""
    return "", f"CDP 已连接，但没有读到微博登录态 Cookie；请在调试 {label} 窗口登录微博后重试。{suffix}"


def page_websockets(endpoint: str, *, fetch: FetchJson = fetch_json) -> list[str]:
    """WebSocket URLs of page targets, opening a weibo tab if there are none.

    Opening a tab is a visible side effect -- the user sees a window appear --
    but without a page target there is nothing to ask for cookies.
    """
    urls: list[str] = []
    try:
        targets = fetch(f"{endpoint}/json/list", DISCOVERY_TIMEOUT_SECONDS)
    except Exception:
        targets = []
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, dict):
                continue
            ws_url = str(target.get("webSocketDebuggerUrl") or "")
            if ws_url and str(target.get("type") or "") in {"page", "webview"}:
                urls.append(ws_url)
    if urls:
        return urls

    try:
        request = Request(f"{endpoint}/json/new?https://weibo.com/", method="PUT")
        target = fetch(request, NEW_TAB_TIMEOUT_SECONDS)
        ws_url = str(target.get("webSocketDebuggerUrl") or "") if isinstance(target, dict) else ""
        if ws_url:
            urls.append(ws_url)
    except Exception:
        pass
    return urls


def cookies_from_page_target(ws_url: str, *, connect=None) -> tuple[str, str | None]:
    try:
        with CdpWebSocket(ws_url, connect=connect) as ws:
            # Some builds answer getCookies without this; others need it.
            with suppress(Exception):
                ws.call("Network.enable")
            result = ws.call("Network.getCookies", {"urls": list(WEIBO_COOKIE_URLS)})
        cookie = cookies_to_header(result.get("cookies", []))
        if cookie:
            return cookie, None
        return "", "Network.getCookies: 未找到微博登录态 Cookie"
    except Exception as exc:
        return "", f"Network.getCookies: {type(exc).__name__}: {exc}"


def cookies_from_browser_target(ws_url: str, *, connect=None) -> tuple[str, str | None]:
    try:
        with CdpWebSocket(ws_url, connect=connect) as ws:
            result = ws.call("Storage.getCookies")
        cookie = cookies_to_header(result.get("cookies", []))
        if cookie:
            return cookie, None
        return "", "Storage.getCookies: 未找到微博登录态 Cookie"
    except Exception as exc:
        return "", f"Storage.getCookies: {type(exc).__name__}: {exc}"


def cookies_to_header(cookies: list[dict]) -> str:
    """Build a Cookie header from CDP records, or "" if login state is absent.

    A name can appear more than once with different paths; the root-path entry
    is the one the browser would send to weibo.com, so it wins.
    """
    selected: dict[str, tuple[int, str]] = {}
    for item in cookies:
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if not name or not value:
            continue
        if not domain_applies_to_weibo(str(item.get("domain") or "")):
            continue
        rank = cookie_rank(item)
        previous = selected.get(name)
        if previous is None or rank > previous[0]:
            selected[name] = (rank, value)
    pairs = {name: value for name, (_, value) in selected.items()}
    if not WEIBO_LOGIN_COOKIE_NAMES.issubset(pairs.keys()):
        return ""
    return "; ".join(f"{name}={value}" for name, value in pairs.items())


def domain_applies_to_weibo(domain: str) -> bool:
    return domain.lstrip(".").lower() == "weibo.com"


def cookie_rank(item: dict) -> int:
    return 2 if str(item.get("path") or "") in {"", "/"} else 1


def browser_label(browser: str | None) -> str:
    if not browser:
        return "浏览器"
    return "Chrome" if _normalize(browser) == "chrome" else "Edge"


def _normalize(browser: str | None) -> str:
    return "chrome" if str(browser or "").strip().lower() == "chrome" else "edge"
