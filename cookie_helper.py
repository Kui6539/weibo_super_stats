from __future__ import annotations

import os
from pathlib import Path
import re


class CookieFetchError(Exception):
    pass


def extract_cookie_from_text(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""

    # 1) 原始请求头格式: Cookie: a=1; b=2
    m = re.search(r"(?im)^\s*cookie\s*:\s*(.+?)\s*$", raw)
    if m:
        return m.group(1).strip().strip("'\"")

    # 2) cURL 片段: -H 'cookie: a=1; b=2'
    m = re.search(r"-H\s+['\"]cookie:\s*(.+?)['\"]", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 3) cURL 片段: -b 'a=1; b=2' 或 --cookie 'a=1; b=2'
    m = re.search(r"(?:-b|--cookie)\s+['\"](.+?)['\"]", raw, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 4) JSON/对象片段: "Cookie": "a=1; b=2"
    m = re.search(r'(?i)"cookie"\s*:\s*"(.+?)"', raw)
    if m:
        return m.group(1).strip()

    return ""


def get_weibo_cookie_header() -> str:
    try:
        import browser_cookie3 as bc3
    except Exception as exc:  # noqa: BLE001
        raise CookieFetchError(
            "缺少 browser-cookie3 依赖，请先运行 run.bat 安装依赖。"
        ) from exc

    # 某些环境下 shadowcopy 会要求管理员权限，禁用以提高普通用户可用性。
    try:
        bc3.shadowcopy = None
    except Exception:  # noqa: BLE001
        pass

    browser_funcs = [("Edge", bc3.edge), ("Chrome", bc3.chrome)]

    last_err: str | None = None
    for browser_name, loader in browser_funcs:
        # 1) 先走库的默认查找
        for domain in ("weibo.com", "m.weibo.cn"):
            try:
                jar = loader(domain_name=domain)
                cookie = _jar_to_cookie_header(jar)
                if cookie:
                    return cookie
            except Exception as exc:  # noqa: BLE001
                last_err = f"{browser_name}({domain}): {exc}"

        # 2) 遍历各 profile 的 cookie 文件，解决“登录在非默认 profile”问题
        for cookie_file in _iter_cookie_files(browser_name):
            for domain in ("weibo.com", "m.weibo.cn"):
                try:
                    jar = loader(cookie_file=str(cookie_file), domain_name=domain)
                    cookie = _jar_to_cookie_header(jar)
                    if cookie:
                        return cookie
                except Exception as exc:  # noqa: BLE001
                    last_err = f"{browser_name} {cookie_file.name} ({domain}): {exc}"

    extra = f"（最后错误: {last_err}）" if last_err else ""
    raise CookieFetchError(
        "未能从 Edge/Chrome 读取到 weibo.com Cookie。请先在浏览器登录微博，再重试。"
        + extra
    )


def _jar_to_cookie_header(jar) -> str:
    pairs: dict[str, str] = {}
    for item in jar:
        domain = getattr(item, "domain", "") or ""
        name = getattr(item, "name", "") or ""
        value = getattr(item, "value", "") or ""
        if not name or not value:
            continue
        if "weibo.com" not in domain and ".weibo.cn" not in domain:
            continue
        pairs[name] = value
    if not pairs:
        return ""
    # 按键名排序，方便稳定复现与排查。
    return "; ".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))


def _iter_cookie_files(browser_name: str) -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return []

    browser_map = {
        "Edge": Path(local_app_data) / "Microsoft" / "Edge" / "User Data",
        "Chrome": Path(local_app_data) / "Google" / "Chrome" / "User Data",
    }
    root = browser_map.get(browser_name)
    if not root or not root.exists():
        return []

    profile_names: list[str] = ["Default"]
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if p.name.startswith("Profile "):
            profile_names.append(p.name)

    files: list[Path] = []
    for profile in sorted(set(profile_names)):
        base = root / profile
        for rel in ("Network/Cookies", "Cookies"):
            f = base / rel
            if f.exists() and f.is_file():
                files.append(f)
    return files
