from __future__ import annotations

import unittest

from modules.cookie_parser import (
    extract_cookie_from_curl,
    extract_cookie_from_headers,
    extract_cookie_from_plain_text,
    extract_cookie_from_text,
    mask_cookie_for_log,
    normalize_cookie,
)


class CookieParserTests(unittest.TestCase):
    def test_extract_plain_cookie(self) -> None:
        self.assertEqual(extract_cookie_from_plain_text("SUB=abc; SCF=def"), "SUB=abc; SCF=def")

    def test_extract_headers_cookie(self) -> None:
        text = "GET / HTTP/1.1\nHost: weibo.com\nCookie: SUB=abc; SCF=def\n"
        self.assertEqual(extract_cookie_from_headers(text), "SUB=abc; SCF=def")

    def test_extract_curl_cookie(self) -> None:
        text = "curl 'https://weibo.com' -H 'cookie: SUB=abc; SCF=def'"
        self.assertEqual(extract_cookie_from_curl(text), "SUB=abc; SCF=def")
        self.assertEqual(extract_cookie_from_text("curl x --cookie 'SUB=abc; SCF=def'"), "SUB=abc; SCF=def")

    def test_normalize_cookie(self) -> None:
        self.assertEqual(normalize_cookie(" SUB = abc ; ; SCF= def ; SUB=ignored "), "SUB=abc; SCF=def")

    def test_mask_cookie_for_log(self) -> None:
        masked = mask_cookie_for_log("SUB=abcdefghijklmnopqrstuvwxyz; SCF=123456")
        self.assertIn("SUB=abc...xyz", masked)
        self.assertIn("SCF=***", masked)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", masked)


if __name__ == "__main__":
    unittest.main()
