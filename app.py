from __future__ import annotations

import argparse
import os
import threading
import webbrowser

from core.job import console_log
from server.http_server import APP_HOST, APP_PORT, create_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="微博超话周报统计本地 Web 工具")
    parser.add_argument("--host", default=APP_HOST, help=f"监听地址，默认 {APP_HOST}")
    parser.add_argument("--port", default=APP_PORT, type=int, help=f"监听端口，默认 {APP_PORT}")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
