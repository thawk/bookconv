"""Markdown 输入插件：按 ``#`` 标题分章。"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .. import markdown_lite
from ..htmlutil import escape, plain_text, rewrite_images, strip_paragraph_indent
from ..images import ImageStore
from ..models import Chapter
from .base import InputFormat, ParseOptions, SourceFile

H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$")
H1_TAG_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def split_chapters(text: str) -> List[Tuple[str, str]]:
    """按行首的 ``# 标题`` 分章。

    返回 [(章节标题, 该章的 markdown 文本)]；第一个 ``#`` 之前的内容标题为空串。
    围栏代码块和缩进代码块里的 ``#`` 不算标题。
    """
    chapters: List[Tuple[str, str]] = []
    title = ""
    lines: List[str] = []
    fence: Optional[str] = None

    def flush() -> None:
        nonlocal title, lines
        if title or any(line.strip() for line in lines):
            chapters.append((title, "\n".join(lines)))
        title, lines = "", []

    for line in text.splitlines():
        stripped = line.lstrip()

        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            lines.append(line)
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            lines.append(line)
            continue
        if line.startswith("    ") or line.startswith("\t"):
            lines.append(line)
            continue

        matched = H1_RE.match(line)
        if matched:
            flush()
            title = matched.group(1).strip()
            lines = [line]
            continue
        lines.append(line)

    flush()
    return chapters


def render_markdown(text: str) -> str:
    return markdown_lite.render(text)


class MarkdownInput(InputFormat):
    name = "markdown"
    extensions = ("md", "markdown", "mdown", "mkd")

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        chunks = split_chapters(source.text)
        has_titles = any(title for title, _ in chunks)
        chapters: List[Chapter] = []

        for title, chunk in chunks:
            html = render_markdown(chunk)
            if not options.keep_indent:
                html = strip_paragraph_indent(html)
            html = rewrite_images(html, source.base_dir, images, href_prefix="../")

            if not title:
                # 第一个 # 之前的内容：有章节标题时单独成“前言”页，否则只有正文
                title = "前言" if has_titles else "正文"
                if has_titles:
                    html = ('<h1 class="chapter-title">%s</h1>\n%s'
                            % (escape(title), html))
            else:
                matched = H1_TAG_RE.search(html)
                if matched:                  # 目录里用渲染后的纯文本标题
                    title = plain_text(matched.group(1)) or title

            chapters.append(Chapter(title=title, html=html, level=1))

        return chapters


__all__ = ["MarkdownInput", "split_chapters", "render_markdown"]
