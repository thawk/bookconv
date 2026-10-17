"""一个够用的 Markdown 子集渲染器（只依赖标准库）。

小说里常见的写法都支持：标题、段落、分隔线、引用、围栏代码块、无序/有序列表、
插图、链接、粗体/斜体/行内代码、硬换行。表格、脚注、嵌套列表没有实现。

之所以不直接用 markdown 库：这个工具想做到"拷到哪都能跑"，不装任何包。
"""

from __future__ import annotations

import html as html_lib
import re
from typing import List, Tuple

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^(```+|~~~+)\s*(\S*)\s*$")
HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")

#: 行内代码、图片、链接
CODE_RE = re.compile(r"`([^`\n]+)`")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"([^\"]*)\")?\s*\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)(?:\s+\"([^\"]*)\")?\s*\)")
RAW_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
ENTITY_RE = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")

#: 占位符（\x00 不会出现在正文里）
PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def _escape(text: str) -> str:
    return html_lib.escape(text, quote=False)


def _escape_attr(text: str) -> str:
    return html_lib.escape(text, quote=True)


def _escape_text(text: str) -> str:
    """转义 & < >，但保留已有的 HTML 实体。"""
    parts: List[str] = []
    pos = 0
    for matched in ENTITY_RE.finditer(text):
        parts.append(_escape(text[pos:matched.start()]))
        parts.append(matched.group(0))
        pos = matched.end()
    parts.append(_escape(text[pos:]))
    return "".join(parts)


class _Slugger(object):
    """给标题生成唯一 id。"""

    def __init__(self) -> None:
        self._seen = {}

    def slug(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = html_lib.unescape(text)
        slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip()).strip("-")
        slug = slug or "section"
        count = self._seen.get(slug, 0)
        self._seen[slug] = count + 1
        return slug if count == 0 else "%s-%d" % (slug, count)


def render_inline(text: str) -> str:
    """渲染行内语法。"""
    stash: List[str] = []

    def keep(fragment: str) -> str:
        stash.append(fragment)
        return "\x00%d\x00" % (len(stash) - 1)

    # 反斜杠转义
    text = ESCAPE_RE.sub(lambda m: keep(_escape(m.group(1))), text)
    # 行内代码
    text = CODE_RE.sub(
        lambda m: keep("<code>%s</code>" % _escape(m.group(1))), text)
    # 原始 HTML 标签原样保留
    text = RAW_TAG_RE.sub(lambda m: keep(m.group(0)), text)
    # 图片、链接
    text = IMAGE_RE.sub(
        lambda m: keep('<img src="%s" alt="%s"/>' % (_escape_attr(m.group(2)),
                                                     _escape_attr(m.group(1)))),
        text)
    text = LINK_RE.sub(
        lambda m: keep('<a href="%s">%s</a>' % (_escape_attr(m.group(2)),
                                                _escape(m.group(1)))),
        text)
    # 其余文本转义
    text = _escape_text(text)
    # 强调
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"___(.+?)___", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    # 行尾两个空格 = 硬换行
    text = text.replace("  \n", "<br />\n")

    while "\x00" in text:
        text = PLACEHOLDER_RE.sub(lambda m: stash[int(m.group(1))], text)
    return text


def _is_block_start(line: str) -> bool:
    return bool(FENCE_RE.match(line) or HEADING_RE.match(line)
                or HR_RE.match(line) or QUOTE_RE.match(line)
                or UL_RE.match(line) or OL_RE.match(line))


def _render_list(lines: List[str], index: int) -> Tuple[str, int]:
    ordered = bool(OL_RE.match(lines[index]))
    pattern = OL_RE if ordered else UL_RE
    items = []

    while index < len(lines):
        matched = pattern.match(lines[index])
        if not matched:
            break
        item = [matched.group(1)]
        index += 1
        while (index < len(lines) and lines[index].strip()
               and not pattern.match(lines[index])
               and not _is_block_start(lines[index])):
            item.append(lines[index].strip())
            index += 1
        items.append("<li>%s</li>" % render_inline(" ".join(item)))

    tag = "ol" if ordered else "ul"
    return "<%s>%s</%s>" % (tag, "".join(items), tag), index


def _render_blocks(lines: List[str], slugger: _Slugger) -> str:
    out: List[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        matched = FENCE_RE.match(line)
        if matched:
            fence = matched.group(1)[0] * 3
            language = matched.group(2)
            code: List[str] = []
            index += 1
            while index < total and not lines[index].strip().startswith(fence):
                code.append(lines[index])
                index += 1
            index += 1                       # 跳过结束围栏
            class_attr = (' class="language-%s"' % _escape_attr(language)
                          if language else "")
            out.append("<pre><code%s>%s</code></pre>"
                       % (class_attr, _escape("\n".join(code))))
            continue

        matched = HEADING_RE.match(line)
        if matched:
            level = len(matched.group(1))
            content = matched.group(2)
            out.append('<h%d id="%s">%s</h%d>'
                       % (level, _escape_attr(slugger.slug(content)),
                          render_inline(content), level))
            index += 1
            continue

        if HR_RE.match(line):
            out.append("<hr />")
            index += 1
            continue

        if QUOTE_RE.match(line):
            quoted: List[str] = []
            while index < total and QUOTE_RE.match(lines[index]):
                quoted.append(QUOTE_RE.match(lines[index]).group(1))
                index += 1
            out.append("<blockquote>%s</blockquote>"
                       % _render_blocks(quoted, slugger))
            continue

        if UL_RE.match(line) or OL_RE.match(line):
            html_list, index = _render_list(lines, index)
            out.append(html_list)
            continue

        paragraph = [line]
        index += 1
        while (index < total and lines[index].strip()
               and not _is_block_start(lines[index])):
            paragraph.append(lines[index])
            index += 1
        out.append("<p>%s</p>" % render_inline("\n".join(paragraph)))

    return "\n".join(out)


def render(text: str) -> str:
    """把 Markdown 文本渲染成 XHTML 片段。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return _render_blocks(lines, _Slugger())
