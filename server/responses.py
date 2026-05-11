from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from typing import Any


def json_ok(handler, data: Any = None, **extra: Any) -> None:
    payload = {"ok": True, "data": data if data is not None else {}}
    payload.update(extra)
    send_json(handler, payload)


def json_error(
    handler,
    code: str,
    message: str,
    suggestion: str | None = None,
    status: int | HTTPStatus = HTTPStatus.BAD_REQUEST,
) -> None:
    send_json(
        handler,
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "suggestion": suggestion or "请检查输入后重试。",
            },
        },
        status,
    )


def send_json(handler, payload: dict[str, Any], status: int | HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    send_bytes(handler, body, status=status, content_type="application/json; charset=utf-8")


def send_static_file(handler, path: Path, content_type: str | None = None) -> None:
    body = path.read_bytes()
    send_bytes(handler, body, status=HTTPStatus.OK, content_type=content_type or content_type_for(path))


def parse_json_body(handler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def send_bytes(handler, body: bytes, status: int | HTTPStatus, content_type: str) -> None:
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except OSError as err:
        if _is_client_disconnect(err):
            return
        raise


def content_type_for(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _is_client_disconnect(err: OSError) -> bool:
    if isinstance(err, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    return getattr(err, "winerror", None) in {10053, 10054, 10058}

