"""Request-origin guards for the local HTTP service.

The tool binds to 127.0.0.1 and has no authentication, which is fine for a
local tool right up until a web page the user has open starts talking to it.
Two distinct attacks are in scope:

CSRF
    A cross-site ``fetch`` with ``Content-Type: text/plain`` is a CORS "simple
    request": no preflight, and the browser sends it even though the response
    is unreadable. The side effect still happens -- ``/api/output/cleanup``
    with ``confirm: true`` deletes run directories, ``/api/config`` overwrites
    the stored cookie, ``/api/history/remove`` deletes real files.

DNS rebinding
    An attacker page on ``evil.example`` whose DNS is re-pointed at 127.0.0.1
    becomes same-origin with this server. Then the response *is* readable, and
    ``/api/cookie/auto`` hands over the user's live weibo login token.

Checking the Host header defeats rebinding (the browser keeps sending the
attacker's hostname), and checking Origin/Sec-Fetch-Site defeats CSRF.
"""

from __future__ import annotations

from urllib.parse import urlparse

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}

# Requests the browser labels as top-level navigations rather than script-driven
# fetches. A user typing the URL or following a bookmark sends no Origin.
_SAFE_FETCH_SITES = {"same-origin", "none"}


def host_is_local(host_header: str | None, expected_port: int | None = None) -> bool:
    """True when the Host header names this machine's loopback interface."""
    raw = (host_header or "").strip()
    if not raw:
        # HTTP/1.1 requires Host; a missing one is not something a browser does.
        return False
    hostname, _, port = _split_host_port(raw)
    if hostname.lower() not in _LOOPBACK_HOSTS:
        return False
    if expected_port is None or not port:
        return True
    return port == str(expected_port)


def origin_is_local(origin_header: str | None, expected_port: int | None = None) -> bool:
    """True when Origin is absent (same-origin fetch) or points back at us."""
    raw = (origin_header or "").strip()
    if not raw or raw == "null":
        # Same-origin fetches from our own page omit Origin on GET, and browsers
        # send it on POST -- an absent value cannot be forged cross-site.
        return True
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    if expected_port is None or parsed.port is None:
        return True
    return parsed.port == expected_port


def fetch_site_is_safe(sec_fetch_site: str | None) -> bool:
    """Reject Sec-Fetch-Site values that mark the request as cross-site.

    Absent means an older browser or a non-browser client (curl, our own
    tests); those still have to pass the Host and Origin checks.
    """
    raw = (sec_fetch_site or "").strip().lower()
    if not raw:
        return True
    return raw in _SAFE_FETCH_SITES


def content_type_is_json(content_type: str | None) -> bool:
    """Require an explicit JSON content type on bodies that change state.

    This is what actually blocks the text/plain simple-request bypass: a
    cross-site page cannot set application/json without triggering a preflight,
    and the preflight fails because we never answer OPTIONS with CORS headers.
    """
    raw = (content_type or "").strip().lower()
    if not raw:
        return False
    return raw.split(";", 1)[0].strip() == "application/json"


def _split_host_port(raw: str) -> tuple[str, str, str]:
    if raw.startswith("["):
        # IPv6 literal: [::1]:8765
        closing = raw.find("]")
        if closing == -1:
            return raw, "", ""
        host = raw[: closing + 1]
        rest = raw[closing + 1 :]
        port = rest[1:] if rest.startswith(":") else ""
        return host, ":", port
    host, sep, port = raw.partition(":")
    return host, sep, port
