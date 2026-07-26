from __future__ import annotations

import html
import os
import re
from pathlib import Path

from export.image_report.models import (
    CommentBlock,
    ImageAsset,
    ImageReportConfig,
    ImageReportData,
    PageBlock,
    PostBlock,
)


def render_preview_html(
    data: ImageReportData,
    pages: list[PageBlock],
    config: ImageReportConfig,
    output_dir: Path,
) -> str:
    style = _style(config)
    page_html = "\n".join(_render_page(data, page, len(pages), config, output_dir) for page in pages)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width={config.width}, initial-scale=1" />
    <title>{_e(_display_title(data))}</title>
    <style>
{style}
    </style>
  </head>
  <body>
    <main class="preview-stage">
{page_html}
    </main>
  </body>
</html>
"""


def _render_page(
    data: ImageReportData,
    page: PageBlock,
    page_count: int,
    config: ImageReportConfig,
    output_dir: Path,
) -> str:
    posts = "\n".join(_render_post(post, output_dir, data.emoticons) for post in page.posts)
    if not posts:
        posts = '<section class="empty-card">暂无入选帖子</section>'
    return f"""      <section class="report-page" data-page="{page.number}" style="width: {config.width}px">
        <div class="decor decor-dot decor-dot-a"></div>
        <div class="decor decor-dot decor-dot-b"></div>
        <div class="decor decor-spark decor-spark-a">✦</div>
        <header class="page-header">
          <h1>{_e(_display_title(data))}</h1>
          <p class="date-range">{_e(data.date_range)}</p>
        </header>
        <div class="post-stack">
{posts}
        </div>
        <footer class="page-footer">
          <span>Made for Weibo</span>
          <span>{_e(_english_topic_label(data))}</span>
        </footer>
      </section>"""


def _render_post(post: PostBlock, output_dir: Path, emoticons: dict[str, str]) -> str:
    stats = [
        ("点赞", post.likes),
        ("评论", post.comments_count),
        ("转发", post.reposts),
        ("综合分", f"{post.score:.2f}" if post.score else "-"),
    ]
    stat_html = "".join(f'<span><b>{_e(value)}</b>{_e(label)}</span>' for label, value in stats)
    image_html = "".join(_render_image(image, output_dir, "post-image") for image in post.images)
    comments = "".join(_render_comment(comment, output_dir, emoticons) for comment in post.comments)
    comments_html = (
        f"""          <section class="comment-card">
            <div class="comment-title">热评</div>
            <div class="comment-list">
{comments}
            </div>
          </section>"""
        if comments
        else ""
    )
    return f"""          <article class="post-block" data-post-id="{_attr(post.post_id)}">
            <section class="main-card">
              <div class="post-head">
                <div>
                  <span class="rank">No. {post.rank:02d}</span>
                  <strong>@{_e(post.author)}</strong>
                  <small>{_e(post.publish_time)}</small>
                </div>
              </div>
              <div class="post-content">{_render_inline_text(post.content or "（无正文）", emoticons)}</div>
              <div class="image-flow">
{image_html}
              </div>
              <div class="stats-row">{stat_html}</div>
            </section>
{comments_html}
          </article>"""


def _render_comment(comment: CommentBlock, output_dir: Path, emoticons: dict[str, str]) -> str:
    user = f'<strong>@{_e(comment.user_name)}</strong>' if comment.user_name else ""
    images = "".join(_render_image(image, output_dir, "comment-image") for image in comment.images)
    return f"""              <div class="comment-item">
                <div class="comment-meta">{user}</div>
                <div class="comment-text">{_render_inline_text(comment.text or "（图片评论）", emoticons)}</div>
                <div class="comment-images">{images}</div>
              </div>"""


def _render_inline_text(text: str, emoticons: dict[str, str]) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    if not emoticons:
        return _e(raw)

    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\[([^\[\]\r\n]{1,24})\]", raw):
        parts.append(_e(raw[cursor : match.start()]))
        token = match.group(0)
        name = match.group(1).strip()
        src = emoticons.get(name)
        if src:
            parts.append(
                f'<img class="weibo-emoticon" src="{_attr(src)}" alt="{_attr(token)}" title="{_attr(token)}" />'
            )
        else:
            parts.append(_e(token))
        cursor = match.end()
    parts.append(_e(raw[cursor:]))
    return "".join(parts)


def _render_image(image: ImageAsset, output_dir: Path, class_name: str) -> str:
    src = _asset_src(image, output_dir)
    if not src:
        note = image.note or "图片加载失败"
        return f'<div class="image-placeholder {_attr(class_name)}">{_e(note)}</div>'
    return f'<img class="{_attr(class_name)}" src="{_attr(src)}" alt="{_attr(image.alt)}" loading="eager" />'


def _asset_src(image: ImageAsset, output_dir: Path) -> str:
    if not image.local_path:
        return ""
    path = Path(image.local_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        return Path(os.path.relpath(path.resolve(), output_dir.resolve())).as_posix()
    except Exception:
        return path.resolve().as_uri()


def _display_title(data: ImageReportData) -> str:
    title = data.title.strip() or "微博超话周报"
    issue = data.issue.strip()
    if issue:
        normalized_issue = issue
        if normalized_issue.startswith("第") and normalized_issue.endswith("期"):
            normalized_issue = normalized_issue[1:-1].strip()
        if f"第{normalized_issue}期" not in title:
            return f"{title} 第{normalized_issue}期"
    return title


def _english_topic_label(data: ImageReportData) -> str:
    title = data.title.strip()
    title = re.sub(r"\s*第[^\s]+期\s*$", "", title)
    title = title.removesuffix("周报").removesuffix("超话").strip()
    return f"{title or 'Weibo'} Super Topic"


def _style(config: ImageReportConfig) -> str:
    font_face = _font_face(config)
    return f"""
{font_face}
:root {{
  --page-width: {config.width}px;
  --paper: #ffe7a8;
  --paper-deep: #f6cf75;
  --cream: #fffaf0;
  --cream-strong: #fff3cf;
  --comment-bg: #f7ddba;
  --comment-item: #fff7e7;
  --ink: #5a321d;
  --soft-ink: #865535;
  --line: #e9bd70;
  --shadow: rgba(92, 54, 24, 0.14);
}}
* {{
  box-sizing: border-box;
}}
html,
body {{
  margin: 0;
  min-height: 100%;
  background: #f2dfbc;
  color: var(--ink);
  font-family: "WeiboImageReport", "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
}}
.preview-stage {{
  display: grid;
  gap: 32px;
  justify-content: center;
  padding: 32px;
}}
.report-page {{
  position: relative;
  overflow: hidden;
  padding: 46px 48px 42px;
  background:
    radial-gradient(circle at 9% 7%, rgba(255, 255, 255, 0.52) 0 72px, transparent 74px),
    linear-gradient(180deg, var(--paper), #ffefbe 45%, #ffe1a0);
  border: 3px solid #e8ba65;
  border-radius: 36px;
  box-shadow: 0 16px 42px var(--shadow);
}}
.page-header {{
  position: relative;
  z-index: 1;
  margin-bottom: 38px;
  text-align: center;
}}
h1 {{
  margin: 0;
  color: var(--ink);
  font-size: 50px;
  line-height: 1.18;
  letter-spacing: 0;
}}
.date-range {{
  margin: 12px 0 0;
  color: var(--soft-ink);
  font-size: 26px;
  line-height: 1.3;
}}
.post-stack {{
  position: relative;
  z-index: 1;
  display: grid;
  gap: 34px;
}}
.post-block {{
  display: grid;
  gap: 10px;
}}
.main-card,
.comment-card,
.empty-card {{
  border: 2px solid rgba(137, 78, 31, 0.18);
  border-radius: 30px;
  box-shadow: 0 12px 26px rgba(88, 47, 21, 0.10);
}}
.main-card {{
  padding: 30px 34px 34px;
  background: var(--cream);
}}
.post-head {{
  display: flex;
  justify-content: space-between;
  gap: 22px;
  align-items: flex-start;
}}
.post-head strong {{
  display: inline-block;
  margin-left: 10px;
  color: var(--ink);
  font-size: 30px;
  line-height: 1.25;
}}
.post-head small {{
  display: block;
  margin-top: 8px;
  color: var(--soft-ink);
  font-size: 21px;
}}
.rank {{
  display: inline-block;
  padding: 7px 13px;
  border-radius: 999px;
  background: #f2cb75;
  color: #674020;
  font-size: 20px;
  font-weight: 900;
}}
.stats-row {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 24px 0 0;
}}
.stats-row span {{
  min-width: 0;
  padding: 14px 8px;
  border-radius: 20px;
  background: var(--cream-strong);
  color: var(--soft-ink);
  font-size: 18px;
  line-height: 1.25;
  text-align: center;
}}
.stats-row b {{
  display: block;
  color: var(--ink);
  font-size: 24px;
  line-height: 1.2;
}}
.post-content,
.comment-text {{
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
.weibo-emoticon {{
  display: inline-block;
  width: 1.22em;
  height: 1.22em;
  margin: 0 0.04em;
  object-fit: contain;
  vertical-align: -0.22em;
}}
.post-content {{
  color: #55301d;
  font-size: 31px;
  line-height: 1.42;
}}
.image-flow,
.comment-images {{
  display: grid;
  gap: 22px;
  margin-top: 26px;
}}
.post-image,
.comment-image {{
  display: block;
  height: auto;
  border-radius: 24px;
  border: 2px solid rgba(126, 73, 31, 0.13);
  background: #fff3d6;
}}
.post-image {{
  width: 88%;
  margin-inline: auto;
}}
.comment-image {{
  width: 100%;
}}
.comment-card {{
  padding: 24px 28px 28px;
  background: var(--comment-bg);
}}
.comment-title {{
  display: inline-block;
  margin-bottom: 18px;
  padding: 8px 16px;
  border-radius: 999px;
  background: #8a5632;
  color: #fff6e6;
  font-size: 22px;
  font-weight: 900;
}}
.comment-list {{
  display: grid;
  gap: 16px;
}}
.comment-item {{
  padding: 20px 22px;
  border-radius: 24px;
  background: var(--comment-item);
  border: 2px solid rgba(142, 84, 41, 0.11);
}}
.comment-meta {{
  margin-bottom: 10px;
  color: var(--soft-ink);
  font-size: 22px;
  line-height: 1.3;
}}
.comment-text {{
  color: #5c3723;
  font-size: 27px;
  line-height: 1.42;
}}
.comment-image {{
  border-radius: 20px;
}}
.image-placeholder {{
  display: grid;
  min-height: 126px;
  place-items: center;
  padding: 24px;
  border: 2px dashed #c99452;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.45);
  color: var(--soft-ink);
  font-size: 24px;
  font-weight: 800;
}}
.page-footer {{
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  margin-top: 34px;
  color: rgba(88, 52, 29, 0.62);
  font-size: 18px;
  font-weight: 700;
}}
.empty-card {{
  padding: 56px;
  background: var(--cream);
  color: var(--soft-ink);
  font-size: 28px;
  text-align: center;
}}
.decor {{
  position: absolute;
  pointer-events: none;
  opacity: 0.42;
}}
.decor-dot {{
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #bc7c3b;
}}
.decor-dot-a {{
  right: 56px;
  top: 172px;
}}
.decor-dot-b {{
  left: 38px;
  bottom: 82px;
  width: 15px;
  height: 15px;
}}
.decor-spark {{
  color: #9b622f;
  font-size: 38px;
  line-height: 1;
}}
.decor-spark-a {{
  right: 112px;
  bottom: 54px;
}}
@media print {{
  .preview-stage {{
    padding: 0;
    gap: 0;
  }}
}}
"""


def _font_face(config: ImageReportConfig) -> str:
    if not config.font_path:
        return ""
    path = Path(config.font_path)
    if not path.exists() or not path.is_file():
        return ""
    return f"""@font-face {{
  font-family: "WeiboImageReport";
  src: url("{path.resolve().as_uri()}") format("opentype");
  font-weight: 400 900;
}}"""


def _e(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _attr(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)
