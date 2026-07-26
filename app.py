from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import threading
import webbrowser

from core.job import console_log
from server.http_server import APP_HOST, APP_PORT, create_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="微博超话周报统计本地 Web 工具")
    parser.add_argument("--host", default=APP_HOST, help=f"监听地址，默认 {APP_HOST}")
    parser.add_argument("--port", default=APP_PORT, type=int, help=f"监听端口，默认 {APP_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="允许绑定非回环地址（危险：本工具没有任何鉴权）",
    )
    return parser.parse_args()


def check_bind_address(host: str, allow_remote: bool) -> None:
    """Refuse a non-loopback bind unless the user opted in explicitly.

    There is no authentication anywhere in this service: binding 0.0.0.0 hands
    the whole API -- including the stored weibo cookie -- to everyone on the
    network segment. The Host-header guard stops a browser being tricked into
    reaching us; this stops the user configuring the exposure directly.
    """
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Hostnames rather than literals ("localhost") are treated as local
        # only when they resolve to loopback by name.
        is_loopback = host.strip().lower() in {"localhost", ""}
    if is_loopback or allow_remote:
        if not is_loopback:
            console_log("警告：正在监听非回环地址。本工具没有鉴权，同网段任何人都可读取你的微博 Cookie 与本机文件。")
        return
    console_log(f"已拒绝绑定非回环地址 {host}。")
    console_log("本工具没有任何鉴权，只应运行在 127.0.0.1。确需局域网访问请显式加上 --allow-remote。")
    sys.exit(2)


def main() -> None:
    args = parse_args()
    check_bind_address(args.host, args.allow_remote)
    server, url = create_server(args.host, args.port)
    console_log(f"微博超话周报统计已启动：{url}")
    console_log("命令行会实时滚动输出抓取日志；结束时按 Ctrl+C。")
    if not args.no_browser and os.environ.get("WEIBO_STATS_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console_log("正在关闭服务...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
