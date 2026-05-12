from __future__ import annotations

import json
import unittest

from tests.helpers import FIXTURE_DIR, assert_no_sensitive_fields


class FixtureSafetyTests(unittest.TestCase):
    def test_all_fixture_json_is_valid_and_not_sensitive(self) -> None:
        fixture_files = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertTrue(fixture_files)
        for path in fixture_files:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                assert_no_sensitive_fields(self, data)


if __name__ == "__main__":
    unittest.main()
