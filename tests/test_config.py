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
        self.assertEqual(data["version"], 2)
        self.assertIn("super_topic", data)

    def test_old_config_migrates(self) -> None:
        data = config.migrate_config({"super_topic": "100808abc", "advanced_mode": True})
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["super_topic"], "100808abc")
        self.assertEqual(data["advanced_mode"], "true")

    def test_clear_cookie_preserves_other_config(self) -> None:
        config.save_config({"super_topic": "100808abc", "cookie": "SUB=secret", "output_dir": "output"})
        cleared = config.clear_config("cookie")
        self.assertEqual(cleared["cookie"], "")
        self.assertEqual(cleared["super_topic"], "100808abc")


if __name__ == "__main__":
    unittest.main()

