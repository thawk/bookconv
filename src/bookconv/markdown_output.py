"""把 ``Chapter`` 列表写成单个 Markdown 文件。

用于 ``bookconv --format md``。章节正文已经是清洗过的 XHTML 片段，所以这里只做
三件事：去掉重复的章节标题、按目录层级调整小节标题、用 html2text 转成 Markdown。

输出约定：

* 文件头写 YAML frontmatter（title / author / description），可以被 bookconv 的
  Markdown 输入插件直接读回；
* 第 1 级章节用 ``#``，第 2 级用 ``##``，依此类推；
* 插图写到 ``<md 文件名>.images/``，Markdown 里的路径同步改写；
* EPUB/CHM 等输入自带的封面写到与 md 同名的图片文件（``书名.jpg``），
  这样再次用 bookconv 转回 EPUB 时能自动找到封面。
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional, Set

import html2text
from lxml import etree, html as lxml_html

from .htmlutil import escape
from .images import EpubImage, ImageStore, safe_name
from .models import BookMeta, Chapter

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
IMAGE_PATH_RE = re.compile(r"^(?:\.\./)*images/(.+)$", re.IGNORECASE)


def _local_tag(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _new_converter() -> html2text.HTML2Text:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_links = False
    converter.ignore_images = False
    converter.ignore_emphasis = False
    converter.protect_links = False
    converter.unicode_snob = True
    converter.single_line_break = False
    converter.use_automatic_links = False
    converter.mark_code = False
    converter.ul_item_mark = "-"
    return converter


def _inner_html(root) -> str:
    parts: List[str] = []
    if root.text:
        parts.append(escape(root.text))
    for child in root:
        parts.append(etree.tostring(child, encoding="unicode", method="xml",
                                    with_tail=False))
        if child.tail:
            parts.append(escape(child.tail))
    return "".join(parts)


def _title_key(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _strip_title_heading(root, title: str) -> None:
    if not title:
        return
    title_key = _title_key(title)
    if not title_key:
        return
    for child in list(root):
        tag = _local_tag(child.tag)
        if tag not in HEADING_TAGS:
            continue
        heading_key = _title_key(child.text_content())
        if not heading_key:
            continue
        if (heading_key == title_key or title_key in heading_key
                or heading_key in title_key):
            previous = child.getprevious()
            tail = child.tail or ""
            root.remove(child)
            if tail:
                if previous is not None:
                    previous.tail = (previous.tail or "") + tail
                else:
                    root.text = (root.text or "") + tail
            continue
        break


def _shift_headings(root, shift: int) -> None:
    if shift <= 0:
        return
    for element in root.iter():
        tag = _local_tag(element.tag)
        if tag in HEADING_TAGS:
            level = min(6, int(tag[1]) + shift)
            element.tag = "h%d" % level


def _rewrite_images(root, assets_name: str) -> None:
    for image in root.iter("img"):
        src = (image.get("src") or "").strip()
        matched = IMAGE_PATH_RE.match(src)
        if matched:
            name = matched.group(1).rsplit("/", 1)[-1]
            image.set("src", assets_name + "/" + name)


class _FootnoteState(object):
    """整篇 Markdown 共用，保证脚注标签不重复。"""

    def __init__(self) -> None:
        self.labels: Dict[str, str] = {}
        self.defined: Set[str] = set()
        self.used: Set[str] = set()
        self.counter = 0

    def label(self, target: str) -> str:
        if target in self.labels:
            return self.labels[target]
        self.counter += 1
        base = re.sub(r"[^0-9A-Za-z_.-]+", "-", target).strip("-")
        if not base:
            base = "note%d" % self.counter
        label = base
        index = 2
        while label.lower() in self.used:
            label = "%s-%d" % (base, index)
            index += 1
        self.used.add(label.lower())
        self.labels[target] = label
        return label


def _epub_types(element) -> List[str]:
    value = element.get("epub:type") or element.get("type") or ""
    return [part.lower() for part in value.split()]


def _class_tokens(element) -> List[str]:
    return (element.get("class") or "").lower().split()


def _is_noteref(element) -> bool:
    href = (element.get("href") or "").strip()
    if not href.startswith("#"):
        return False
    return ("noteref" in _epub_types(element)
            or any("footnote" in token for token in _class_tokens(element)))


def _is_footnote(element) -> bool:
    return ("footnote" in _epub_types(element)
            or "footnote" in _class_tokens(element))


def _remove_element(element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail or ""
    previous = element.getprevious()
    parent.remove(element)
    if tail:
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail


def _drop_footnote_backlinks(element) -> None:
    for anchor in list(element.iter("a")):
        href = (anchor.get("href") or "").strip()
        text = (anchor.text_content() or "").strip()
        if (href.startswith("#")
                and ("footnote-backref" in _class_tokens(anchor)
                     or text in ("⊙", "↩", "↵"))):
            _remove_element(anchor)


def _footnote_text(element, converter: html2text.HTML2Text) -> str:
    _drop_footnote_backlinks(element)
    for rule in list(element.iter("hr")):
        _remove_element(rule)
    text = converter.handle(_inner_html(element)).strip()
    return text.replace("\u00a0", " ").strip()


def _format_footnote(label: str, text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n")
             .replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    parts = ["[^%s]: %s" % (label, lines[0].strip())]
    for line in lines[1:]:
        parts.append("    " + line.strip() if line.strip() else "")
    return "\n".join(parts)


def _extract_footnotes(root, converter: html2text.HTML2Text,
                       state: _FootnoteState) -> List[str]:
    """把 EPUB/HTML 里的脚注块转成 Markdown 脚注定义。"""
    definitions: List[str] = []
    asides = [element for element in root.iter()
              if _local_tag(element.tag) == "aside" and _is_footnote(element)]
    for aside in asides:
        items = [child for child in aside.iter()
                 if _local_tag(child.tag) == "li"
                 and (child.get("id") or "").strip()]
        if not items:
            items = [aside]
        for item in items:
            target = (item.get("id") or aside.get("id") or "").strip()
            if not target:
                continue
            text = _footnote_text(item, converter)
            if not text:
                continue
            state.defined.add(target)
            definitions.append(_format_footnote(state.label(target), text))
        _remove_element(aside)

    for anchor in list(root.iter("a")):
        if not _is_noteref(anchor):
            continue
        href = (anchor.get("href") or "").strip()
        target = href[1:] if href.startswith("#") else ""
        if target not in state.defined:
            # 找不到对应的脚注体，就保留链接文字，避免写出悬空的 [^标签]
            continue
        label = state.label(target)
        replacement = etree.Element("span")
        replacement.text = "[^%s]" % label
        replacement.tail = anchor.tail
        parent = anchor.getparent()
        if parent is not None:
            parent.replace(anchor, replacement)
    return definitions


def _chapter_markdown(chapter: Chapter, assets_name: str,
                      converter: html2text.HTML2Text,
                      footnotes: _FootnoteState) -> str:
    if not chapter.html.strip():
        return ""
    try:
        root = lxml_html.fragment_fromstring(chapter.html, create_parent="div")
    except (etree.ParserError, ValueError):
        root = None

    if root is None:
        return ""
    _strip_title_heading(root, chapter.title)
    _shift_headings(root, chapter.level - 1)
    _rewrite_images(root, assets_name)
    definitions = _extract_footnotes(root, converter, footnotes)
    fragment = _inner_html(root)
    if not fragment.strip():
        return "\n\n".join(definitions)
    markdown = converter.handle(fragment).strip()
    # html2text 会在强调标记和中文标点之间插空格，去掉更自然
    markdown = re.sub(r"(\*\*|__|\*|_)[ \t]+([，。！？；：、）】」』])",
                      r"\1\2", markdown)
    if definitions:
        markdown = "\n\n".join([markdown] + definitions)
    return markdown


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(meta: BookMeta) -> str:
    lines = ["---"]
    if meta.title:
        lines.append("title: " + _yaml_string(meta.title))
    if meta.authors:
        lines.append("author:")
        lines.extend("  - " + _yaml_string(author) for author in meta.authors)
    if meta.comments:
        lines.append("description: |")
        for line in meta.comments.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            lines.append("  " + line if line else "")
    lines.append("---")
    return "\n".join(lines)


def _write_images(assets_dir: str, images: ImageStore) -> int:
    if not images.items:
        return 0
    os.makedirs(assets_dir, exist_ok=True)
    for image in images.items:
        name = os.path.basename(image.path)
        with open(os.path.join(assets_dir, name), "wb") as f:
            f.write(image.data)
    return len(images.items)


def _write_cover(out_path: str, cover: Optional[EpubImage]) -> Optional[str]:
    if cover is None:
        return None
    ext = os.path.splitext(cover.path)[1].lstrip(".").lower() or "jpg"
    cover_path = os.path.splitext(out_path)[0] + "." + ext
    with open(cover_path, "wb") as f:
        f.write(cover.data)
    return cover_path


def write_markdown(out_path: str, meta: BookMeta, chapters: List[Chapter],
                   images: ImageStore, cover: Optional[EpubImage] = None,
                   include_frontmatter: bool = True,
                   verbose: bool = False) -> str:
    """把章节写成 Markdown，返回输出文件名。"""
    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)

    stem = os.path.splitext(os.path.basename(out_path))[0] or "book"
    assets_name = safe_name(stem) + ".images"
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                              assets_name)

    converter = _new_converter()
    footnotes = _FootnoteState()
    parts: List[str] = []
    if include_frontmatter:
        parts.append(_frontmatter(meta))

    for chapter in chapters:
        title = (chapter.title or "正文").replace("\n", " ").strip()
        level = min(6, max(1, chapter.level))
        parts.append("#" * level + " " + title)
        body = _chapter_markdown(chapter, assets_name, converter, footnotes)
        if body:
            parts.append(body)

    text = "\n\n".join(parts).strip() + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    image_count = _write_images(assets_dir, images)
    cover_path = _write_cover(out_path, cover)

    if verbose:
        detail = "，%d 张插图" % image_count if image_count else ""
        print("Markdown: %s%s%s"
              % (out_path, detail,
                 "，封面: %s" % cover_path if cover_path else ""),
              file=sys.stderr)
    return out_path


__all__ = ["write_markdown"]
