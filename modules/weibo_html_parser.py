from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl

from bs4 import BeautifulSoup, Tag

from modules.images.url_extract import (
    dedup_keep_order,
    extract_sinaimg_host,
    guess_image_ext,
    split_url_candidates,
    to_original_pic_url,
)
from modules.text_cleaning import clean_topic_tags, collapse_blank_lines, normalize_weibo_text
from modules.weibo_url import to_absolute_url

FM_VIEW_MARKER = "FM.view("
FORWARDED_NODE_TYPES = {
    "feed_list_forwardContent",
    "feed_list_forwardContent_full",
}
FORWARDED_CLASS_NAMES = {
    "WB_feed_expand",
    "WB_feed_expand_v2",
    "WB_expand",
    "WB_feed_expand_media",
}


def extract_feed_html_from_page(page_html: str) -> str:
    objects = parse_fm_view_objects(page_html)
    if not objects:
        raise ValueError("页面中未找到 FM.view 数据块，无法解析帖子列表。")

    for obj in objects:
        domid = str(obj.get("domid", ""))
        html = obj.get("html")
        if domid.startswith("Pl_Core_MixedFeed__") and isinstance(html, str) and "feed_list_item" in html:
            return html

    html_candidates = [
        obj.get("html", "")
        for obj in objects
        if isinstance(obj.get("html"), str) and "feed_list_item" in obj.get("html", "")
    ]
    if html_candidates:
        return max(html_candidates, key=len)

    raise ValueError("页面结构已变化：未在 FM.view 中找到帖子列表 HTML。")


def parse_fm_view_objects(page_html: str) -> list[dict]:
    results: list[dict] = []
    cursor = 0
    while True:
        idx = page_html.find(FM_VIEW_MARKER, cursor)
        if idx < 0:
            break

        payload_start = idx + len(FM_VIEW_MARKER)
        payload_start = _skip_space(page_html, payload_start)
        if payload_start >= len(page_html) or page_html[payload_start] != "{":
            cursor = payload_start + 1
            continue

        payload_end = _find_json_object_end(page_html, payload_start)
        if payload_end < 0:
            cursor = payload_start + 1
            continue

        payload = page_html[payload_start : payload_end + 1]
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                results.append(obj)
        except Exception:
            pass
        cursor = payload_end + 1
    return results


def parse_posts_from_html(html: str) -> list[dict]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    items = [item for item in soup.select("div[action-type='feed_list_item']") if not _is_nested_feed_item(item)]
    posts: list[dict] = []
    for item in items:
        post_id = item.get("mid") or item.get("data-mid") or ""
        user_name = _extract_user_name(item)
        author_id = _extract_author_id(item)
        publish_time = _extract_publish_time(item)
        post_url = _extract_post_url(item)
        original_image_urls = _extract_original_image_urls(item)
        content = clean_topic_tags(_remove_expand_hint_preserve(_extract_content(item)), preserve_newlines=True)
        has_video = _extract_has_video(item)
        reposts = _extract_action_count(item, ["feed_list_forward", "fl_forward"])
        comments = _extract_action_count(item, ["feed_list_comment", "fl_comment"])
        likes = _extract_action_count(item, ["feed_list_like", "fl_like"])

        posts.append(
            {
                "post_id": str(post_id),
                "author_id": str(author_id),
                "user_name": user_name,
                "publish_time": publish_time,
                "post_url": post_url,
                "original_image_urls": " | ".join(original_image_urls),
                "image_count": len(original_image_urls),
                "downloaded_image_count": 0,
                "image_local_paths": "",
                "content": content,
                "has_video": has_video,
                "reposts": reposts,
                "comments": comments,
                "likes": likes,
                "non_author_comments": 0,
                "author_replies": 0,
                "topic_comment_factor": 1.0,
                "score": 0.0,
                "top_comment_1": "",
                "top_comment_2": "",
                "top_comment_3": "",
                "top_comment_count": 0,
                "engagement_total": reposts + comments + likes,
            }
        )
    return posts


def parse_count(text: str) -> int:
    raw = normalize_weibo_text(text)
    if not raw:
        return 0
    match = re.search(r"(\d+(?:\.\d+)?)\s*万", raw)
    if match:
        return int(float(match.group(1)) * 10000)
    match = re.search(r"(\d+)", raw)
    if match:
        return int(match.group(1))
    return 0


def is_inside_forwarded_content(node: Tag, root: Tag | None = None) -> bool:
    return _is_inside_forwarded_content(node, root)


def extract_original_image_urls(item: Tag) -> list[str]:
    return _extract_original_image_urls(item)


def _skip_space(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index] in (" ", "\n", "\r", "\t"):
        index += 1
    return index


def _find_json_object_end(text: str, obj_start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[obj_start:], start=obj_start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _is_nested_feed_item(item: Tag) -> bool:
    parent = item.parent
    while isinstance(parent, Tag):
        if parent.get("action-type") == "feed_list_item":
            return True
        if _is_forwarded_content_container(parent):
            return True
        parent = parent.parent
    return False


def _select_outer(root: Tag, selector: str) -> list[Tag]:
    return [
        node
        for node in root.select(selector)
        if isinstance(node, Tag) and not _is_inside_forwarded_content(node, root)
    ]


def _select_one_outer(root: Tag, selector: str) -> Tag | None:
    for node in _select_outer(root, selector):
        return node
    return None


def _is_inside_forwarded_content(node: Tag, root: Tag | None = None) -> bool:
    current: Tag | None = node if isinstance(node, Tag) else None
    while isinstance(current, Tag):
        if root is not None and current is root:
            return False
        if _is_forwarded_content_container(current):
            return True
        if root is not None and current is not node and current.get("action-type") == "feed_list_item":
            return True
        current = current.parent if isinstance(current.parent, Tag) else None
    return False


def _is_forwarded_content_container(node: Tag) -> bool:
    node_type = str(node.get("node-type") or "").strip()
    if node_type in FORWARDED_NODE_TYPES:
        return True
    classes = node.get("class") or []
    if isinstance(classes, str):
        class_names = classes.split()
    else:
        class_names = [str(item) for item in classes]
    return any(name in FORWARDED_CLASS_NAMES or name.startswith("WB_feed_expand") for name in class_names)


def _extract_user_name(item: Tag) -> str:
    selectors = [
        "a[node-type='feed_list_item_name']",
        "a.W_f14.W_fb.S_txt1[usercard]",
        "a[usercard][nick-name]",
        "a[usercard]",
    ]
    for selector in selectors:
        text = _first_text(_select_outer(item, selector))
        if text:
            return normalize_weibo_text(text)
    return ""


def _extract_author_id(item: Tag) -> str:
    tbinfo = str(item.get("tbinfo") or "")
    match = re.search(r"ouid=(\d+)", tbinfo)
    if match:
        return match.group(1)

    anchor = _select_one_outer(item, "a[usercard]")
    if anchor:
        usercard = str(anchor.get("usercard") or "")
        match = re.search(r"id=(\d+)", usercard)
        if match:
            return match.group(1)
    return ""


def _extract_publish_time(item: Tag) -> str:
    date_link = _select_one_outer(item, "a[node-type='feed_list_item_date']")
    if not date_link:
        return ""
    title = date_link.get("title")
    if title:
        return normalize_weibo_text(str(title))
    return normalize_weibo_text(date_link.get_text(" ", strip=True))


def _extract_content(item: Tag) -> str:
    selectors = [
        "div[node-type='feed_list_content_full']",
        "p[node-type='feed_list_content_full']",
        "div[node-type='feed_list_content']",
        "p[node-type='feed_list_content']",
    ]
    texts: list[str] = []
    for selector in selectors:
        for node in _select_outer(item, selector):
            text = collapse_blank_lines(node.get_text("\n", strip=True))
            if text:
                texts.append(text)
    if not texts:
        return ""
    return _remove_expand_hint(max(texts, key=len))


def _extract_has_video(item: Tag) -> bool:
    selectors = [
        ".WB_video",
        "video",
        "[action-type='feed_list_media_play']",
        "[action-type='feed_list_media_video']",
        "[node-type='fl_h5_video']",
        "a[suda-data*='video']",
    ]
    for selector in selectors:
        if _select_one_outer(item, selector):
            return True
    return False


def _extract_post_url(item: Tag) -> str:
    date_link = _select_one_outer(item, "a[node-type='feed_list_item_date']")
    if not date_link:
        return ""
    href = str(date_link.get("href") or "").strip()
    return to_absolute_url(href)


def _extract_original_image_urls(item: Tag) -> list[str]:
    urls: list[str] = []

    for node in _select_outer(item, ".WB_media_a[action-data], .WB_media_wrap[action-data]"):
        action_data = str(node.get("action-data") or "")
        if "pic" not in action_data.lower():
            continue
        pairs = dict(parse_qsl(action_data))
        clear_pic_src = pairs.get("clear_picSrc") or ""
        urls.extend(to_original_pic_url(candidate) for candidate in split_url_candidates(clear_pic_src))

    for media_node in _select_outer(item, "[action-type='feed_list_media_img']"):
        action_data = str(media_node.get("action-data") or "")
        pairs = dict(parse_qsl(action_data))
        pid_text = str(pairs.get("pic_ids") or pairs.get("pid") or "").strip()
        if not pid_text:
            continue
        pids = [item.strip() for item in pid_text.split(",") if item.strip()]
        img = media_node.select_one("img")
        img_src = to_absolute_url(str((img.get("src") if img else "") or ""))
        ext = guess_image_ext(img_src)
        host = extract_sinaimg_host(img_src) or "wx1.sinaimg.cn"
        urls.extend(f"https://{host}/large/{pid}{ext}" for pid in pids)
        if img_src:
            urls.append(to_original_pic_url(img_src))

    return dedup_keep_order([url for url in urls if url])


def _extract_action_count(item: Tag, action_types: list[str]) -> int:
    best = 0
    for action_type in action_types:
        for action in _select_outer(item, f"a[action-type='{action_type}']"):
            text = normalize_weibo_text(action.get_text(" ", strip=True))
            best = max(best, parse_count(text))
    return best


def _remove_expand_hint(text: str) -> str:
    raw = normalize_weibo_text(text)
    raw = re.sub(r"(展开全文|展开原文)\s*[cC]?", " ", raw)
    return normalize_weibo_text(raw)


def _remove_expand_hint_preserve(text: str) -> str:
    raw = collapse_blank_lines(text)
    raw = re.sub(r"(展开全文|展开原文)\s*[cC]?", " ", raw)
    return collapse_blank_lines(raw)


def _first_text(elements: list) -> str:
    if not elements:
        return ""
    return elements[0].get_text(" ", strip=True)
