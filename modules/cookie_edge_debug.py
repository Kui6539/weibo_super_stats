from __future__ import annotations

import socket
from pathlib import Path


def start_debug_edge(profile_dir: Path | None = None, port: int = 9222) -> str:
    from cookie_helper import launch_edge_debug_browser

    return launch_edge_debug_browser(profile_dir=profile_dir, port=port)


def read_cookie_from_debug_edge() -> str:
    from cookie_helper import _try_get_cookie_header_from_cdp

    cookie, _err = _try_get_cookie_header_from_cdp()
    return cookie


def close_debug_edge_if_needed() -> bool:
    from cookie_helper import close_edge_debug_browser

    return close_edge_debug_browser()


def is_debug_port_available(port: int = 9222, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) == 0
