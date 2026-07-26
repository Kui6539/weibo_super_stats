"""One splitter for multi-valued post fields, shared by every consumer.

image_local_paths and original_image_urls arrive as a list or a "|"-joined
string, sometimes newline-separated. That parsing was reimplemented eight
times. Seven agreed; export/report_helpers.split_multi_values did not -- it
rejected list input and ignored newlines, so a newline-separated path field
rendered in DOCX and Excel but silently vanished from Markdown and the
long-image report.
"""

from __future__ import annotations

import unittest

from modules.post_normalizer import split_multi_value


class SplitMultiValueTests(unittest.TestCase):
    def test_pipe_separated_string(self) -> None:
        self.assertEqual(split_multi_value("a|b|c"), ["a", "b", "c"])

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        self.assertEqual(split_multi_value(" a | b "), ["a", "b"])

    def test_newlines_separate_too(self) -> None:
        self.assertEqual(split_multi_value("a\nb"), ["a", "b"])
        self.assertEqual(split_multi_value("a\n\n\nb"), ["a", "b"])

    def test_mixed_separators(self) -> None:
        self.assertEqual(split_multi_value("a|b\nc"), ["a", "b", "c"])

    def test_list_input_is_accepted(self) -> None:
        self.assertEqual(split_multi_value(["a", " b ", ""]), ["a", "b"])

    def test_empty_and_none_yield_nothing(self) -> None:
        for value in ("", None, [], "||", "\n\n"):
            with self.subTest(value=value):
                self.assertEqual(split_multi_value(value), [])


class AllConsumersAgreeTests(unittest.TestCase):
    def test_every_export_splitter_is_the_shared_function(self) -> None:
        from export import docx_exporter, docx_images, excel_images, reexport
        from modules.images import downloader

        for module, name in (
            (docx_images, "_split_paths"),
            (excel_images, "_split_multi_paths"),
            (reexport, "_split_paths"),
            (downloader, "_split_paths"),
            (docx_exporter, "_split_image_paths"),
        ):
            with self.subTest(module=module.__name__, name=name):
                self.assertIs(getattr(module, name), split_multi_value)

    def test_report_helpers_now_matches_on_newlines_and_lists(self) -> None:
        """The divergence that made Markdown drop images DOCX kept."""
        from export.report_helpers import split_multi_values

        for value in ("a\nb", "a|b\nc", " a | b "):
            with self.subTest(value=value):
                self.assertEqual(split_multi_values(value), split_multi_value(value))

    def test_a_non_default_separator_still_behaves_as_before(self) -> None:
        from export.report_helpers import split_multi_values

        self.assertEqual(split_multi_values("a,b", sep=","), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
