from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.crawler_filters import should_exclude_post
from modules.post_normalizer import split_multi_value
from modules.text_cleaning import (
    clean_topic_tags,
    collapse_blank_lines,
    normalize_weibo_text,
    remove_weibo_private_chars,
)
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
    """Split a "|"-joined field, delegating to the shared normalizer.

    This used to be its own implementation that ignored list input and did not
    treat newlines as separators, so a newline-separated image path field came
    out empty in Markdown and the long-image report while DOCX and Excel read
    it fine. Every caller passes the default separator; the parameter is kept
    so any other value still behaves as before.
    """
    if sep == "|":
        return split_multi_value(text)
    parts = [part.strip() for part in str(text or "").split(sep)]
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
        return f"{user}：（图片评论）"
    return ""


def clean_report_text(text: str) -> str:
    raw = clean_topic_tags(collapse_blank_lines(text), preserve_newlines=True)
    raw = replace_weibo_emoticons(raw)
    raw = replace_unicode_emoji(raw)
    raw = remove_weibo_private_chars(raw)
    return collapse_blank_lines(raw)


def clean_image_report_text(text: str) -> str:
    raw = clean_topic_tags(collapse_blank_lines(text), preserve_newlines=True)
    raw = remove_weibo_private_chars(raw)
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
    match = re.match(r"^(.*?)（赞.*?）\s*(.*)$", raw)
    if match:
        user = normalize_weibo_text(match.group(1))
        content = normalize_weibo_text(match.group(2))
        return f"{user}：{content}"
    return raw


def replace_weibo_emoticons(text: str) -> str:
    mapping = {
        "抱一抱": "(つ´ω`)つ",
        "抱抱": "(つ´ω`)つ",
        "打call": "٩(ˊᗜˋ*)و",
        "哈哈": "(*≧▽≦)",
        "嘻嘻": "(*^▽^*)",
        "笑cry": "(*≧▽≦)ﾉｼ",
        "笑哭": "(*≧▽≦)ﾉｼ",
        "偷笑": "( *´艸`)",
        "憧憬": "(*´▽`*)",
        "可爱": "(｡･ω･｡)",
        "爱你": "(´▽`ʃ♡ƪ)",
        "亲亲": "(づ￣ ³￣)づ",
        "鼓掌": "(*'▽'*)ﾉﾞ",
        "送花花": "(ﾉ´ヮ`)ﾉ*:･ﾟ✧",
        "赞": "(๑•̀ㅂ•́)و✧",
        "ok": "(๑•̀ㅂ•́)و✧",
        "泪": "(；ω；)",
        "流泪": "(；ω；)",
        "泪奔": "(；ω；)",
        "悲伤": "(｡•́︿•̀｡)",
        "大哭": "(╥﹏╥)",
        "委屈": "(｡•́︿•̀｡)",
        "允悲": "(；´д｀)ゞ",
        "苦涩": "(｡•́︿•̀｡)",
        "哼": "(｀へ´*)ノ",
        "doge": "( •̀ ω •́ )",
        "doge脸": "( •̀ ω •́ )",
        "二哈": "(´･ᴗ･`)",
        "疑问": "(・_・?)",
        "思考": "(｡･ˇ_ˇ･｡)",
        "裂开": "(つд⊂)",
        "跪了": "_(:3」∠)_",
        "馋嘴": "(๑´ڡ`๑)",
        "干饭人": "(๑´ڡ`๑)",
        "心": "♡",
        "给你小心心": "♡♡",
    }

    def repl(match: re.Match[str]) -> str:
        key = normalize_weibo_text(match.group(1))
        # Anything not in the table is ordinary bracketed text -- [公告],
        # [抽奖规则], [视频] -- and must survive verbatim. Substituting a
        # default kaomoji corrupted post content. The long-image renderer has
        # always kept unknown tokens; this brings the other exporters in line.
        return mapping.get(key, match.group(0))

    return re.sub(r"\[([^\[\]]{1,24})\]", repl, text)


def format_leaderboard_line(
    item: dict[str, Any],
    include_hot: bool = True,
    include_quality: bool = False,
    include_like_total: bool = True,
    include_post_span: bool = False,
) -> str:
    """Render one leaderboard row.

    Single source of truth for both the initial export and reexport. They used
    different formatters, so regenerating a report silently downgraded the
    leaderboards -- losing the rank, the @ prefix, the like totals and the
    hot-comment counts.
    """
    rank = int(item.get("rank", 0) or 0)
    user_name = clean_report_text(str(item.get("user_name", "") or "匿名用户"))
    comment_count = int(item.get("comment_count", 0) or 0)
    commented_post_count = int(item.get("commented_post_count", 0) or 0)
    like_total = int(item.get("comment_likes_total", 0) or 0)
    hot_count = int(item.get("hot_top3_count", 0) or 0)
    line = f"{rank}. @{user_name}：评论 {comment_count} 条"
    if include_post_span:
        line += f"，评论过 {commented_post_count} 条帖子"
    elif include_like_total:
        line += f"，本周评论获赞 {like_total}"
    if include_hot:
        line += f"，热评前三 {hot_count} 次"
    if include_quality:
        line += f"，质量分 {float(item.get('quality_score', 0.0)):.4f}"
    return line


def replace_unicode_emoji(text: str) -> str:
    emoji_map = {
        "😄": "(*^▽^*)",
        "😃": "(*^▽^*)",
        "😁": "(*≧▽≦)",
        "😂": "(*≧▽≦)ﾉｼ",
        "🤣": "(*≧▽≦)ﾉｼ",
        "😊": "(*´▽`*)",
        "🥰": "(´▽`ʃ♡ƪ)",
        "😍": "(´▽`ʃ♡ƪ)",
        "😘": "(づ￣ ³￣)づ",
        "😋": "(๑´ڡ`๑)",
        "😆": "(*^▽^*)",
        "😎": "( •̀ ω •́ )✧",
        "😅": "(*^▽^*;)",
        "😭": "(╥﹏╥)",
        "😢": "(；ω；)",
        "🥹": "(；ω；)",
        "😔": "(｡•́︿•̀｡)",
        "😡": "(｀へ´*)ノ",
        "😠": "(｀へ´*)ノ",
        "😴": "(¦3[▓▓]",
        "👍": "(๑•̀ㅂ•́)و✧",
        "👏": "(*'▽'*)ﾉﾞ",
        "🙏": "(*´人`*)",
        "❤️": "♡",
        "❤": "♡",
        "💕": "♡♡",
        "💖": "♡♡",
        "💗": "♡♡",
        "💙": "♡",
        "✨": "✧",
        "🌟": "✧",
    }
    out = text
    for emoji, face in emoji_map.items():
        out = out.replace(emoji, face)
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "(｡･ω･｡)", out)
