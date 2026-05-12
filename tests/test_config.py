from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import core.config as config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = config.CONFIG_PATH
        config.CONFIG_PATH = Path(self.tmp.name) / "weibo_stats_config.json"

    def tearDown(self) -> None:
        config.CONFIG_PATH = self.old_path
        self.tmp.cleanup()

    def test_default_config_loads_when_missing(self) -> None:
        data = config.load_config()
        self.assertEqual(data["version"], 3)
        self.assertIn("presets", data)
        self.assertIn("global", data)

    def test_old_config_migrates(self) -> None:
        data = config.migrate_config({"super_topic": "100808abc", "advanced_mode": True})
        self.assertEqual(data["version"], 3)
        flat = config.flatten_active_config(data)
        self.assertEqual(flat["super_topic"], "100808abc")
        self.assertEqual(flat["advanced_mode"], "true")

    def test_clear_cookie_preserves_other_config(self) -> None:
        config.save_config({"super_topic": "100808abc", "cookie": "SUB=secret", "output_dir": "output"})
        cleared = config.clear_config("cookie")
        self.assertEqual(cleared["cookie"], "")
        self.assertEqual(cleared["super_topic"], "100808abc")

    def test_log_position_migrates_and_normalizes(self) -> None:
        data = config.migrate_config({"log_position": {"mode": "panel", "left": "123.8", "top": 99.2}})
        self.assertEqual(data["global"]["log_position"], {"mode": "panel", "left": 123, "top": 99})

        fallback = config.migrate_config({"log_position": {"mode": "bad", "left": -10, "top": "bad"}})
        self.assertEqual(fallback["global"]["log_position"], {"mode": "bubble", "left": 0, "top": 86})

    def test_cookie_browser_migrates_and_normalizes(self) -> None:
        chrome = config.migrate_config({"cookie_browser": "Chrome"})
        self.assertEqual(chrome["global"]["cookie_browser"], "chrome")

        fallback = config.migrate_config({"cookie_browser": "firefox"})
        self.assertEqual(fallback["global"]["cookie_browser"], "edge")


if __name__ == "__main__":
    unittest.main()
