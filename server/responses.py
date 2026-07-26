from __future__ import annotations

import json
import mimetypes
import shutil
from http import HTTPStatus
from pathlib import Path
from typing import Any

# A JSON body larger than this is a bug or an attack, never a real request:
# the biggest legitimate payload is /api/select's index array or a config save.
# Without a cap, a declared Content-Length allocates that much memory per
# request thread.
MAX_BODY_BYTES = 2 * 1024 * 1024

# Stream rather than buffer anything above this; long-image JPGs run to several
# megabytes each and used to be read fully into memory before sending.
STREAM_CHUNK_THRESHOLD = 256 * 1024


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
    resolved_type = content_type or content_type_for(path)
    size = path.stat().st_size
    if size <= STREAM_CHUNK_THRESHOLD:
        send_bytes(handler, path.read_bytes(), status=HTTPStatus.OK, content_type=resolved_type, cache="private")
        return
    try:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", resolved_type)
        handler.send_header("Content-Length", str(size))
        _send_common_headers(handler, cache="private")
        handler.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, handler.wfile)
    except OSError as err:
        if _is_client_disconnect(err):
            return
        raise


def parse_json_body(handler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    if length > MAX_BODY_BYTES:
        # The body stays unread, so this connection can no longer be reused:
        # its leftover bytes would be parsed as the next request line.
        handler.close_connection = True
        raise ValueError("请求体过大，已拒绝处理。")
    raw = handler.rfile.read(length)
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def send_bytes(
    handler,
    body: bytes,
    status: int | HTTPStatus,
    content_type: str,
    cache: str = "no-store",
) -> None:
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        _send_common_headers(handler, cache=cache)
        handler.end_headers()
        handler.wfile.write(body)
    except OSError as err:
        if _is_client_disconnect(err):
            return
        raise


def _send_common_headers(handler, cache: str) -> None:
    handler.send_header("Cache-Control", "no-store" if cache == "no-store" else "private, max-age=0, must-revalidate")
    # /api/report-asset serves bytes downloaded from weibo with a type guessed
    # from the file name, so sniffing must stay off.
    handler.send_header("X-Content-Type-Options", "nosniff")
    # Report previews load remote weibo images; without this the local URL
    # (which carries run_id / md_path) would travel to those hosts as Referer.
    handler.send_header("Referrer-Policy", "no-referrer")


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

