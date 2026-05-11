from __future__ import annotations


def read_cookie_from_edge_store() -> str:
    import browser_cookie3 as bc3
    from cookie_helper import _try_loader

    cookie, _err = _try_loader(bc3.edge, domain_name="weibo.com")
    return cookie


def read_cookie_from_chrome_store() -> str:
    import browser_cookie3 as bc3
    from cookie_helper import _try_loader

    cookie, _err = _try_loader(bc3.chrome, domain_name="weibo.com")
    return cookie


def read_cookie_from_browser_store() -> str:
    edge_cookie = read_cookie_from_edge_store()
    if edge_cookie:
        return edge_cookie
    return read_cookie_from_chrome_store()
