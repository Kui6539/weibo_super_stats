from __future__ import annotations

import math
from functools import lru_cache

from export.image_report.models import ImageReportConfig, PageBlock, PostBlock

PAGE_VERTICAL_CHROME = 210
POST_GAP = 34
POST_CARD_BASE = 146
COMMENT_SECTION_BASE = 72
COMMENT_GAP = 16
HEIGHT_SAFETY_FACTOR = 1.22
POST_IMAGE_WIDTH_RATIO = 0.88
PLANNING_HEIGHT_HEADROOM = 0.96


def paginate_posts(posts: list[PostBlock], config: ImageReportConfig) -> list[PageBlock]:
    rows = list(posts)
    if not rows:
        return [PageBlock(number=1, posts=[], estimated_height=PAGE_VERTICAL_CHROME)]
    for post in rows:
        post.estimated_height = estimate_post_height(post, config.width)

    natural = _greedy_pages(rows, config)
    natural_count = len(natural)
    min_pages = max(1, math.ceil(len(rows) / config.max_posts_per_page))
    max_pages = min(config.max_pages, len(rows))
    best: tuple[float, list[PageBlock]] | None = None

    for count in range(min_pages, max_pages + 1):
        partition = _best_partition_for_count(rows, config, count)
        if not partition:
            continue
        score = _score_partition(partition, config, natural_count)
        if best is None or score < best[0]:
            best = (score, partition)

    pages = best[1] if best else natural
    for index, page in enumerate(pages, start=1):
        page.number = index
    return pages


def estimate_post_height(post: PostBlock, page_width: int) -> int:
    content_width = max(520, page_width - 180)
    body_lines = _line_count(post.content, content_width, font_size=31)
    body_height = max(52, body_lines * 43)
    post_image_width = int(content_width * POST_IMAGE_WIDTH_RATIO)
    image_height = sum(
        126 if not image.exists else _image_display_height(image.width, image.height, post_image_width)
        for image in post.images
    )
    if len(post.images) > 1:
        image_height += (len(post.images) - 1) * 22

    comment_height = 0
    if post.comments:
        comment_height += COMMENT_SECTION_BASE
        for comment in post.comments:
            lines = _line_count(_comment_text(comment.user_name, comment.text), content_width - 42, font_size=27)
            comment_height += 42 + max(38, lines * 36)
            for image in comment.images:
                comment_height += 126 if not image.exists else _image_display_height(image.width, image.height, content_width - 68)
            if comment.images:
                comment_height += len(comment.images) * 14
        comment_height += max(0, len(post.comments) - 1) * COMMENT_GAP

    return int((POST_CARD_BASE + body_height + image_height + comment_height) * HEIGHT_SAFETY_FACTOR)


def _best_partition_for_count(
    posts: list[PostBlock],
    config: ImageReportConfig,
    page_count: int,
) -> list[PageBlock] | None:
    n = len(posts)

    @lru_cache(maxsize=None)
    def solve(start: int, pages_left: int) -> tuple[float, tuple[int, ...]] | None:
        remaining = n - start
        if pages_left == 0:
            return (0.0, ()) if remaining == 0 else None
        if remaining < pages_left or remaining > pages_left * config.max_posts_per_page:
            return None

        best: tuple[float, tuple[int, ...]] | None = None
        max_take = min(config.max_posts_per_page, remaining - pages_left + 1)
        for take in range(1, max_take + 1):
            page_posts = posts[start : start + take]
            height = _page_height(page_posts)
            overflow = max(0, height - _planning_max_height(config))
            if overflow and take > 1:
                continue
            rest = solve(start + take, pages_left - 1)
            if rest is None:
                continue
            local_score = (overflow * overflow * 20) + height
            score = local_score + rest[0]
            sizes = (take, *rest[1])
            if best is None or score < best[0]:
                best = (score, sizes)
        return best

    solved = solve(0, page_count)
    if solved is None:
        return None
    pages: list[PageBlock] = []
    start = 0
    for number, size in enumerate(solved[1], start=1):
        page_posts = posts[start : start + size]
        pages.append(PageBlock(number=number, posts=page_posts, estimated_height=_page_height(page_posts)))
        start += size
    return _rebalance_partition(pages, config)


def _rebalance_partition(pages: list[PageBlock], config: ImageReportConfig) -> list[PageBlock]:
    changed = True
    while changed:
        changed = False
        heights = [page.estimated_height for page in pages]
        if not heights:
            return pages
        high_index = heights.index(max(heights))
        low_index = heights.index(min(heights))
        if abs(high_index - low_index) != 1:
            break
        high = pages[high_index]
        low = pages[low_index]
        if len(high.posts) <= 1 or len(low.posts) >= config.max_posts_per_page:
            break
        if high_index < low_index:
            moving = high.posts[-1]
            next_high = high.posts[:-1]
            next_low = [moving, *low.posts]
        else:
            moving = high.posts[0]
            next_high = high.posts[1:]
            next_low = [*low.posts, moving]
        next_heights = [_page_height(next_high), _page_height(next_low)]
        if max(next_heights) < max(high.estimated_height, low.estimated_height):
            high.posts = next_high
            low.posts = next_low
            high.estimated_height = next_heights[0]
            low.estimated_height = next_heights[1]
            changed = True
    return pages


def _greedy_pages(posts: list[PostBlock], config: ImageReportConfig) -> list[PageBlock]:
    pages: list[PageBlock] = []
    current: list[PostBlock] = []
    for post in posts:
        candidate = [*current, post]
        if (
            current
            and (len(candidate) > config.max_posts_per_page or _page_height(candidate) > config.max_page_height)
        ):
            pages.append(PageBlock(number=len(pages) + 1, posts=current, estimated_height=_page_height(current)))
            current = [post]
        else:
            current = candidate
    if current:
        pages.append(PageBlock(number=len(pages) + 1, posts=current, estimated_height=_page_height(current)))
    return pages


def _score_partition(pages: list[PageBlock], config: ImageReportConfig, natural_count: int) -> float:
    heights = [page.estimated_height for page in pages]
    avg = sum(heights) / max(1, len(heights))
    balance = sum((height - avg) ** 2 for height in heights) / 900
    overflow = sum(max(0, height - _planning_max_height(config)) ** 2 for height in heights) * 40
    short = sum(max(0, avg * 0.48 - height) ** 2 for height in heights) / 1200
    return _page_count_penalty(len(pages), natural_count, sum(len(page.posts) for page in pages)) + balance + overflow + short


def _page_count_penalty(page_count: int, natural_count: int, post_count: int) -> float:
    preferred = page_count in {3, 4, 6, 9}
    if preferred:
        base = 0
    elif post_count <= 5 and page_count == natural_count:
        base = 0
    else:
        base = 90000
    return base + abs(page_count - natural_count) * 5200


def _page_height(posts: list[PostBlock]) -> int:
    if not posts:
        return PAGE_VERTICAL_CHROME
    return PAGE_VERTICAL_CHROME + sum(post.estimated_height for post in posts) + max(0, len(posts) - 1) * POST_GAP


def _planning_max_height(config: ImageReportConfig) -> int:
    return max(1, int(config.max_page_height * PLANNING_HEIGHT_HEADROOM))


def _line_count(text: str, width: int, font_size: int) -> int:
    chars_per_line = max(12, int(width / (font_size * 0.92)))
    total = 0
    for raw in str(text or "").splitlines() or [""]:
        line = raw.strip()
        total += max(1, math.ceil(_weighted_len(line) / chars_per_line))
    return total


def _weighted_len(text: str) -> float:
    total = 0.0
    for char in text:
        total += 1.0 if ord(char) > 127 else 0.56
    return total


def _image_display_height(width: int, height: int, display_width: int) -> int:
    if width <= 0 or height <= 0:
        return 360
    ratio = height / width
    return int(display_width * ratio)


def _comment_text(user_name: str, text: str) -> str:
    if user_name and text:
        return f"{user_name}：{text}"
    return text or user_name
