from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import core.config as config


class PresetsConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = config.CONFIG_PATH
        config.CONFIG_PATH = Path(self.tmp.name) / "weibo_stats_config.json"

    def tearDown(self) -> None:
        config.CONFIG_PATH = self.old_path
        self.tmp.cleanup()

    def test_version_2_flat_config_migrates_to_version_3(self) -> None:
        migrated = config.migrate_config(
            {
                "version": 2,
                "super_topic": "100808abc",
                "cookie": "SUB=secret",
                "output_dir": "output",
            }
        )
        flat = config.flatten_active_config(migrated)
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(flat["super_topic"], "100808abc")
        self.assertEqual(migrated["global"]["cookie"], "SUB=secret")
        self.assertNotIn("cookie", migrated["presets"]["default"])

    def test_save_activate_duplicate_and_delete_preset(self) -> None:
        config.save_preset("warma", {"name": "Warma", "super_topic": "100808warma"})
        payload = config.get_presets_payload()
        self.assertIn("warma", payload["presets"])
        self.assertFalse("cookie" in payload["global"])

        config.duplicate_preset("warma", "warma_copy", "Warma 副本")
        payload = config.activate_preset("warma_copy")
        self.assertEqual(payload["active_preset"], "warma_copy")

        payload = config.delete_preset("warma")
        self.assertIn("warma_copy", payload["presets"])

    def test_cannot_delete_last_preset(self) -> None:
        with self.assertRaises(config.ConfigError):
            config.delete_preset("default")


if __name__ == "__main__":
    unittest.main()
