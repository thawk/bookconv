"""AsciiDoc 输入插件。

只实现小说/技术书里常见的 AsciiDoc 子集，够用且不引入额外依赖：

* 文档头：``= 书名``、``:author:`` / ``:authors:``、``:description:``
* 章节：``== 第一章``（一级）、``=== 第一节``（二级）……
* 段落、列表（``*`` / ``-`` / ``.``）、定义列表、引用块、示例/侧栏
* ``----`` / ``....`` 代码块、``|===`` 表格、``image::`` / ``image:`` 插图
* ``*粗体*``、``_斜体_``、```等宽```、``#高亮#``、``^上标^``、``~下标~``、链接

刻意不处理：include、条件指令、属性替换、脚注编号引用等。它们要么依赖
完整的 Asciidoctor，要么对小说转换没有意义。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from ..htmlutil import escape, rewrite_images, strip_paragraph_indent
from ..images import ImageStore
from ..models import BookMeta, Chapter
from .base import InputFormat, ParseOptions, SourceFile

SECTION_RE = re.compile(r"^(={2,6})\s+(.+?)\s*(?:\1)?\s*$")
DOC_TITLE_RE = re.compile(r"^=\s+(.+?)\s*(?:=)?\s*$")
ATTR_RE = re.compile(r"^:([^:]+):\s*(.*?)\s*$")
BLOCK_ATTR_RE = re.compile(r"^\[([^\]]*)\]\s*$")
BLOCK_TITLE_RE = re.compile(r"^\.([^. \t　].*)$")
DELIM_RE = re.compile(r"^([/\+.\*_=-])\1{3,}\s*$")
TABLE_DELIM_RE = re.compile(r"^\|={3,}\s*$")
LIST_RE = re.compile(r"^(\s*)([*\-]+|\.+)\s+(.*)$")
DEFINITION_RE = re.compile(r"^(.+?)::\s*(.*)$")
RULER_RE = re.compile(r"^'{3,}\s*$")
IMAGE_BLOCK_RE = re.compile(r"^image::([^\s\[]+)\[([^\]]*)\]\s*$")
IMAGE_INLINE_RE = re.compile(r"image:([^\s\[]+)\[([^\]]*)\]")
COMMENT_BLOCK_RE = re.compile(r"^/{4,}\s*$")

#: 属性名 -> BookMeta 字段
META_KEYS = ("title", "author", "authors", "description", "abstract",
             "comments", "summary")


@dataclass
class Section:
    title: str
    level: int
    lines: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 文档头 / 章节切分


def split_document(text: str) -> Tuple[Dict[str, str], List[Section]]:
    """返回 (文档头属性, 章节列表)。

    第一个 ``==`` 之前的内容放在 level=0 的 section 里（可能是前言）。
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    attrs: Dict[str, str] = {}
    pos = 0

    while pos < len(lines) and not lines[pos].strip():
        pos += 1

    if pos < len(lines):
        matched = DOC_TITLE_RE.match(lines[pos])
        if matched:
            attrs["title"] = matched.group(1).strip()
            pos += 1

    # 文档头属性可以紧跟标题，也可以出现在正文之前
    while pos < len(lines):
        line = lines[pos]
        if not line.strip():
            pos += 1
            continue
        matched = ATTR_RE.match(line)
        if matched:
            name = matched.group(1).strip().lower()
            if name in META_KEYS:
                attrs[name] = matched.group(2).strip()
            pos += 1
            continue
        if line.lstrip().startswith("//") and not COMMENT_BLOCK_RE.match(line):
            pos += 1
            continue
        break

    sections: List[Section] = [Section("", 0, [])]
    in_comment = False
    for line in lines[pos:]:
        if COMMENT_BLOCK_RE.match(line):
            in_comment = not in_comment
            continue
        if in_comment:
            continue
        matched = SECTION_RE.match(line)
        if matched:
            level = len(matched.group(1)) - 1
            title = _section_title(matched.group(2))
            sections.append(Section(title, level, []))
        else:
            sections[-1].lines.append(line)
    return attrs, sections


def _section_title(title: str) -> str:
    title = re.sub(r"\[\[[^\]]*\]\]", "", title)
    title = re.sub(r"^\[#?[^\]]*\]\s*", "", title)
    return title.strip()


def _meta_from_attrs(attrs: Dict[str, str]) -> BookMeta:
    meta = BookMeta()
    meta.title = attrs.get("title", "")
    authors = attrs.get("authors") or attrs.get("author") or ""
    if authors:
        parts = re.split(r"\s*(?:[,，、;；&]|\band\b)\s*", authors)
        meta.authors = [part.strip() for part in parts if part.strip()]
    meta.comments = (attrs.get("description") or attrs.get("abstract")
                     or attrs.get("comments") or attrs.get("summary") or "")
    return meta


# ---------------------------------------------------------------------------
# 行内格式


def _split_attrs(text: str) -> List[str]:
    """``alt,width`` / ``alt="x",width=100`` 这类属性列表。"""
    result: List[str] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip().lower() in ("alt", "title"):
                result.append(value.strip().strip("\"'"))
            else:
                result.append("")
        else:
            result.append(part.strip().strip("\"'"))
    return result


def _image_attrs(spec: str) -> Tuple[str, str, str]:
    """返回 (alt, width, height)。"""
    parts = _split_attrs(spec)
    alt = parts[0] if parts else ""
    width = height = ""
    for part in parts[1:]:
        if re.fullmatch(r"\d+%?", part):
            if not width:
                width = part
            elif not height:
                height = part
    return alt, width, height


class _InlineRenderer:
    """把 AsciiDoc 行内标记转成 XHTML。"""

    def __init__(self) -> None:
        self._tokens: List[str] = []

    def _protect(self, html: str) -> str:
        self._tokens.append(html)
        return "\x00%d\x00" % (len(self._tokens) - 1)

    def render(self, text: str) -> str:
        text = escape(text)

        # 行内代码、图片、链接先替换成占位符，避免后续强调标记误伤
        text = re.sub(r"`([^`\n]+)`",
                      lambda m: self._protect("<code>%s</code>" % m.group(1)),
                      text)
        text = IMAGE_INLINE_RE.sub(self._image, text)
        text = re.sub(r"link:([^\s\[]+)\[([^\]]*)\]", self._link, text)
        text = re.sub(r"(https?://[^\s\[\]<>]+)\[([^\]]*)\]", self._link, text)
        text = re.sub(r"footnote:\[([^\]]*)\]",
                      lambda m: self._protect("<sup>%s</sup>" % m.group(1)),
                      text)

        # 强调
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__(.+?)__", r"<em>\1</em>", text)
        text = re.sub(r"\*([^*\n]+)\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
        text = re.sub(r"#([^#\n]+)#",
                      r'<span class="mark">\1</span>', text)
        text = re.sub(r"\^([^^\n]+)\^", r"<sup>\1</sup>", text)
        text = re.sub(r"~([^~\n]+)~", r"<sub>\1</sub>", text)
        text = re.sub(r"\+([^+\n]+)\+", r"<code>\1</code>", text)

        # 字符替换
        for source, target in (("(C)", "©"), ("(TM)", "™"), ("(R)", "®"),
                               ("--", "—"), ("...", "…"),
                               ("->", "→"), ("<-", "←")):
            text = text.replace(source, target)

        # 裸 URL
        text = re.sub(
            r"(?<![\"'=])(https?://[^\s<>\"'，。；：！？、]+)",
            lambda m: self._protect(
                '<a href="%s">%s</a>' % (m.group(1), m.group(1))),
            text)

        for index, html in enumerate(self._tokens):
            text = text.replace("\x00%d\x00" % index, html)
        return text

    def _image(self, matched: "re.Match[str]") -> str:
        path, spec = matched.group(1), matched.group(2)
        alt, width, height = _image_attrs(spec)
        attrs = ' src="%s" alt="%s"' % (escape(path), escape(alt))
        if width:
            attrs += ' width="%s"' % escape(width)
        if height:
            attrs += ' height="%s"' % escape(height)
        return self._protect("<img%s/>" % attrs)

    def _link(self, matched: "re.Match[str]") -> str:
        href, label = matched.group(1), matched.group(2)
        label = label or href
        return self._protect('<a href="%s">%s</a>' % (href, label))


# ---------------------------------------------------------------------------
# 块级渲染


class _BlockRenderer:
    def __init__(self) -> None:
        self.inline = _InlineRenderer()

    def render(self, lines: Sequence[str]) -> str:
        out: List[str] = []
        attrs: Dict[str, str] = {}
        pos = 0
        total = len(lines)

        while pos < total:
            line = lines[pos]
            if not line.strip():
                pos += 1
                continue
            stripped = line.lstrip()

            # 行注释 / 块注释
            if COMMENT_BLOCK_RE.match(line):
                pos += 1
                while pos < total and not COMMENT_BLOCK_RE.match(lines[pos]):
                    pos += 1
                pos += 1
                continue
            if stripped.startswith("//") and not stripped.startswith("///"):
                pos += 1
                continue
            if re.match(r"^(?:include|ifdef|ifndef|ifeval|endif|toc|index)::",
                        stripped):
                pos += 1                  # 不支持 include / 条件指令，直接跳过
                continue

            # 块属性
            matched = BLOCK_ATTR_RE.match(line)
            if matched:
                attrs = self._parse_block_attrs(matched.group(1))
                pos += 1
                continue

            # 表格 / 分隔块 / 图片 / 分隔线
            if TABLE_DELIM_RE.match(line):
                pos = self._table(lines, pos, out)
                attrs = {}
                continue

            matched = DELIM_RE.match(line)
            if matched:
                pos = self._delimited(lines, pos, matched.group(1), out, attrs)
                attrs = {}
                continue

            matched = IMAGE_BLOCK_RE.match(line)
            if matched:
                out.append(self._block_image(matched.group(1), matched.group(2)))
                pos += 1
                attrs = {}
                continue

            if RULER_RE.match(line):
                out.append("<hr/>")
                pos += 1
                attrs = {}
                continue

            # 块标题
            matched = BLOCK_TITLE_RE.match(line)
            if matched:
                out.append('<p class="block-title"><strong>%s</strong></p>'
                           % self.inline.render(matched.group(1)))
                pos += 1
                attrs = {}
                continue

            # 列表
            if LIST_RE.match(line):
                rendered, pos = self._list(lines, pos)
                out.append(rendered)
                attrs = {}
                continue

            # 定义列表
            if DEFINITION_RE.match(line):
                rendered, pos = self._definition_list(lines, pos)
                out.append(rendered)
                attrs = {}
                continue

            # 缩进 literal
            if line[:1] in (" ", "\t"):
                rendered, pos = self._literal(lines, pos)
                out.append(rendered)
                attrs = {}
                continue

            # 普通段落
            rendered, pos = self._paragraph(lines, pos)
            role = attrs.get("role", "")
            if role == "quote":
                inner = "<p>%s</p>" % rendered
                attribution = attrs.get("attribution", "")
                if attribution:
                    inner += ('<p class="attribution">——%s</p>'
                              % self.inline.render(attribution))
                out.append("<blockquote>%s</blockquote>" % inner)
            else:
                css = (' class="%s"' % role
                       if re.fullmatch(r"[A-Za-z0-9_-]+", role) else "")
                out.append("<p%s>%s</p>" % (css, rendered))
            attrs = {}

        return "\n".join(out)

    # -- 各块 ------------------------------------------------------------

    def _parse_block_attrs(self, text: str) -> Dict[str, str]:
        attrs: Dict[str, str] = {}
        parts = [part.strip() for part in text.split(",")]
        if not parts:
            return attrs
        first = parts[0]
        if first and "=" not in first:
            attrs["role"] = first
            parts = parts[1:]
            if first.lower() in ("source", "listing") and parts:
                attrs["language"] = parts[0].strip().strip("\"'")
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                attrs[key.strip().lower()] = value.strip().strip("\"'")
        for part in parts:
            if part and "=" not in part:      # [quote, 作者, 出处]
                attrs.setdefault("attribution", part.strip().strip("\"'"))
        if text.startswith("quote"):
            values = [part.strip().strip("\"'") for part in text.split(",")[1:]]
            if values:
                attrs["attribution"] = values[0]
        return attrs

    def _paragraph(self, lines: Sequence[str], pos: int) -> Tuple[str, int]:
        parts: List[str] = []
        total = len(lines)
        while pos < total:
            line = lines[pos]
            if not line.strip() or self._is_block_start(line):
                break
            hard_break = line.rstrip().endswith(" +")
            line = line.rstrip()
            if hard_break:
                line = line[:-1].rstrip() + " +"
            parts.append(line)
            pos += 1

        text = ""
        for line in parts:
            # 只去掉半角缩进，全角空格保留给 --keep-indent / CSS 处理
            line = line.strip(" \t")
            hard_break = line.endswith(" +")
            if hard_break:
                line = line[:-2].rstrip()
            if not text:
                text = line
            elif _needs_space(text, line):
                text += " " + line
            else:
                text += line
            if hard_break:
                text += "\x01"              # 渲染完再换成 <br/>
        return (self.inline.render(text).replace("\x01", "<br/>"), pos)

    def _list(self, lines: Sequence[str], pos: int) -> Tuple[str, int]:
        items: List[Tuple[int, bool, str]] = []
        total = len(lines)
        while pos < total:
            matched = LIST_RE.match(lines[pos])
            if not matched:
                break
            depth = len(matched.group(2))
            ordered = matched.group(2)[0] == "."
            text = matched.group(3).strip()
            pos += 1
            # 缩进续行并入当前条目
            while (pos < total and lines[pos].strip()
                   and not LIST_RE.match(lines[pos])
                   and lines[pos][:1] in (" ", "\t")):
                text += " " + lines[pos].strip()
                pos += 1
            items.append((depth, ordered, text))
        return self._nested_list(items), pos

    def _nested_list(self, items: Sequence[Tuple[int, bool, str]]) -> str:
        out: List[str] = []
        stack: List[Tuple[int, str]] = []
        for depth, ordered, text in items:
            tag = "ol" if ordered else "ul"
            while stack and depth < stack[-1][0]:
                out.append("</li></%s>" % stack[-1][1])
                stack.pop()
            if not stack or depth > stack[-1][0]:
                out.append("<%s>" % tag)
                stack.append((depth, tag))
            elif stack[-1][1] != tag:
                out.append("</li></%s>" % stack[-1][1])
                stack.pop()
                out.append("<%s>" % tag)
                stack.append((depth, tag))
            else:
                out.append("</li>")
            out.append("<li>%s" % self.inline.render(text))
        while stack:
            out.append("</li></%s>" % stack[-1][1])
            stack.pop()
        return "".join(out)

    def _definition_list(self, lines: Sequence[str], pos: int) -> Tuple[str, int]:
        out = ["<dl>"]
        total = len(lines)
        while pos < total:
            matched = DEFINITION_RE.match(lines[pos])
            if not matched:
                break
            out.append("<dt>%s</dt>" % self.inline.render(matched.group(1).strip()))
            out.append("<dd>%s</dd>" % self.inline.render(matched.group(2).strip()))
            pos += 1
        out.append("</dl>")
        return "".join(out), pos

    def _literal(self, lines: Sequence[str], pos: int) -> Tuple[str, int]:
        block: List[str] = []
        total = len(lines)
        while pos < total and (not lines[pos].strip() or lines[pos][:1] in (" ", "\t")):
            block.append(lines[pos])
            pos += 1
        while block and not block[-1].strip():
            block.pop()
        # 去掉公共缩进
        indents = [len(line) - len(line.lstrip()) for line in block if line.strip()]
        cut = min(indents) if indents else 0
        block = [line[cut:] if line.strip() else "" for line in block]
        return "<pre>%s</pre>" % escape("\n".join(block)), pos

    def _table(self, lines: Sequence[str], pos: int,
               out: List[str]) -> int:
        pos += 1
        rows: List[List[str]] = []
        total = len(lines)
        while pos < total and not TABLE_DELIM_RE.match(lines[pos]):
            line = lines[pos].strip()
            if line.startswith("|"):
                cells = [cell.strip() for cell in line.split("|")[1:]]
                if cells and cells[-1] == "":
                    cells.pop()
                if cells:
                    rows.append(cells)
            pos += 1
        pos += 1

        if not rows:
            return pos
        parts = ["<table><tbody>"]
        for row in rows:
            parts.append("<tr>")
            for cell in row:
                parts.append("<td>%s</td>" % self.inline.render(cell))
            parts.append("</tr>")
        parts.append("</tbody></table>")
        out.append("".join(parts))
        return pos

    def _delimited(self, lines: Sequence[str], pos: int, char: str,
                   out: List[str], attrs: Dict[str, str]) -> int:
        pos += 1
        block: List[str] = []
        total = len(lines)
        closing = re.compile(r"^%s{4,}\s*$" % re.escape(char))
        while pos < total and not closing.match(lines[pos]):
            block.append(lines[pos])
            pos += 1
        pos += 1

        if char in ("-", "."):
            language = attrs.get("language", "")
            if re.fullmatch(r"[A-Za-z0-9_+-]+", language):
                out.append('<pre><code class="language-%s">%s</code></pre>'
                           % (language, escape("\n".join(block))))
            else:
                out.append("<pre>%s</pre>" % escape("\n".join(block)))
        elif char == "_":
            inner = _BlockRenderer().render(block)
            attribution = attrs.get("attribution", "")
            if attribution:
                inner += '<p class="attribution">——%s</p>' % self.inline.render(attribution)
            out.append("<blockquote>%s</blockquote>" % inner)
        elif char == "+":
            out.append("\n".join(block))       # passthrough
        else:
            cls = "sidebar" if char == "*" else "example"
            out.append('<div class="%s">%s</div>'
                       % (cls, _BlockRenderer().render(block)))
        return pos

    def _block_image(self, path: str, spec: str) -> str:
        alt, width, height = _image_attrs(spec)
        attrs = ' src="%s" alt="%s"' % (escape(path), escape(alt))
        if width:
            attrs += ' width="%s"' % escape(width)
        if height:
            attrs += ' height="%s"' % escape(height)
        return '<p class="image"><img%s/></p>' % attrs

    def _is_block_start(self, line: str) -> bool:
        return bool(
            COMMENT_BLOCK_RE.match(line)
            or TABLE_DELIM_RE.match(line)
            or DELIM_RE.match(line)
            or IMAGE_BLOCK_RE.match(line)
            or RULER_RE.match(line)
            or BLOCK_TITLE_RE.match(line)
            or LIST_RE.match(line)
            or DEFINITION_RE.match(line)
            or BLOCK_ATTR_RE.match(line)
            or SECTION_RE.match(line)
        )


def _needs_space(left: str, right: str) -> bool:
    """中文换行不补空格，西文单词之间补一个。"""
    if not left or not right:
        return False
    return left[-1].isascii() and left[-1].isalnum() \
        and right[0].isascii() and right[0].isalnum()


# ---------------------------------------------------------------------------
# 插件


class AsciiDocInput(InputFormat):
    name = "asciidoc"
    extensions = ("asciidoc", "adoc", "asc")

    def metadata(self, source: SourceFile) -> BookMeta:
        attrs, _ = split_document(source.text)
        return _meta_from_attrs(attrs)

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        attrs, sections = split_document(source.text)
        has_sections = any(section.level > 0 for section in sections)
        chapters: List[Chapter] = []
        max_level = 0

        for section in sections:
            body = _BlockRenderer().render(section.lines)
            title = section.title
            level = section.level

            if level == 0:
                if not body.strip():
                    continue
                title = "前言" if has_sections else "正文"
                level = 1
            else:
                level = min(level, max_level + 1)
                max_level = max(max_level, level)

            heading = ""
            if title:
                heading = '<h1 class="chapter-title">%s</h1>' % escape(title)
            html = heading + ("\n" + body if body else "")
            if not options.keep_indent:
                html = strip_paragraph_indent(html)
            html = rewrite_images(html, source.base_dir, images,
                                  href_prefix="../")
            chapters.append(Chapter(title=title, html=html, level=level))

        if not chapters:
            title = attrs.get("title", "") or "正文"
            chapters.append(Chapter(
                title=title,
                html='<h1 class="chapter-title">%s</h1>' % escape(title),
                level=1))
        return chapters


__all__ = ["AsciiDocInput", "split_document", "Section"]
