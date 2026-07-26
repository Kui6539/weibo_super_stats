from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from modules.cookie_cdp import (
    cdp_endpoints as _cdp_endpoints,
)
from modules.cookie_cdp import (
    domain_applies_to_weibo as _cookie_domain_applies_to_weibo,
)
from modules.cookie_cdp import (
    fetch_json as _fetch_json,
)
from modules.cookie_cdp import (
    read_cookie_from_cdp,
)
from modules.cookie_cdp_ws import CdpWebSocket as _CdpWebSocket
from modules.cookie_parser import extract_cookie_from_text, mask_cookie_for_log, normalize_cookie

CDP_BROWSER_DEFAULTS = {
    "edge": {"label": "Edge", "profile_dir": ".edge_cdp_profile", "port": 9222},
    "chrome": {"label": "Chrome", "profile_dir": ".chrome_cdp_profile", "port": 9223},
}
CDP_DEFAULT_ENDPOINTS = (
    "http://127.0.0.1:9222",
    "http://localhost:9222",
    "http://127.0.0.1:9223",
    "http://localhost:9223",
)
CDP_ENV_VAR = "WEIBO_COOKIE_CDP_URL"
WEIBO_LOGIN_COOKIE_NAMES = {"SUB"}
WEIBO_COOKIE_URLS = (
    "https://weibo.com/",
    "https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index",
)
__all__ = [
    "CookieFetchError",
    "browser_display_name",
    "cdp_profile_dirs",
    "clear_cdp_debug_cache",
    "close_debug_browser",
    "close_edge_debug_browser",
    "extract_cookie_from_text",
    "get_weibo_cookie_header",
    "launch_debug_browser",
    "launch_edge_debug_browser",
    "mask_cookie_for_log",
    "normalize_browser_name",
    "normalize_cookie",
]


class CookieFetchError(Exception):
    pass


def normalize_browser_name(browser: str | None) -> str:
    value = str(browser or "").strip().lower()
    if value in {"chrome", "google", "google-chrome", "google chrome"}:
        return "chrome"
    return "edge"


def browser_display_name(browser: str | None) -> str:
    return str(CDP_BROWSER_DEFAULTS[normalize_browser_name(browser)]["label"])


def cdp_profile_dirs(root_dir: Path | None = None) -> dict[str, Path]:
    root = (root_dir or Path(__file__).resolve().parent).resolve()
    return {
        browser: root / str(defaults["profile_dir"])
        for browser, defaults in CDP_BROWSER_DEFAULTS.items()
    }


def clear_cdp_debug_cache(root_dir: Path | None = None, close_browsers: bool = True) -> dict[str, object]:
    root = (root_dir or Path(__file__).resolve().parent).resolve()
    profile_dirs = cdp_profile_dirs(root)
    closed_browsers: list[str] = []
    deleted: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    if close_browsers:
        for browser in profile_dirs:
            if close_debug_browser(browser):
                closed_browsers.append(browser_display_name(browser))
        if closed_browsers:
            time.sleep(0.6)

    for browser, profile_dir in profile_dirs.items():
        label = browser_display_name(browser)
        expected_name = str(CDP_BROWSER_DEFAULTS[browser]["profile_dir"])
        target = profile_dir.resolve()
        item = {"browser": label, "path": str(target)}
        if target.parent != root or target.name != expected_name:
            errors.append({**item, "error": "拒绝删除非固定 CDP profile 目录"})
            continue
        if not target.exists():
            missing.append(item)
            continue
        if not target.is_dir():
            errors.append({**item, "error": "目标不是文件夹"})
            continue
        remove_error = _remove_profile_dir_with_retry(target)
        if remove_error:
            errors.append({**item, "error": str(remove_error)})
        else:
            deleted.append(item)

    return {
        "deleted": deleted,
        "missing": missing,
        "errors": errors,
        "closed_browsers": closed_browsers,
    }


def get_weibo_cookie_header(browser: str | None = None) -> str:
    selected_browser = normalize_browser_name(browser) if browser else ""
    cdp_cookie, cdp_err = _try_get_cookie_header_from_cdp(selected_browser or None)
    if cdp_cookie:
        return cdp_cookie

    try:
        import browser_cookie3 as bc3
    except Exception as exc:
        raise CookieFetchError(
            "缺少 browser-cookie3 依赖，请先运行 pip install -r requirements.txt 安装依赖。"
        ) from exc

    browser_funcs = _browser_loaders(bc3, selected_browser)
    domains = ("weibo.com",)
    read_errors: list[str] = []
    no_cookie_errors: list[str] = []

    for browser_name, loader in browser_funcs:
        for domain in domains:
            cookie, err = _try_loader(loader, domain_name=domain)
            if cookie:
                return cookie
            if err:
                _append_attempt_error(f"{browser_name} 默认({domain}): {err}", read_errors, no_cookie_errors)

        # 遍历各 profile 的 cookie 文件，解决“登录在非默认 profile”问题。
        # 先直接读；若数据库被浏览器占用，再复制 Cookies/WAL/SHM 到临时目录读取。
        for source in _iter_cookie_sources(browser_name):
            for domain in domains:
                cookie, err = _try_loader(loader, cookie_file=str(source.path), domain_name=domain)
                if cookie:
                    return cookie
                if err:
                    _append_attempt_error(
                        f"{browser_name} {source.label}({domain}): {err}",
                        read_errors,
                        no_cookie_errors,
                    )

            copied_path: Path | None = None
            temp_dir: Path | None = None
            try:
                copied_path, temp_dir = _copy_cookie_db_to_temp(source.path)
                for domain in domains:
                    cookie, err = _try_loader(loader, cookie_file=str(copied_path), domain_name=domain)
                    if cookie:
                        return cookie
                    if err:
                        _append_attempt_error(
                            f"{browser_name} {source.label} 临时副本({domain}): {err}",
                            read_errors,
                            no_cookie_errors,
                        )
            except Exception as exc:
                _append_attempt_error(
                    f"{browser_name} {source.label} 临时副本: {type(exc).__name__}: {exc}",
                    read_errors,
                    no_cookie_errors,
                )
            finally:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

    extra = ""
    if read_errors:
        extra = "（关键错误: " + "；".join(read_errors[-4:]) + "）"
        cdp_hint = f"；CDP 检查: {cdp_err}" if cdp_err else ""
        raise CookieFetchError(
            f"检测到 {_browser_error_label(selected_browser)} 的 Cookie 数据库正在被占用或需要更高权限，当前普通权限无法读取。"
            "推荐点击页面里的“打开调试浏览器”，在新窗口登录微博后再点“自动获取 Cookie”。"
            "也可以使用页面里的“读取剪贴板/识别粘贴内容”手动导入。"
            + cdp_hint
            + extra
        )
    if no_cookie_errors:
        extra = "（最近检查: " + "；".join(no_cookie_errors[-4:]) + "）"
    raise CookieFetchError(
        f"未能从 {_browser_error_label(selected_browser)} 读取到微博登录态 Cookie。请确认已在所选浏览器窗口登录微博；"
        "若仍失败，请点击页面里的“打开调试浏览器”，在新窗口登录微博后重试，"
        "或使用页面里的“读取剪贴板/识别粘贴内容”。"
        + extra
    )


def launch_debug_browser(browser: str | None = None, profile_dir: Path | None = None, port: int | None = None) -> str:
    browser_key = normalize_browser_name(browser)
    browser_label = browser_display_name(browser_key)
    browser_exe = _find_browser_exe(browser_key)
    if not browser_exe:
        raise CookieFetchError(f"未找到 {browser_label}，可切换其他浏览器或改用手动粘贴 Cookie。")

    profile_path = profile_dir or cdp_profile_dirs()[browser_key]
    profile_path.mkdir(parents=True, exist_ok=True)
    debug_port = int(port or CDP_BROWSER_DEFAULTS[browser_key]["port"])
    endpoint = f"http://127.0.0.1:{debug_port}"
    args = [
        str(browser_exe),
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--new-window",
        "https://weibo.com/",
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return endpoint


def launch_edge_debug_browser(profile_dir: Path | None = None, port: int = 9222) -> str:
    return launch_debug_browser("edge", profile_dir=profile_dir, port=port)


def close_debug_browser(browser: str | None = None) -> bool:
    for endpoint in _cdp_endpoints(normalize_browser_name(browser) if browser else None):
        try:
            version = _fetch_json(f"{endpoint}/json/version", 1.5)
        except Exception:
            continue
        if not isinstance(version, dict):
            continue
        browser_ws = str(version.get("webSocketDebuggerUrl") or "")
        if not browser_ws:
            continue
        try:
            with _CdpWebSocket(browser_ws) as ws:
                ws.call("Browser.close")
            return True
        except Exception:
            continue
    return False


def close_edge_debug_browser() -> bool:
    return close_debug_browser("edge")


def _remove_profile_dir_with_retry(path: Path) -> Exception | None:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            shutil.rmtree(path)
            return None
        except FileNotFoundError:
            return None
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.35)
    return last_error


def _browser_loaders(browser_cookie3_module, browser: str) -> list[tuple[str, object]]:
    loaders = {
        "edge": [("Edge", browser_cookie3_module.edge)],
        "chrome": [("Chrome", browser_cookie3_module.chrome)],
    }
    if browser:
        return loaders[normalize_browser_name(browser)]
    return [*loaders["edge"], *loaders["chrome"]]


def _browser_error_label(browser: str) -> str:
    return browser_display_name(browser) if browser else "Edge/Chrome"


def _find_browser_exe(browser: str | None) -> Path | None:
    return _find_chrome_exe() if normalize_browser_name(browser) == "chrome" else _find_edge_exe()


def _find_edge_exe() -> Path | None:
    found = shutil.which("msedge")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _find_chrome_exe() -> Path | None:
    for command in ("chrome", "chrome.exe", "google-chrome"):
        found = shutil.which(command)
        if found:
            return Path(found)
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _try_get_cookie_header_from_cdp(browser: str | None = None) -> tuple[str, str | None]:
    """Kept as the name other modules import; the logic lives in modules.cookie_cdp."""
    return read_cookie_from_cdp(browser)


def _try_loader(loader, **kwargs) -> tuple[str, str | None]:
    try:
        jar = loader(**kwargs)
        cookie = _jar_to_cookie_header(jar)
        if cookie:
            return cookie, None
        return "", "未找到匹配的 weibo.com Cookie"
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def _append_attempt_error(message: str, read_errors: list[str], no_cookie_errors: list[str]) -> None:
    if _looks_like_read_error(message):
        read_errors.append(message)
    else:
        no_cookie_errors.append(message)


def _looks_like_read_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "unable to read database file",
            "requiresadminerror",
            "permissionerror",
            "winerror 32",
            "locked",
            "fileaccessdenied",
            "database is locked",
            "access is denied",
            "另一个程序正在使用",
            "无法访问",
        )
    )


def _jar_to_cookie_header(jar) -> str:
    pairs: dict[str, str] = {}
    for item in jar:
        domain = getattr(item, "domain", "") or ""
        name = getattr(item, "name", "") or ""
        value = getattr(item, "value", "") or ""
        if not name or not value:
            continue
        if not _cookie_domain_applies_to_weibo(domain):
            continue
        pairs[name] = value
    if not pairs:
        return ""
    if not _has_weibo_login_cookie(pairs):
        return ""
    return _pairs_to_header(pairs)


def _has_weibo_login_cookie(pairs: dict[str, str]) -> bool:
    return any(name in pairs for name in WEIBO_LOGIN_COOKIE_NAMES) or pairs.get("MLOGIN") == "1"


def _pairs_to_header(pairs: dict[str, str]) -> str:
    # 按键名排序，方便稳定复现与排查。
    return "; ".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))


class CookieSource:
    def __init__(self, path: Path, label: str) -> None:
        self.path = path
        self.label = label


def _iter_cookie_sources(browser_name: str) -> list[CookieSource]:
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
    profile_names.extend(_profile_names_from_local_state(root))
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if p.name.startswith("Profile ") or p.name.endswith("Profile"):
            profile_names.append(p.name)

    sources: list[CookieSource] = []
    seen: set[Path] = set()
    for profile in sorted(set(profile_names)):
        base = root / profile
        for rel in ("Network/Cookies", "Cookies"):
            f = base / rel
            resolved = f.resolve()
            if f.exists() and f.is_file() and resolved not in seen:
                sources.append(CookieSource(f, f"{profile}/{rel}"))
                seen.add(resolved)
    return sources


def _profile_names_from_local_state(root: Path) -> list[str]:
    local_state = root / "Local State"
    if not local_state.exists():
        return []
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
    except Exception:
        return []
    info_cache = data.get("profile", {}).get("info_cache", {})
    if not isinstance(info_cache, dict):
        return []
    return [str(name) for name in info_cache if name]


def _copy_cookie_db_to_temp(cookie_file: Path) -> tuple[Path, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="weibo_cookie_"))
    target = temp_dir / "Cookies"
    shutil.copy2(cookie_file, target)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(cookie_file) + suffix)
        if sidecar.exists() and sidecar.is_file():
            shutil.copy2(sidecar, Path(str(target) + suffix))
    return target, temp_dir
