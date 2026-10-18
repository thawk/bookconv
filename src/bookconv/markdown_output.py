"""把 ``Chapter`` 列表写成单个 Markdown 文件。

用于 ``bookconv --format md``。章节正文已经是清洗过的 XHTML 片段，所以这里只做
三件事：去掉重复的章节标题、按目录层级调整小节标题、用 html2text 转成 Markdown。

输出约定：

* 文件头写 YAML frontmatter（title / authors / comments），可以被 bookconv 的
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
from typing import List, Optional

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


def _strip_title_heading(root, title: str) -> None:
    if not title:
        return
    title = re.sub(r"\s+", " ", title).strip()
    for child in root:
        tag = _local_tag(child.tag)
        if tag not in HEADING_TAGS:
            continue
        heading = re.sub(r"\s+", " ", child.text_content()).strip()
        if not heading:
            continue
        if heading == title or title in heading or heading in title:
            previous = child.getprevious()
            tail = child.tail or ""
            root.remove(child)
            if tail:
                if previous is not None:
                    previous.tail = (previous.tail or "") + tail
                else:
                    root.text = (root.text or "") + tail
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


def _chapter_markdown(chapter: Chapter, assets_name: str,
                      converter: html2text.HTML2Text) -> str:
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
    fragment = _inner_html(root)
    if not fragment.strip():
        return ""
    markdown = converter.handle(fragment).strip()
    # html2text 会在强调标记和中文标点之间插空格，去掉更自然
    markdown = re.sub(r"(\*\*|__|\*|_)[ \t]+([，。！？；：、）】」』])",
                      r"\1\2", markdown)
    return markdown


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(meta: BookMeta) -> str:
    lines = ["---"]
    if meta.title:
        lines.append("title: " + _yaml_string(meta.title))
    if meta.authors:
        lines.append("authors:")
        lines.extend("  - " + _yaml_string(author) for author in meta.authors)
    if meta.comments:
        lines.append("comments: |")
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
    parts: List[str] = []
    if include_frontmatter:
        parts.append(_frontmatter(meta))

    for chapter in chapters:
        title = (chapter.title or "正文").replace("\n", " ").strip()
        level = min(6, max(1, chapter.level))
        parts.append("#" * level + " " + title)
        body = _chapter_markdown(chapter, assets_name, converter)
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
