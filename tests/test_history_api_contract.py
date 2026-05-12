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
import core.history as history_module
from server.handlers import AppRequestHandler
from tests.helpers import assert_json_ok, write_cache_fixture


class HistoryApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._old_config_path = config_module.CONFIG_PATH
        cls._old_history_path = history_module.HISTORY_PATH
        cls._temp_config_dir = tempfile.TemporaryDirectory()
        config_module.CONFIG_PATH = Path(cls._temp_config_dir.name) / "weibo_stats_config.json"
        history_module.HISTORY_PATH = Path(cls._temp_config_dir.name) / "weibo_stats_history.json"
        cls.output_root = Path.cwd() / "output"
        cls.output_root.mkdir(exist_ok=True)
        cls._temp_output_dir = tempfile.TemporaryDirectory(dir=cls.output_root, prefix="history_api_")
        cls.run_dir = Path(cls._temp_output_dir.name) / "20260512_020202"
        cls.run_dir.mkdir()
        write_cache_fixture(cls.run_dir)
        cls._write_manifest(cls.run_dir)

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
        history_module.HISTORY_PATH = cls._old_history_path
        cls._temp_output_dir.cleanup()
        cls._temp_config_dir.cleanup()

    def test_history_scan_cache_status_remove_and_reexport_contracts(self) -> None:
        empty_history = self.get_json("/api/history")
        assert_json_ok(self, empty_history)

        scanned = self.post_json("/api/history/scan", {"output_dir": str(Path(self._temp_output_dir.name).relative_to(Path.cwd()))})
        assert_json_ok(self, scanned)
        self.assertEqual(scanned["data"]["scanned"], 1)
        run_id = scanned["data"]["items"][0]["run_id"]

        status = self.post_json("/api/history/cache-status", {"run_id": run_id})
        assert_json_ok(self, status)
        self.assertTrue(status["data"]["can_reexport"])

        reexport = self.post_json("/api/history/reexport", {"run_id": run_id, "export_types": ["markdown", "csv", "summary"]})
        assert_json_ok(self, reexport)
        self.assertTrue(reexport["ok"])
        self.assertIn("manifest", reexport["data"])

        removed = self.post_json("/api/history/remove", {"run_id": run_id, "delete_files": False})
        assert_json_ok(self, removed)
        self.assertEqual(removed["data"]["removed"], run_id)

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
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as err:
            return json.loads(err.read().decode("utf-8"))

    @staticmethod
    def _write_manifest(run_dir: Path) -> None:
        manifest = {
            "run_id": run_dir.name,
            "created_at": "2026-05-12 02:02:02",
            "updated_at": "2026-05-12 02:02:02",
            "status": "completed",
            "super_topic": "100808abc",
            "selected_count": 3,
            "total_posts": 3,
            "files": {"markdown": "weekly_report.md", "csv": "weibo_posts.csv", "summary": "weibo_summary.txt"},
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
