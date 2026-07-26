"""Launching and querying a browser started with --remote-debugging-port.

Reading cookies goes straight to modules.cookie_cdp. Launching and closing a
browser still calls back into cookie_helper, which owns executable discovery
and profile handling; those imports stay function-local because cookie_helper
imports this package's siblings and a module-level import would cycle.

This module used to reach for cookie_helper's private
_try_get_cookie_header_from_cdp -- a module depending on a private name in the
layer above it, which is the wrong way round and breaks silently if that name
is renamed.
"""

from __future__ import annotations

import socket
from pathlib import Path

from modules.cookie_cdp import read_cookie_from_cdp


def start_debug_edge(profile_dir: Path | None = None, port: int = 9222) -> str:
    from cookie_helper import launch_edge_debug_browser

    return launch_edge_debug_browser(profile_dir=profile_dir, port=port)


def start_debug_browser(browser: str = "edge", profile_dir: Path | None = None, port: int | None = None) -> str:
    from cookie_helper import launch_debug_browser

    return launch_debug_browser(browser=browser, profile_dir=profile_dir, port=port)


def read_cookie_from_debug_edge() -> str:
    cookie, _err = read_cookie_from_cdp("edge")
    return cookie


def read_cookie_from_debug_browser(browser: str = "edge") -> str:
    cookie, _err = read_cookie_from_cdp(browser)
    return cookie


def close_debug_edge_if_needed() -> bool:
    from cookie_helper import close_edge_debug_browser

    return close_edge_debug_browser()


def close_debug_browser_if_needed(browser: str = "edge") -> bool:
    from cookie_helper import close_debug_browser

    return close_debug_browser(browser)


def is_debug_port_available(port: int = 9222, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) == 0
