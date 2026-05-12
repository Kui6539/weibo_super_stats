from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.output_cleanup import cleanup_output, cleanup_preview, output_summary
from server.handlers import parse_optional_int


class OutputCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_root = Path.cwd() / "output"
        self.output_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.output_root, prefix="cleanup_root_")
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_summary_and_preview(self) -> None:
        self._make_run("20260510_010101", can_reexport=False)
        self._make_run("20260511_010101", can_reexport=True)
        summary = output_summary(self.root)
        self.assertEqual(summary["run_count"], 2)

        preview = cleanup_preview(self.root, keep_recent=0, incomplete_only=True)
        self.assertEqual(preview["delete_count"], 1)
        self.assertEqual(preview["items"][0]["run_id"], "20260510_010101")

    def test_cleanup_requires_confirm_and_keeps_recent(self) -> None:
        old_dir = self._make_run("20260510_010101", can_reexport=False)
        self._make_run("20260511_010101", can_reexport=False)

        no_delete = cleanup_output(self.root, keep_recent=0, incomplete_only=True, confirm=False)
        self.assertFalse(no_delete["deleted"])
        self.assertTrue(old_dir.exists())

        deleted = cleanup_output(self.root, keep_recent=1, incomplete_only=True, confirm=True)
        self.assertTrue(deleted["deleted"])
        self.assertFalse(old_dir.exists())
        self.assertTrue((self.root / "20260511_010101").exists())

    def test_api_keep_recent_zero_is_preserved(self) -> None:
        self.assertEqual(parse_optional_int(0, 5), 0)
        self.assertEqual(parse_optional_int("0", 5), 0)
        self.assertEqual(parse_optional_int("", 5), 5)

    def _make_run(self, name: str, can_reexport: bool) -> Path:
        run_dir = self.root / name
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text('{"status":"completed","files":{}}', encoding="utf-8")
        cache = run_dir / "cache"
        cache.mkdir()
        (cache / "run_config.json").write_text("{}", encoding="utf-8")
        if can_reexport:
            (cache / "posts_scored.json").write_text('[{"post_id":"1"}]', encoding="utf-8")
            (cache / "selected_posts.json").write_text('[{"post_id":"1"}]', encoding="utf-8")
        return run_dir


if __name__ == "__main__":
    unittest.main()
