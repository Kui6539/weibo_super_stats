from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import core.config as config_module
from server.handlers import AppRequestHandler
from tests.helpers import assert_json_ok


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._old_config_path = config_module.CONFIG_PATH
        cls._temp_config_dir = tempfile.TemporaryDirectory()
        config_module.CONFIG_PATH = Path(cls._temp_config_dir.name) / "weibo_stats_config.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AppRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        config_module.CONFIG_PATH = cls._old_config_path
        cls._temp_config_dir.cleanup()

    def test_defaults_status_and_cookie_contracts(self) -> None:
        defaults = self.get_json("/api/defaults")
        assert_json_ok(self, defaults)
        self.assertIn("defaults", defaults)
        self.assertEqual(defaults["defaults"].get("cookie"), "")
        self.assertIn("version", defaults["defaults"])

        status = self.get_json("/api/status")
        assert_json_ok(self, status)
        self.assertIn("job", status)

        cookie = self.post_json("/api/check-cookie", {"cookie": "", "super_topic": ""})
        assert_json_ok(self, cookie)
        self.assertEqual(cookie["data"]["login_state"], "invalid")
        self.assertNotIn("Traceback", json.dumps(cookie, ensure_ascii=False))

    def test_preflight_returns_checks_without_starting_task(self) -> None:
        payload = {
            "super_topic": "",
            "cookie": "",
            "window_start": "2026-05-02T04:00",
            "window_end": "2026-05-01T04:00",
            "max_pages": "0",
            "pause_seconds": "-1",
            "topic_comment_factor": "0.1",
            "output_dir": str(Path(self._temp_config_dir.name) / "output"),
        }
        response = self.post_json("/api/preflight", payload)
        assert_json_ok(self, response)
        self.assertFalse(response["data"]["can_start"])
        self.assertTrue(response["data"]["checks"])

    def test_cache_status_and_reexport_error_contracts(self) -> None:
        cache_missing = self.post_json("/api/cache-status", {"run_dir": "output/not_exists_for_api_contract"})
        assert_json_ok(self, cache_missing)
        self.assertFalse(cache_missing["ok"])

        output_root = Path.cwd() / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root, prefix="api_contract_") as tmp:
            rel = Path(tmp).relative_to(Path.cwd())
            reexport = self.post_json("/api/reexport", {"run_dir": str(rel), "export_types": ["markdown"]})
            assert_json_ok(self, reexport)
            self.assertFalse(reexport["ok"])
            self.assertIn("error", reexport)
            self.assertNotIn("Traceback", json.dumps(reexport, ensure_ascii=False))

    def get_json(self, path: str) -> dict:
        return self._request("GET", path)

    def post_json(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as err:
            return json.loads(err.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
