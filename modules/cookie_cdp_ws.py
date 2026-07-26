"""A minimal WebSocket client for talking to a browser's DevTools endpoint.

Chrome DevTools Protocol is only reachable over WebSocket, and pulling in a
websocket library for one request-response call would be a heavy dependency for
a tool that otherwise runs on the standard library. So this implements just the
client half of RFC 6455 that CDP needs: the HTTP upgrade handshake, masked
client frames, fragment reassembly, and ping/pong.

Deliberately not implemented, because CDP over loopback never exercises them:
per-message compression, continuation of control frames, and anything about
``wss://``. Connections are to 127.0.0.1, so there is nothing to encrypt.

Kept apart from cookie_helper so the protocol can be tested against a socket
pair without a browser anywhere in sight -- previously it was inlined next to
the cookie logic and had no tests at all.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
from contextlib import suppress
from urllib.parse import urlparse

# RFC 6455's fixed handshake salt.
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

# Guards against a malformed endpoint streaming forever during the handshake.
HANDSHAKE_LIMIT_BYTES = 65536
CONNECT_TIMEOUT_SECONDS = 5


class CdpWebSocket:
    """A CDP session: ``with CdpWebSocket(url) as ws: ws.call("Method")``."""

    def __init__(self, ws_url: str, connect=None) -> None:
        self.ws_url = ws_url
        self.sock: socket.socket | None = None
        self.next_id = 1
        # Injectable so tests can supply a socket pair instead of a browser.
        self._connect = connect or websocket_connect

    def __enter__(self) -> CdpWebSocket:
        self.sock = self._connect(self.ws_url)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.sock:
            with suppress(Exception):
                send_frame(self.sock, b"", opcode=OPCODE_CLOSE)
            self.sock.close()
            self.sock = None

    def call(self, method: str, params: dict | None = None) -> dict:
        """Issue one CDP command and wait for the reply with a matching id.

        The endpoint interleaves unsolicited events with replies, so anything
        carrying a different id is skipped rather than treated as an answer.
        """
        if not self.sock:
            raise RuntimeError("CDP websocket 未连接")
        msg_id = self.next_id
        self.next_id += 1
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        send_json(self.sock, payload)
        while True:
            msg = json.loads(read_message(self.sock))
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RuntimeError(json.dumps(msg["error"], ensure_ascii=False))
            result = msg.get("result", {})
            if not isinstance(result, dict):
                raise RuntimeError(f"CDP 返回格式异常: {result!r}")
            return result


def websocket_connect(ws_url: str) -> socket.socket:
    """Open a socket and complete the RFC 6455 upgrade handshake."""
    parsed = urlparse(ws_url)
    if parsed.scheme != "ws":
        raise ValueError(f"仅支持 ws:// CDP 地址: {ws_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_SECONDS)
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
    response = recv_until(sock, b"\r\n\r\n", limit=HANDSHAKE_LIMIT_BYTES)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError(response.decode("utf-8", errors="replace").splitlines()[0])
    if expected_accept(key).encode("ascii") not in response:
        raise RuntimeError("CDP websocket 握手校验失败")
    return sock


def expected_accept(key: str) -> str:
    """The Sec-WebSocket-Accept value a compliant server must return."""
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")


def recv_until(sock: socket.socket, marker: bytes, limit: int) -> bytes:
    data = b""
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("连接已关闭")
        data += chunk
        if len(data) > limit:
            raise RuntimeError("响应过大")
    return data


def send_json(sock: socket.socket, payload: dict) -> None:
    send_frame(sock, json.dumps(payload, ensure_ascii=False).encode("utf-8"), opcode=OPCODE_TEXT)


def send_frame(sock: socket.socket, payload: bytes, opcode: int) -> None:
    """Write one final, masked frame. Clients must always mask (RFC 6455 §5.3)."""
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, 0x80 | length])
    elif length < (1 << 16):
        header = bytes([first, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 0x80 | 127]) + length.to_bytes(8, "big")
    mask = os.urandom(4)
    sock.sendall(header + mask + apply_mask(payload, mask))


def apply_mask(payload: bytes, mask: bytes) -> bytes:
    """XOR with the 4-byte key; masking and unmasking are the same operation."""
    if not mask:
        return payload
    return bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))


def read_message(sock: socket.socket) -> str:
    """Read one logical text message, reassembling fragments and answering pings."""
    chunks: list[bytes] = []
    while True:
        fin, opcode, payload = read_frame(sock)
        if opcode == OPCODE_CLOSE:
            raise RuntimeError("CDP websocket 已关闭")
        if opcode == OPCODE_PING:
            send_frame(sock, payload, opcode=OPCODE_PONG)
            continue
        if opcode in {OPCODE_TEXT, OPCODE_CONTINUATION}:
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8")


def read_frame(sock: socket.socket) -> tuple[bool, int, bytes]:
    header = recv_exact(sock, 2)
    first, second = header
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(recv_exact(sock, 8), "big")
    # Servers must not mask, but unmask anyway rather than return garbage.
    mask = recv_exact(sock, 4) if masked else b""
    payload = recv_exact(sock, length) if length else b""
    return fin, opcode, apply_mask(payload, mask)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("连接已关闭")
        data += chunk
    return data
