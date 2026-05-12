from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.crawler_filters import should_exclude_post
from modules.text_cleaning import clean_topic_tags, collapse_blank_lines, normalize_weibo_text
from modules.time_utils import parse_weibo_time


def format_posts_date_range(posts: list[dict[str, Any]]) -> str:
    dates: list[datetime] = []
    for post in posts:
        dt = parse_weibo_time(str(post.get("publish_time", "") or ""))
        if dt:
            dates.append(dt)
    if not dates:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"{today} 至 {today}"
    start = min(dates).strftime("%Y-%m-%d")
    end = max(dates).strftime("%Y-%m-%d")
    return f"{start} 至 {end}"


def split_multi_values(text: str, sep: str = "|") -> list[str]:
    raw = str(text or "")
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(sep)]
    return [part for part in parts if part]


def to_rel_path(base_dir: Path, target: Path) -> str:
    try:
        rel = target.resolve().relative_to(base_dir.resolve())
        return str(rel).replace("\\", "/")
    except Exception:
        return str(target.resolve()).replace("\\", "/")


def select_weekly_posts(posts: Iterable[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    rows = list(posts)
    selected = [row for row in rows if not should_exclude_post(row)[0]]
    return selected[: max(1, limit)]


def iter_report_comments(post: dict[str, Any]) -> list[dict[str, Any]]:
    top_comments = post.get("top_comments_data") or []
    result: list[dict[str, Any]] = []
    if isinstance(top_comments, list) and top_comments:
        for item in top_comments[:3]:
            if not isinstance(item, dict):
                continue
            image_urls = split_multi_values(str(item.get("image_urls") or ""), sep="|")
            image_local_paths = split_multi_values(str(item.get("image_local_paths") or ""), sep="|")
            text = normalize_report_text(str(item.get("text", "") or ""), preserve_newlines=True)
            if image_urls or image_local_paths:
                text = strip_url_like_text(text)
            result.append(
                {
                    "user_name": normalize_weibo_text(str(item.get("user_name", "") or "")),
                    "text": text,
                    "image_urls": " | ".join(image_urls),
                    "image_local_paths": " | ".join(image_local_paths),
                }
            )
    if result:
        return result

    fallback = [
        normalize_weibo_text(str(post.get("top_comment_1", "") or "")),
        normalize_weibo_text(str(post.get("top_comment_2", "") or "")),
        normalize_weibo_text(str(post.get("top_comment_3", "") or "")),
    ]
    return [{"user_name": "", "text": item, "image_urls": "", "image_local_paths": ""} for item in fallback if item]


def format_hot_comment_text(comment: dict[str, Any]) -> str:
    user = normalize_weibo_text(str(comment.get("user_name", "") or ""))
    text = normalize_report_text(str(comment.get("text", "") or ""), preserve_newlines=True)
    if user and text:
        return f"{user}：{text}"
    if text:
        return text
    if user and split_multi_values(str(comment.get("image_local_paths") or ""), sep="|"):
        return f"{user}： （图片评论）"
    return ""


def clean_report_text(text: str) -> str:
    raw = clean_topic_tags(collapse_blank_lines(text), preserve_newlines=True)
    raw = replace_weibo_emoticons(raw)
    raw = replace_unicode_emoji(raw)
    # 去掉微博字体图标的私有区字符、零宽字符，避免周报里出现乱码方块。
    raw = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", raw)
    raw = raw.replace("\ufe0f", "")
    raw = re.sub(r"[\ue000-\uf8ff]", "", raw)
    return collapse_blank_lines(raw)


def normalize_report_text(text: str, preserve_newlines: bool = False) -> str:
    return collapse_blank_lines(text) if preserve_newlines else normalize_weibo_text(text)


def strip_url_like_text(text: str) -> str:
    raw = normalize_weibo_text(text)
    raw = re.sub(r"https?://\S+", " ", raw, flags=re.I)
    raw = re.sub(r"\b(?:t\.cn|weibo\.cn|weibo\.com)/\S+", " ", raw, flags=re.I)
    raw = re.sub(r"(网页链接|网页链接\:?)", " ", raw, flags=re.I)
    raw = re.sub(r"\s{2,}", " ", raw)
    return raw.strip()


def simplify_hot_comment(text: str) -> str:
    raw = normalize_weibo_text(text)
    match = re.match(r"^(.*?)（赞.*?）:\s*(.*)$", raw)
    if match:
        user = normalize_weibo_text(match.group(1))
        content = normalize_weibo_text(match.group(2))
        return f"{user}：{content}"
    return raw


def replace_weibo_emoticons(text: str) -> str:
    mapping = {
        "抱一抱": "(づ｡◕‿‿◕｡)づ",
        "抱抱": "(づ￣ 3￣)づ",
        "打call": "ヾ(≧▽≦*)o",
        "哈哈": "(๑>◡<๑)",
        "嘻嘻": "(*^▽^*)",
        "可爱": "(=^･ω･^=)",
        "爱你": "( ˘ ³˘)♥",
        "亲亲": "( ˘ ³˘)♥",
        "鼓掌": "(*'ω'ﾉﾉﾞ☆",
        "送花花": "(✿◡‿◡)",
        "赞": "(๑•̀ㅂ•́)و",
        "ok": "(๑•̀ㅂ•́)و",
        "笑cry": "(≧▽≦;)",
        "笑哭": "(≧▽≦;)",
        "偷笑": "(￣▽￣)~*",
        "憨笑": "(≧∀≦)ゞ",
        "doge": "(￣▽￣)",
        "doge脸": "(￣▽￣)",
        "二哈": "(哈▽哈)",
        "允悲": "(；▽；)",
        "泪": "(T_T)",
        "流泪": "(；﹏；)",
        "泪奔": "(ಥ_ಥ)",
        "悲伤": "(Q_Q)",
        "大哭": "(╥﹏╥)",
        "委屈": "(｡•́︿•̀｡)",
        "可怜": "(´；ω；`)",
        "思考": "( •̀ .̫ •́ )",
        "疑问": "( ?_? )",
        "跪了": "_(:3」∠)_",
        "馋嘴": "(๑´ڡ`๑)",
        "干饭人": "(๑´ڡ`๑)",
        "裂开": "(⊙_⊙;)",
        "苦涩": "(＞﹏＜)",
        "哇": "(✧ω✧)",
        "心": "<3",
        "给你小心心": "<3<3",
    }

    def repl(match: re.Match[str]) -> str:
        key = normalize_weibo_text(match.group(1))
        return mapping.get(key, "(๑•ᴗ•๑)")

    return re.sub(r"\[([^\[\]]{1,24})\]", repl, text)


def replace_unicode_emoji(text: str) -> str:
    emoji_map = {
        "😀": "(*^_^*)",
        "😄": "(*^o^*)",
        "😁": "(๑>◡<๑)",
        "😆": "(≧ω≦)",
        "😊": "(*^_^*)",
        "😍": "(=^.^=)",
        "🥰": "(=^.^=)",
        "😘": "(*^3^*)",
        "😋": "(^q^)",
        "🤗": "(*^_^*)",
        "😇": "(^_^)v",
        "😎": "B-)",
        "😂": "(≧▽≦;)",
        "🤣": "xD",
        "😹": "(=^▽^=;)",
        "😅": "(*^_^*;)",
        "😢": "(；﹏；)",
        "😭": "(╥﹏╥)",
        "🥲": "(´；ω；`)",
        "😿": "(T_T)",
        "🥺": "(｡•́︿•̀｡)",
        "🤔": "( •̀ .̫ •́ )",
        "😴": "(-_-) zzz",
        "😐": "( -_- )",
        "😑": "( -_- )",
        "😶": "( ._. )",
        "❤": "<3",
        "❤️": "<3",
        "💗": "<3",
        "💖": "<3",
        "💘": "<3",
        "💕": "<3",
        "💞": "<3",
        "✨": "(*_*)",
        "🌟": "(*_*)",
        "👍": "(^_^)v",
        "👏": "(*'ω'ﾉﾉﾞ☆",
        "🙏": "(*^_^*)",
    }
    out = text
    for emoji, face in emoji_map.items():
        out = out.replace(emoji, face)
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "(๑•ᴗ•๑)", out)
