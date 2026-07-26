"""Regression tests for the local HTTP service's security boundary.

These lock down invariants that are cheap to break during a refactor and
expensive to discover in the wild: a malicious page must not be able to reach
the API, and no caller-supplied path may escape the directories the tool owns.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import core.config as config_module
import core.history as history_module
from server.handlers import ROOT_DIR, AppRequestHandler

SENTINEL_COOKIE = "SUB=_sentinel_cookie_value_must_never_leak_; SUBP=abc"


class SecurityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._old_config_path = config_module.CONFIG_PATH
        cls._old_history_path = history_module.HISTORY_PATH
        cls._temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(cls._temp_dir.name)
        config_module.CONFIG_PATH = temp_root / "weibo_stats_config.json"
        history_module.HISTORY_PATH = temp_root / "weibo_stats_history.json"
        # A stored cookie is the thing most worth stealing, so make sure one
        # exists while these tests run.
        config_module.save_user_config({"cookie": SENTINEL_COOKIE})

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AppRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        config_module.CONFIG_PATH = cls._old_config_path
        history_module.HISTORY_PATH = cls._old_history_path
        cls._temp_dir.cleanup()

    # --- request origin -------------------------------------------------

    def test_non_loopback_host_header_is_rejected(self) -> None:
        """Defeats DNS rebinding: the browser keeps sending the attacker host."""
        status, body = self.request("GET", "/api/defaults", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)
        self.assertNotIn("_sentinel_cookie_value", body)

    def test_cross_site_origin_is_rejected(self) -> None:
        status, body = self.request(
            "POST",
            "/api/config",
            body={"theme": "light"},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertEqual(status, 403)
        self.assertNotIn("_sentinel_cookie_value", body)

    def test_cross_site_fetch_metadata_is_rejected(self) -> None:
        status, _ = self.request(
            "POST",
            "/api/config",
            body={"theme": "light"},
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(status, 403)

    def test_text_plain_body_is_rejected(self) -> None:
        """The CORS "simple request" bypass: no preflight, side effect anyway."""
        status, _ = self.request(
            "POST",
            "/api/output/cleanup",
            raw_body=json.dumps({"confirm": True, "keep_recent": 0}),
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 403)

    def test_same_origin_request_still_works(self) -> None:
        status, body = self.request(
            "GET",
            "/api/defaults",
            headers={"Origin": f"http://127.0.0.1:{self.port}", "Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_oversized_body_is_refused_without_buffering_it(self) -> None:
        """A declared Content-Length must not become an allocation.

        The server refuses before reading and drops the connection, so the
        client may well see a reset instead of the 400 -- either way the body
        was never buffered. What matters is that the service survives it.
        """
        try:
            status, _ = self.request("POST", "/api/config", raw_body="x" * (3 * 1024 * 1024))
            self.assertEqual(status, 400)
        except OSError:
            pass
        status, body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    # --- credential confinement ------------------------------------------

    def test_defaults_never_returns_the_stored_cookie(self) -> None:
        status, body = self.request("GET", "/api/defaults")
        self.assertEqual(status, 200)
        self.assertNotIn("_sentinel_cookie_value", body)
        defaults = json.loads(body)["data"]["defaults"]
        self.assertEqual(defaults["cookie"], "")
        self.assertTrue(defaults["has_cookie"])
        self.assertEqual(defaults["cookie_length"], len(SENTINEL_COOKIE))

    def test_presets_never_returns_the_stored_cookie(self) -> None:
        status, body = self.request("GET", "/api/presets")
        self.assertEqual(status, 200)
        self.assertNotIn("_sentinel_cookie_value", body)

    # --- path confinement -------------------------------------------------

    def test_md_path_cannot_read_arbitrary_files(self) -> None:
        """md_path used to accept any existing file and return it as Markdown."""
        for target in (
            str(ROOT_DIR / "weibo_stats_config.json"),
            str(ROOT_DIR / "app.py"),
            "C:/Windows/win.ini",
            "/etc/passwd",
        ):
            with self.subTest(target=target):
                status, body = self.request("GET", f"/api/report-preview?md_path={quote(target)}")
                self.assertEqual(status, 404)
                self.assertNotIn("import argparse", body)
                self.assertNotIn("_sentinel_cookie_value", body)

    def test_report_asset_cannot_escape_via_md_path(self) -> None:
        status, body = self.request(
            "GET",
            f"/api/report-asset?md_path={quote(str(ROOT_DIR / 'app.py'))}&path=app.py",
        )
        self.assertEqual(status, 404)
        self.assertNotIn("import argparse", body)

    def test_report_asset_rejects_relative_traversal(self) -> None:
        for rel in ("../weibo_stats_config.json", "..%2F..%2Fapp.py", "C:/Windows/win.ini"):
            with self.subTest(rel=rel):
                status, body = self.request("GET", f"/api/report-asset?path={quote(rel, safe='%')}")
                self.assertIn(status, (400, 404))
                self.assertNotIn("_sentinel_cookie_value", body)

    def test_static_route_cannot_escape_web_root(self) -> None:
        for url_path in ("/../app.py", "/..%2Fapp.py", "/js/../../app.py"):
            with self.subTest(url_path=url_path):
                status, body = self.request("GET", url_path)
                self.assertIn(status, (400, 404))
                self.assertNotIn("import argparse", body)

    def test_candidate_thumbnail_rejects_traversal(self) -> None:
        status, body = self.request(
            "GET",
            "/api/candidate-thumbnail?run_id=..&path=" + quote("../../weibo_stats_config.json"),
        )
        self.assertIn(status, (400, 404))
        self.assertNotIn("_sentinel_cookie_value", body)

    def test_run_dir_outside_output_is_rejected(self) -> None:
        for run_dir in (str(ROOT_DIR / "web"), str(ROOT_DIR), "C:/Windows"):
            with self.subTest(run_dir=run_dir):
                status, body = self.request("POST", "/api/cache-status", body={"run_dir": run_dir})
                self.assertEqual(status, 400)
                self.assertFalse(json.loads(body)["ok"])

    def test_open_result_dir_rejects_arbitrary_paths(self) -> None:
        status, body = self.request("POST", "/api/open-result-dir", body={"run_dir": "C:/Windows"})
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["ok"])

    # --- error hygiene ----------------------------------------------------

    def test_errors_never_carry_tracebacks_or_absolute_paths(self) -> None:
        status, body = self.request("POST", "/api/reexport", body={"run_dir": "output/20990101_000000"})
        self.assertGreaterEqual(status, 400)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("C:\\\\Users", body)

    def test_keep_alive_lets_a_connection_serve_two_requests(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            for _ in range(2):
                conn.request("GET", "/api/status", headers={"Host": f"127.0.0.1:{self.port}"})
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
                self.assertFalse(response.will_close)
        finally:
            conn.close()

    # --- helper -----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        raw_body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """Issue a request with full control over headers, including Host.

        urllib rewrites Host, so these tests talk to HTTPConnection directly.
        """
        sent = {"Host": f"127.0.0.1:{self.port}"}
        payload = raw_body if raw_body is not None else (json.dumps(body) if body is not None else None)
        if payload is not None:
            sent["Content-Type"] = "application/json"
            sent["Content-Length"] = str(len(payload.encode("utf-8")))
        sent.update(headers or {})
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=payload, headers=sent)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", errors="replace")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
