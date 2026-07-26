"""Tests for reading weibo cookies out of a DevTools endpoint.

This path had no coverage at all: the discovery calls went straight to urlopen,
so exercising them needed a real browser on a real debug port. Every network
call now takes a ``fetch`` parameter, and the WebSocket a ``connect``, so the
whole flow runs on canned data.

No real cookie values appear here -- ``SUB=fake-...`` is a placeholder chosen so
a grep for leaked credentials stays quiet.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from modules.cookie_cdp import (
    CDP_ENV_VAR,
    cdp_endpoints,
    cookie_rank,
    cookies_to_header,
    domain_applies_to_weibo,
    page_websockets,
    read_cookie_from_cdp,
    read_cookie_from_endpoint,
)

FAKE_SUB = "fake-login-token"


def cookie(name: str, value: str = "v", domain: str = ".weibo.com", path: str = "/") -> dict:
    return {"name": name, "value": value, "domain": domain, "path": path}


class EndpointDiscoveryTests(unittest.TestCase):
    def test_the_environment_override_wins(self) -> None:
        with mock.patch.dict(os.environ, {CDP_ENV_VAR: "http://127.0.0.1:9999/"}):
            self.assertEqual(cdp_endpoints("edge"), ["http://127.0.0.1:9999"])

    def test_each_browser_has_its_own_port(self) -> None:
        with mock.patch.dict(os.environ, {CDP_ENV_VAR: ""}):
            self.assertIn("http://127.0.0.1:9222", cdp_endpoints("edge"))
            self.assertIn("http://127.0.0.1:9223", cdp_endpoints("chrome"))

    def test_without_a_browser_both_default_ports_are_tried(self) -> None:
        with mock.patch.dict(os.environ, {CDP_ENV_VAR: ""}):
            self.assertEqual(len(cdp_endpoints()), 2)


class CookieHeaderTests(unittest.TestCase):
    def test_a_header_is_built_from_weibo_cookies(self) -> None:
        header = cookies_to_header([cookie("SUB", FAKE_SUB), cookie("SUBP", "abc")])
        self.assertIn(f"SUB={FAKE_SUB}", header)
        self.assertIn("SUBP=abc", header)

    def test_without_the_login_cookie_nothing_is_returned(self) -> None:
        """A jar that cannot log in is worse than no jar: it looks like success."""
        self.assertEqual(cookies_to_header([cookie("SUBP", "abc"), cookie("SCF", "d")]), "")

    def test_cookies_from_other_sites_are_ignored(self) -> None:
        header = cookies_to_header([cookie("SUB", FAKE_SUB), cookie("SUB", "other", domain=".example.com")])
        self.assertIn(f"SUB={FAKE_SUB}", header)
        self.assertNotIn("other", header)

    def test_the_root_path_entry_wins_a_duplicate_name(self) -> None:
        """Both are real cookies; the root one is what weibo.com receives."""
        header = cookies_to_header(
            [cookie("SUB", "scoped", path="/nested"), cookie("SUB", FAKE_SUB, path="/")]
        )
        self.assertIn(f"SUB={FAKE_SUB}", header)
        self.assertNotIn("scoped", header)

    def test_empty_names_and_values_are_skipped(self) -> None:
        self.assertEqual(cookies_to_header([cookie("", "x"), cookie("SUB", "")]), "")

    def test_domain_matching_ignores_the_leading_dot_and_case(self) -> None:
        for domain in (".weibo.com", "weibo.com", "WEIBO.COM"):
            with self.subTest(domain=domain):
                self.assertTrue(domain_applies_to_weibo(domain))
        for domain in ("example.com", "notweibo.com", "weibo.com.evil.net", ""):
            with self.subTest(domain=domain):
                self.assertFalse(domain_applies_to_weibo(domain))

    def test_root_paths_outrank_scoped_ones(self) -> None:
        self.assertGreater(cookie_rank({"path": "/"}), cookie_rank({"path": "/x"}))
        self.assertEqual(cookie_rank({"path": ""}), cookie_rank({"path": "/"}))


class PageTargetDiscoveryTests(unittest.TestCase):
    def test_page_and_webview_targets_are_collected(self) -> None:
        def fetch(url, _timeout):
            return [
                {"type": "page", "webSocketDebuggerUrl": "ws://a"},
                {"type": "background_page", "webSocketDebuggerUrl": "ws://skip"},
                {"type": "webview", "webSocketDebuggerUrl": "ws://b"},
                {"type": "page"},
            ]

        self.assertEqual(page_websockets("http://x", fetch=fetch), ["ws://a", "ws://b"])

    def test_a_tab_is_opened_only_when_none_exist(self) -> None:
        """Opening a tab is visible to the user, so it must be a last resort."""
        calls: list[str] = []

        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            calls.append(target)
            if target.endswith("/json/list"):
                return []
            return {"webSocketDebuggerUrl": "ws://new-tab"}

        self.assertEqual(page_websockets("http://x", fetch=fetch), ["ws://new-tab"])
        self.assertTrue(any("/json/new" in call for call in calls))

    def test_no_tab_is_opened_when_a_page_already_exists(self) -> None:
        calls: list[str] = []

        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            calls.append(target)
            return [{"type": "page", "webSocketDebuggerUrl": "ws://existing"}]

        page_websockets("http://x", fetch=fetch)
        self.assertFalse(any("/json/new" in call for call in calls))

    def test_a_listing_failure_degrades_to_opening_a_tab(self) -> None:
        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            if target.endswith("/json/list"):
                raise OSError("connection refused")
            return {"webSocketDebuggerUrl": "ws://new-tab"}

        self.assertEqual(page_websockets("http://x", fetch=fetch), ["ws://new-tab"])


class EndpointReadTests(unittest.TestCase):
    def test_an_unreachable_port_is_reported_not_raised(self) -> None:
        def fetch(*_args):
            raise OSError("connection refused")

        cookie_header, err = read_cookie_from_endpoint("http://x", fetch=fetch)
        self.assertEqual(cookie_header, "")
        self.assertIn("未连接到调试端口", err)

    def test_a_page_target_supplies_the_cookie(self) -> None:
        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            if target.endswith("/json/version"):
                return {"webSocketDebuggerUrl": "ws://browser"}
            return [{"type": "page", "webSocketDebuggerUrl": "ws://page"}]

        with mock.patch(
            "modules.cookie_cdp.cookies_from_page_target", return_value=(f"SUB={FAKE_SUB}", None)
        ):
            cookie_header, err = read_cookie_from_endpoint("http://x", fetch=fetch)

        self.assertEqual(cookie_header, f"SUB={FAKE_SUB}")
        self.assertIsNone(err)

    def test_the_browser_target_is_the_fallback(self) -> None:
        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            if target.endswith("/json/version"):
                return {"webSocketDebuggerUrl": "ws://browser"}
            return []

        with (
            mock.patch("modules.cookie_cdp.page_websockets", return_value=[]),
            mock.patch(
                "modules.cookie_cdp.cookies_from_browser_target", return_value=(f"SUB={FAKE_SUB}", None)
            ),
        ):
            cookie_header, err = read_cookie_from_endpoint("http://x", fetch=fetch)

        self.assertEqual(cookie_header, f"SUB={FAKE_SUB}")
        self.assertIsNone(err)

    def test_a_connected_browser_with_no_login_says_so(self) -> None:
        """The actionable case: the port works, the user just is not logged in."""

        def fetch(url_or_request, _timeout):
            target = getattr(url_or_request, "full_url", url_or_request)
            if target.endswith("/json/version"):
                return {"webSocketDebuggerUrl": "ws://browser"}
            return []

        with (
            mock.patch("modules.cookie_cdp.page_websockets", return_value=[]),
            mock.patch("modules.cookie_cdp.cookies_from_browser_target", return_value=("", "no cookies")),
        ):
            cookie_header, err = read_cookie_from_endpoint("http://x", "Edge", fetch=fetch)

        self.assertEqual(cookie_header, "")
        self.assertIn("请在调试 Edge 窗口登录微博后重试", err)

    def test_a_malformed_version_response_is_rejected(self) -> None:
        cookie_header, err = read_cookie_from_endpoint("http://x", fetch=lambda *_: "not json")
        self.assertEqual(cookie_header, "")
        self.assertIn("格式异常", err)


class MultiEndpointTests(unittest.TestCase):
    def test_the_first_endpoint_that_answers_wins(self) -> None:
        with mock.patch(
            "modules.cookie_cdp.read_cookie_from_endpoint",
            side_effect=[("", "down"), (f"SUB={FAKE_SUB}", None)],
        ):
            cookie_header, err = read_cookie_from_cdp("edge", endpoints=["http://a", "http://b"])
        self.assertEqual(cookie_header, f"SUB={FAKE_SUB}")
        self.assertIsNone(err)

    def test_every_failure_is_reported_together(self) -> None:
        with mock.patch(
            "modules.cookie_cdp.read_cookie_from_endpoint",
            side_effect=[("", "down"), ("", "no login")],
        ):
            cookie_header, err = read_cookie_from_cdp("edge", endpoints=["http://a", "http://b"])
        self.assertEqual(cookie_header, "")
        self.assertIn("http://a: down", err)
        self.assertIn("http://b: no login", err)

    def test_no_endpoints_at_all_is_its_own_message(self) -> None:
        cookie_header, err = read_cookie_from_cdp("edge", endpoints=[])
        self.assertEqual(cookie_header, "")
        self.assertIn("未配置 CDP 调试端口", err)


class CompatibilityTests(unittest.TestCase):
    def test_the_old_private_name_still_forwards(self) -> None:
        """cookie_helper._try_get_cookie_header_from_cdp predates the split."""
        import cookie_helper

        with mock.patch("cookie_helper.read_cookie_from_cdp", return_value=("SUB=x", None)) as forwarded:
            self.assertEqual(cookie_helper._try_get_cookie_header_from_cdp("edge"), ("SUB=x", None))
        forwarded.assert_called_once_with("edge")

    def test_modules_no_longer_reach_into_cookie_helper_privates(self) -> None:
        """A module must not import a private name from the layer above it."""
        import ast
        from pathlib import Path

        tree = ast.parse(Path("modules/cookie_edge_debug.py").read_text(encoding="utf-8"))
        imported_privates = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("cookie_helper")
            for alias in node.names
            if alias.name.startswith("_")
        ]
        self.assertEqual(imported_privates, [])


if __name__ == "__main__":
    unittest.main()
