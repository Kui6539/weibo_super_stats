from __future__ import annotations

import unittest

from modules.images.paths import build_image_filename, build_image_folder_name, sanitize_image_path_part


class ImagesPathsTests(unittest.TestCase):
    def test_safe_folder_name_keeps_chinese(self) -> None:
        name = build_image_folder_name(1, "作者/含*特殊字符", "abc:123")
        self.assertTrue(name.startswith("01_作者_含_特殊字符"))
        self.assertNotIn("/", name)
        self.assertNotIn("*", name)

    def test_empty_and_long_parts(self) -> None:
        self.assertEqual(sanitize_image_path_part(""), "item")
        self.assertLessEqual(len(sanitize_image_path_part("很长" * 50)), 48)

    def test_build_image_filename(self) -> None:
        filename = build_image_filename(1, "https://example.com/a.png", "comment_image")
        self.assertTrue(filename.startswith("comment_01_"))
        self.assertTrue(filename.endswith(".png"))


if __name__ == "__main__":
    unittest.main()
