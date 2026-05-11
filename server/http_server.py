from __future__ import annotations

from http.server import ThreadingHTTPServer

from server.handlers import AppRequestHandler

APP_HOST = "127.0.0.1"
APP_PORT = 8765


def create_server(host: str, port: int) -> tuple[ThreadingHTTPServer, str]:
    ports = [port, *range(port + 1, port + 20)]
    last_error: OSError | None = None
    for candidate in ports:
        server, error = _try_create_server(host, candidate)
        if server:
            return server, f"http://{host}:{candidate}/"
        last_error = error
    raise RuntimeError(f"无法启动本地服务：{last_error}")


def _try_create_server(host: str, port: int) -> tuple[ThreadingHTTPServer | None, OSError | None]:
    try:
        return ThreadingHTTPServer((host, port), AppRequestHandler), None
    except OSError as err:
        return None, err

