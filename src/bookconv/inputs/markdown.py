"""Markdown 输入插件：每个标题一页（标题 + 其下的正文）。

标题级别是相对的：文档里最高一级的标题算 1 级，下一级算 2 级，依此类推。
例如只有 ``##`` 时，``##`` 就是 1 级章节；有 ``# 卷一`` + ``## 第一章`` 时，
``#`` 是 1 级、``##`` 是 2 级，两页都会单独生成 XHTML 文件。

每个标题页的内容是这个标题之后、下一个标题之前的内容。因此 ``## 第一章``
的页面里是第一章的正文；遇到 ``### 小节`` 时，小节会另起一页。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import markdown

from ..htmlutil import escape, plain_text, rewrite_images, strip_paragraph_indent
from ..images import ImageStore
from ..models import Chapter
from .base import InputFormat, ParseOptions, SourceFile

#: python-markdown 扩展：extra 含表格/围栏代码/属性列表等，toc 给标题加 id
MARKDOWN_EXTENSIONS = ["extra", "toc"]

#: 匹配 1-6 个 # 的 ATX 标题（允许最多 3 个前导空格）
HEADING_RE = re.compile(r"^( {0,3})(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
HEADING_TAG_RE = re.compile(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>",
                            re.IGNORECASE | re.DOTALL)
FULLWIDTH_INDENT_RE = re.compile(r"^(\u3000+)")


@dataclass
class MarkdownSection:
    """一个标题页：原始标题、标题级别、该页的 Markdown 片段。"""

    title: str
    level: int          #: 1-6；0 表示第一个标题之前的前言
    chunk: str


def _iter_heading_lines(text: str):
    """逐行产出 (原始行, 标题匹配)；围栏/缩进代码块里的 # 不算标题。"""
    fence: Optional[str] = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            yield line, None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            yield line, None
            continue
        if line.startswith("    ") or line.startswith("\t"):
            yield line, None
            continue
        yield line, HEADING_RE.match(line)


def detect_heading_level(text: str) -> Optional[int]:
    """返回文档里最高一级标题的级别（1-6）；没有标题返回 None。"""
    levels = [len(matched.group(2)) for _, matched in _iter_heading_lines(text)
              if matched is not None]
    return min(levels) if levels else None


def split_sections(text: str) -> List[MarkdownSection]:
    """把 Markdown 切成“每个标题一页”，标题行和其后的正文放在同一页。"""
    sections: List[MarkdownSection] = []
    title = ""
    level = 0
    lines: List[str] = []

    def flush() -> None:
        nonlocal title, level, lines
        if title or any(line.strip() for line in lines):
            sections.append(MarkdownSection(title, level, "\n".join(lines)))
        title, level, lines = "", 0, []

    for line, matched in _iter_heading_lines(text):
        if matched is not None:
            flush()
            title = matched.group(3).strip()
            level = len(matched.group(2))
            lines = [line]
            continue
        lines.append(line)

    flush()
    return sections


def _section_body(section: MarkdownSection) -> str:
    """标题行之后、下一个标题之前的正文（去掉首尾空白）。"""
    lines = section.chunk.splitlines()
    return "\n".join(lines[1:]).strip()


def _heading_title(section: MarkdownSection) -> str:
    lines = section.chunk.splitlines()
    heading = render_markdown(lines[0]) if lines else ""
    matched = HEADING_TAG_RE.search(heading)
    return plain_text(matched.group(1)) if matched else section.title


def _page_heading(html: str, fallback: str):
    """把页面里第一个 Markdown 标题换成统一的章节标题 h1。"""
    matched = HEADING_TAG_RE.search(html)
    if matched is None:
        title = fallback or "正文"
        return (title,
                '<h1 class="chapter-title">%s</h1>\n%s'
                % (escape(title), html))

    inner = matched.group(1)
    title = plain_text(inner) or fallback or "正文"
    id_match = re.search(r'\bid=["\']([^"\']+)["\']', matched.group(0))
    anchor = ' id="%s"' % escape(id_match.group(1)) if id_match else ""
    page = (html[:matched.start()]
            + '<h1 class="chapter-title"%s>%s</h1>' % (anchor, inner)
            + html[matched.end():])
    return title, page


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS,
                             output_format="xhtml")


def preserve_leading_indent(text: str) -> str:
    """把行首的全角空格换成字符实体。

    python-markdown 会 strip 掉段落开头的空白（包括全角空格），想保留源文件的
    缩进就只能换成实体；围栏代码块里不能换，否则会变成字面量。
    """
    lines = []
    fence = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence is None and (stripped.startswith("```")
                              or stripped.startswith("~~~")):
            fence = stripped[:3]
            lines.append(line)
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            lines.append(line)
            continue

        matched = FULLWIDTH_INDENT_RE.match(line)
        if matched:
            width = len(matched.group(1))
            line = "&#x3000;" * width + line[width:]
        lines.append(line)
    return "\n".join(lines)


class MarkdownInput(InputFormat):
    name = "markdown"
    extensions = ("md", "markdown", "mdown", "mkd")

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        sections = split_sections(source.text)
        base_level = detect_heading_level(source.text)
        has_titles = any(section.level > 0 for section in sections)
        chapters: List[Chapter] = []

        for index, section in enumerate(sections):
            if section.level > 0:
                level = max(1, section.level - (base_level or section.level) + 1)
                has_child = (index + 1 < len(sections)
                             and sections[index + 1].level > section.level)
                if not _section_body(section) and has_child:
                    # 只有卷/节标题、下面直接是子标题：目录里保留分组，不建空页
                    chapters.append(Chapter(_heading_title(section), "",
                                            level=level, virtual=True))
                    continue

            chunk = section.chunk
            if options.keep_indent:
                chunk = preserve_leading_indent(chunk)
            html = render_markdown(chunk)
            if not options.keep_indent:
                html = strip_paragraph_indent(html)
            html = rewrite_images(html, source.base_dir, images,
                                  href_prefix="../")

            if section.level == 0:
                title = "前言" if has_titles else "正文"
                level = 1
                if has_titles:
                    html = ('<h1 class="chapter-title">%s</h1>\n%s'
                            % (escape(title), html))
            else:
                title, html = _page_heading(html, section.title)

            chapters.append(Chapter(title=title, html=html, level=level))

        return chapters


__all__ = ["MarkdownInput", "MarkdownSection", "detect_heading_level",
           "split_sections", "render_markdown", "preserve_leading_indent"]
