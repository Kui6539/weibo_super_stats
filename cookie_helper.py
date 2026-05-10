from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CDP_DEFAULT_ENDPOINTS = ("http://127.0.0.1:9222", "http://localhost:9222")
CDP_ENV_VAR = "WEIBO_COOKIE_CDP_URL"
WEIBO_LOGIN_COOKIE_NAMES = {"SUB"}
WEIBO_COOKIE_URLS = (
    "https://weibo.com/",
    "https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index",
)


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
    cdp_cookie, cdp_err = _try_get_cookie_header_from_cdp()
    if cdp_cookie:
        return cdp_cookie

    try:
        import browser_cookie3 as bc3
    except Exception as exc:
        raise CookieFetchError(
            "缺少 browser-cookie3 依赖，请先运行 pip install -r requirements.txt 安装依赖。"
        ) from exc

    browser_funcs = [("Edge", bc3.edge), ("Chrome", bc3.chrome)]
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
            "检测到 Edge/Chrome 的 Cookie 数据库正在被占用或需要更高权限，当前普通权限无法读取。"
            "推荐点击页面里的“打开调试 Edge”，在新窗口登录微博后再点“自动获取 Cookie”。"
            "也可以使用页面里的“读取剪贴板/识别粘贴内容”手动导入。"
            + cdp_hint
            + extra
        )
    if no_cookie_errors:
        extra = "（最近检查: " + "；".join(no_cookie_errors[-4:]) + "）"
    raise CookieFetchError(
        "未能从 Edge/Chrome 读取到微博登录态 Cookie。请确认已在浏览器窗口登录微博；"
        "若仍失败，请点击页面里的“打开调试 Edge”，在新窗口登录微博后重试，"
        "或使用页面里的“读取剪贴板/识别粘贴内容”。"
        + extra
    )


def launch_edge_debug_browser(profile_dir: Path | None = None, port: int = 9222) -> str:
    edge_exe = _find_edge_exe()
    if not edge_exe:
        raise CookieFetchError("未找到 Microsoft Edge，可改用手动粘贴 Cookie。")

    profile_path = profile_dir or (Path.cwd() / ".edge_cdp_profile")
    profile_path.mkdir(parents=True, exist_ok=True)
    endpoint = f"http://127.0.0.1:{port}"
    args = [
        str(edge_exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--new-window",
        "https://weibo.com/",
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return endpoint


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


def _try_get_cookie_header_from_cdp() -> tuple[str, str | None]:
    endpoints = _cdp_endpoints()
    errors: list[str] = []
    for endpoint in endpoints:
        cookie, err = _try_cdp_endpoint(endpoint)
        if cookie:
            return cookie, None
        if err:
            errors.append(f"{endpoint}: {err}")
    if errors:
        return "", "；".join(errors)
    return "", "未配置 CDP 调试端口"


def _cdp_endpoints() -> list[str]:
    configured = os.environ.get(CDP_ENV_VAR, "").strip()
    if configured:
        return [configured.rstrip("/")]
    return [endpoint.rstrip("/") for endpoint in CDP_DEFAULT_ENDPOINTS]


def _try_cdp_endpoint(endpoint: str) -> tuple[str, str | None]:
    try:
        version = _fetch_json(f"{endpoint}/json/version", timeout=1.5)
    except Exception as exc:
        return "", f"未连接到调试端口（{type(exc).__name__}: {exc}）"
    if not isinstance(version, dict):
        return "", "CDP json/version 返回格式异常"

    target_errors: list[str] = []
    for ws_url in _iter_cdp_page_websockets(endpoint):
        cookie, err = _try_cdp_cookies_from_page_ws(ws_url)
        if cookie:
            return cookie, None
        if err:
            target_errors.append(err)

    browser_ws = str(version.get("webSocketDebuggerUrl") or "")
    browser_err = ""
    if browser_ws:
        cookie, browser_err = _try_cdp_cookies_from_browser_ws(browser_ws)
        if cookie:
            return cookie, None
    else:
        browser_err = "json/version 未提供 browser websocket"

    details = [*target_errors[-2:], browser_err]
    return "", "CDP 已连接，但没有读到微博登录态 Cookie；请在调试 Edge 窗口登录微博后重试。" + (
        "（" + "；".join(d for d in details if d) + "）" if details else ""
    )


def _iter_cdp_page_websockets(endpoint: str) -> list[str]:
    urls: list[str] = []
    try:
        targets = _fetch_json(f"{endpoint}/json/list", timeout=1.5)
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
        req = Request(f"{endpoint}/json/new?https://weibo.com/", method="PUT")
        target = _fetch_json(req, timeout=2.5)
        if isinstance(target, dict):
            ws_url = str(target.get("webSocketDebuggerUrl") or "")
        else:
            ws_url = ""
        if ws_url:
            urls.append(ws_url)
    except Exception:
        pass
    return urls


def _try_cdp_cookies_from_page_ws(ws_url: str) -> tuple[str, str | None]:
    try:
        with _CdpWebSocket(ws_url) as ws:
            with suppress(Exception):
                ws.call("Network.enable")
            result = ws.call("Network.getCookies", {"urls": list(WEIBO_COOKIE_URLS)})
        cookie = _cdp_cookies_to_header(result.get("cookies", []))
        if cookie:
            return cookie, None
        return "", "Network.getCookies: 未找到微博登录态 Cookie"
    except Exception as exc:
        return "", f"Network.getCookies: {type(exc).__name__}: {exc}"


def _try_cdp_cookies_from_browser_ws(ws_url: str) -> tuple[str, str | None]:
    errors: list[str] = []
    try:
        with _CdpWebSocket(ws_url) as ws:
            result = ws.call("Storage.getCookies")
        cookie = _cdp_cookies_to_header(result.get("cookies", []))
        if cookie:
            return cookie, None
        errors.append("Storage.getCookies: 未找到微博登录态 Cookie")
    except Exception as exc:
        errors.append(f"Storage.getCookies: {type(exc).__name__}: {exc}")
    return "", "；".join(errors)


def _cdp_cookies_to_header(cookies: list[dict]) -> str:
    selected: dict[str, tuple[int, str]] = {}
    for item in cookies:
        domain = str(item.get("domain") or "")
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if not name or not value:
            continue
        if not _cookie_domain_applies_to_weibo(domain):
            continue
        rank = _cookie_rank_for_weibo(item)
        previous = selected.get(name)
        if previous is None or rank > previous[0]:
            selected[name] = (rank, value)
    pairs = {name: value for name, (_, value) in selected.items()}
    if not _has_weibo_login_cookie(pairs):
        return ""
    return _pairs_to_header(pairs)


def _cookie_domain_applies_to_weibo(domain: str) -> bool:
    clean = domain.lstrip(".").lower()
    return clean == "weibo.com"


def _cookie_rank_for_weibo(item: dict) -> int:
    path = str(item.get("path") or "")
    return 2 if path in {"", "/"} else 1


def _fetch_json(url_or_request, timeout: float) -> dict | list:
    with urlopen(url_or_request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class _CdpWebSocket:
    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self.sock: socket.socket | None = None
        self.next_id = 1

    def __enter__(self) -> _CdpWebSocket:
        self.sock = _websocket_connect(self.ws_url)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.sock:
            with suppress(Exception):
                _websocket_send_frame(self.sock, b"", opcode=0x8)
            self.sock.close()
            self.sock = None

    def call(self, method: str, params: dict | None = None) -> dict:
        if not self.sock:
            raise RuntimeError("CDP websocket 未连接")
        msg_id = self.next_id
        self.next_id += 1
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        _websocket_send_json(self.sock, payload)
        while True:
            msg = json.loads(_websocket_read_message(self.sock))
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RuntimeError(json.dumps(msg["error"], ensure_ascii=False))
            result = msg.get("result", {})
            if not isinstance(result, dict):
                raise RuntimeError(f"CDP 返回格式异常: {result!r}")
            return result


def _websocket_connect(ws_url: str) -> socket.socket:
    parsed = urlparse(ws_url)
    if parsed.scheme != "ws":
        raise ValueError(f"仅支持 ws:// CDP 地址: {ws_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock = socket.create_connection((host, port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = _recv_until(sock, b"\r\n\r\n", limit=65536)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError(response.decode("utf-8", errors="replace").splitlines()[0])
    expected = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    if expected.encode("ascii") not in response:
        raise RuntimeError("CDP websocket 握手校验失败")
    return sock


def _recv_until(sock: socket.socket, marker: bytes, limit: int) -> bytes:
    data = b""
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("连接已关闭")
        data += chunk
        if len(data) > limit:
            raise RuntimeError("响应过大")
    return data


def _websocket_send_json(sock: socket.socket, payload: dict) -> None:
    _websocket_send_frame(sock, json.dumps(payload, ensure_ascii=False).encode("utf-8"), opcode=0x1)


def _websocket_send_frame(sock: socket.socket, payload: bytes, opcode: int) -> None:
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, 0x80 | length])
    elif length < (1 << 16):
        header = bytes([first, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 0x80 | 127]) + length.to_bytes(8, "big")
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    sock.sendall(header + mask + masked)


def _websocket_read_message(sock: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        fin, opcode, payload = _websocket_read_frame(sock)
        if opcode == 0x8:
            raise RuntimeError("CDP websocket 已关闭")
        if opcode == 0x9:
            _websocket_send_frame(sock, payload, opcode=0xA)
            continue
        if opcode in {0x1, 0x0}:
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8")


def _websocket_read_frame(sock: socket.socket) -> tuple[bool, int, bytes]:
    header = _recv_exact(sock, 2)
    first, second = header
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    return fin, opcode, payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("连接已关闭")
        data += chunk
    return data


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
