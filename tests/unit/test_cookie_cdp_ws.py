"""Protocol-level tests for the hand-rolled CDP WebSocket client.

~150 lines of RFC 6455 framing shipped with no tests because it was inlined in
cookie_helper next to code that launches browsers. Split out, it can be driven
over a plain socket pair: no browser, no network, no cookies.
"""

from __future__ import annotations

import json
import socket
import threading
import unittest

from modules.cookie_cdp_ws import (
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_TEXT,
    CdpWebSocket,
    apply_mask,
    expected_accept,
    read_frame,
    read_message,
    recv_exact,
    send_frame,
    send_json,
)


def socket_pair() -> tuple[socket.socket, socket.socket]:
    """A connected pair standing in for client and browser."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.create_connection(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    return client, server


def server_frame(payload: bytes, opcode: int = OPCODE_TEXT, fin: bool = True) -> bytes:
    """Encode a frame the way a server does: no mask bit."""
    first = (0x80 if fin else 0) | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, length])
    elif length < (1 << 16):
        header = bytes([first, 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 127]) + length.to_bytes(8, "big")
    return header + payload


class MaskingTests(unittest.TestCase):
    def test_masking_is_its_own_inverse(self) -> None:
        payload = "永雏塔菲 cookie".encode()
        mask = b"\x01\x02\x03\x04"
        self.assertEqual(apply_mask(apply_mask(payload, mask), mask), payload)

    def test_an_empty_mask_leaves_the_payload_alone(self) -> None:
        self.assertEqual(apply_mask(b"abc", b""), b"abc")

    def test_client_frames_always_set_the_mask_bit(self) -> None:
        """RFC 6455 section 5.3: a server must drop unmasked client frames."""
        client, server = socket_pair()
        try:
            send_frame(client, b"hi", opcode=OPCODE_TEXT)
            header = recv_exact(server, 2)
            self.assertTrue(header[1] & 0x80, "client frames must be masked")
        finally:
            client.close()
            server.close()


class FrameLengthTests(unittest.TestCase):
    def test_each_length_encoding_round_trips(self) -> None:
        """The three payload-length forms: 7-bit, 16-bit and 64-bit."""
        for size in (5, 125, 126, 300, 70000):
            with self.subTest(size=size):
                client, server = socket_pair()
                try:
                    payload = b"x" * size
                    threading.Thread(
                        target=send_frame, args=(client, payload, OPCODE_TEXT), daemon=True
                    ).start()
                    fin, opcode, received = read_frame(server)
                finally:
                    client.close()
                    server.close()
                self.assertTrue(fin)
                self.assertEqual(opcode, OPCODE_TEXT)
                self.assertEqual(received, payload)


class MessageAssemblyTests(unittest.TestCase):
    def test_fragments_are_reassembled_into_one_message(self) -> None:
        client, server = socket_pair()
        try:
            server.sendall(server_frame("永雏".encode(), OPCODE_TEXT, fin=False))
            server.sendall(server_frame("塔菲".encode(), opcode=0x0, fin=True))
            self.assertEqual(read_message(client), "永雏塔菲")
        finally:
            client.close()
            server.close()

    def test_a_ping_is_answered_and_does_not_end_the_message(self) -> None:
        client, server = socket_pair()
        try:
            server.sendall(server_frame(b"keepalive", OPCODE_PING))
            server.sendall(server_frame(b'{"ok":1}', OPCODE_TEXT))
            self.assertEqual(read_message(client), '{"ok":1}')

            # The pong the client sent back is masked, like all client frames.
            fin, opcode, payload = read_frame(server)
            self.assertEqual((fin, opcode, payload), (True, 0xA, b"keepalive"))
        finally:
            client.close()
            server.close()

    def test_a_close_frame_raises_rather_than_hanging(self) -> None:
        client, server = socket_pair()
        try:
            server.sendall(server_frame(b"", OPCODE_CLOSE))
            with self.assertRaises(RuntimeError):
                read_message(client)
        finally:
            client.close()
            server.close()

    def test_a_dropped_connection_raises_rather_than_hanging(self) -> None:
        client, server = socket_pair()
        server.close()
        try:
            with self.assertRaises(RuntimeError):
                recv_exact(client, 4)
        finally:
            client.close()


class HandshakeTests(unittest.TestCase):
    def test_the_accept_value_matches_the_rfc_example(self) -> None:
        """RFC 6455 section 1.3 worked example."""
        self.assertEqual(expected_accept("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")


class CdpSessionTests(unittest.TestCase):
    """The request/response layer, driven over a socket pair."""

    def run_session(self, replies: list[dict]) -> tuple[dict, list[dict]]:
        client, server = socket_pair()
        seen: list[dict] = []

        def respond() -> None:
            for reply in replies:
                request = json.loads(read_message(server))
                seen.append(request)
                body = dict(reply)
                body.setdefault("id", request.get("id"))
                send_json(server, body)

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        try:
            with CdpWebSocket("ws://ignored", connect=lambda _url: client) as ws:
                result = ws.call("Network.getCookies", {"urls": ["https://weibo.com/"]})
        finally:
            thread.join(timeout=3)
            client.close()
            server.close()
        return result, seen

    def test_a_call_sends_the_method_and_returns_its_result(self) -> None:
        result, seen = self.run_session([{"result": {"cookies": [{"name": "SUB"}]}}])
        self.assertEqual(result, {"cookies": [{"name": "SUB"}]})
        self.assertEqual(seen[0]["method"], "Network.getCookies")
        self.assertEqual(seen[0]["params"], {"urls": ["https://weibo.com/"]})

    def test_ids_increment_so_replies_can_be_matched(self) -> None:
        client, server = socket_pair()

        def respond() -> None:
            for _ in range(2):
                request = json.loads(read_message(server))
                send_json(server, {"id": request["id"], "result": {}})

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        try:
            with CdpWebSocket("ws://ignored", connect=lambda _url: client) as ws:
                first = ws.next_id
                ws.call("Network.enable")
                ws.call("Network.getCookies")
                self.assertEqual(ws.next_id, first + 2)
        finally:
            thread.join(timeout=3)
            client.close()
            server.close()

    def test_an_error_reply_raises_with_the_detail(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self.run_session([{"error": {"code": -32000, "message": "Not allowed"}}])
        self.assertIn("Not allowed", str(ctx.exception))

    def test_a_non_object_result_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            self.run_session([{"result": "unexpected"}])

    def test_calling_before_connecting_is_an_error_not_a_crash(self) -> None:
        with self.assertRaises(RuntimeError):
            CdpWebSocket("ws://ignored").call("Network.enable")

    def test_only_ws_urls_are_accepted(self) -> None:
        from modules.cookie_cdp_ws import websocket_connect

        for url in ("wss://example.com/x", "http://127.0.0.1:9222/x", "ftp://x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                websocket_connect(url)


if __name__ == "__main__":
    unittest.main()
