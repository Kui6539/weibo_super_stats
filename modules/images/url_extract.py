from __future__ import annotations

import re
from typing import Any

from modules.weibo_url import normalize_image_url, to_absolute_url


def to_original_pic_url(url: str) -> str:
    return normalize_image_url(url)


def split_url_candidates(text: str) -> list[str]:
    return split_multi_urls(text, sep=",")


def split_multi_urls(text: str, sep: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(sep) if part.strip()]
    return [to_absolute_url(part) for part in parts]


def guess_image_ext(url: str) -> str:
    match = re.search(r"(\.(?:jpg|jpeg|png|gif|webp))(?:[?#].*)?$", str(url or ""), flags=re.I)
    if match:
        return match.group(1).lower()
    return ".jpg"


def extract_sinaimg_host(url: str) -> str:
    match = re.search(r"https?://([^/]*sinaimg\.cn)/", str(url or ""), flags=re.I)
    return match.group(1) if match else ""


def dedup_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def collect_top_comment_image_urls(top_comments: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for comment in top_comments[:3]:
        if not isinstance(comment, dict):
            continue
        urls.extend(collect_comment_image_urls(comment))
    return dedup_image_urls(urls)


def extract_status_image_urls(status: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    if not isinstance(status, dict):
        return urls
    urls.extend(extract_urls_from_data_node(status.get("pic_infos")))
    urls.extend(extract_urls_from_data_node(status.get("pic")))
    urls.extend(extract_urls_from_data_node(status.get("url_struct")))
    urls.extend(extract_urls_from_data_node(status.get("url_objects")))
    urls.extend(extract_urls_from_data_node(status.get("mix_media_info")))
    return dedup_image_urls(urls)


def collect_comment_image_urls(comment: dict[str, Any]) -> list[str]:
    if not isinstance(comment, dict):
        return []
    urls: list[str] = []
    direct = comment.get("image_urls")
    if isinstance(direct, str):
        urls.extend(split_multi_urls(direct, sep="|"))
    elif isinstance(direct, list):
        urls.extend([str(item) for item in direct if str(item).strip()])
    for key in ("pic", "pic_infos", "url_struct", "url_objects", "mix_media_info"):
        urls.extend(extract_urls_from_data_node(comment.get(key)))
    return dedup_image_urls(urls)


def dedup_image_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = to_original_pic_url(str(raw))
        if not looks_like_image_url(url):
            continue
        sig = image_signature(url)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(url)
    return out


def image_signature(url: str) -> str:
    clean = to_absolute_url(url).split("?", 1)[0].split("#", 1)[0]
    match = re.search(r"/([A-Za-z0-9]+)\.(?:jpg|jpeg|png|gif|webp)$", clean, flags=re.I)
    if match:
        return match.group(1).lower()
    return clean.lower()


def extract_urls_from_data_node(node: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(node, str):
        maybe = to_absolute_url(node)
        if looks_like_image_url(maybe):
            urls.append(maybe)
        return urls
    if isinstance(node, list):
        for item in node:
            urls.extend(extract_urls_from_data_node(item))
        return urls
    if isinstance(node, dict):
        for key in ("url", "ori_url", "pic", "pic_url", "thumbnail_pic", "bmiddle_pic", "original_pic"):
            value = node.get(key)
            if isinstance(value, str):
                maybe = to_absolute_url(value)
                if looks_like_image_url(maybe):
                    urls.append(maybe)
            elif isinstance(value, dict):
                nested = value.get("url")
                if isinstance(nested, str):
                    maybe = to_absolute_url(nested)
                    if looks_like_image_url(maybe):
                        urls.append(maybe)
        for key in ("large", "largest", "orj360", "mw2000", "mw690"):
            value = node.get(key)
            if isinstance(value, dict):
                maybe = to_absolute_url(str(value.get("url") or ""))
                if looks_like_image_url(maybe):
                    urls.append(maybe)
        for value in node.values():
            if isinstance(value, (dict, list)):
                urls.extend(extract_urls_from_data_node(value))
    return urls


def looks_like_image_url(url: str) -> bool:
    candidate = to_absolute_url(url)
    if not candidate:
        return False
    if re.search(r"\.(?:jpg|jpeg|png|gif|webp)(?:[?#].*)?$", candidate, flags=re.I):
        return True
    return "sinaimg.cn" in candidate.lower()
