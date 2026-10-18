"""用 ebooklib 组装 EPUB：封面页 / 扉页 / 目录页 / 简介页 / 正文页。"""

from __future__ import annotations

import html as html_lib
import posixpath
import re
import uuid
from typing import List, Optional, Sequence, Tuple

from ebooklib import epub

from .images import EpubImage
from .models import BookMeta, Chapter

#: 章节 XHTML 文件所在目录（样式链接要按层级算相对路径）
CHAPTER_DIR = "text"
STYLE_PATH = "css/style.css"
NAV_PATH = "nav.xhtml"


def _css_href(file_name: str) -> str:
    return posixpath.relpath(STYLE_PATH, posixpath.dirname(file_name) or ".")


def _escape(text: str) -> str:
    return html_lib.escape(text, quote=True)


class _TocNode(object):
    __slots__ = ("item", "level", "children")

    def __init__(self, item: object, level: int) -> None:
        self.item = item
        self.level = level
        self.children: List["_TocNode"] = []


def build_toc(entries: Sequence[Tuple[object, int]]) -> tuple:
    """把 (页面, 层级) 列表转成 ebooklib 需要的嵌套目录结构。"""
    roots: List[_TocNode] = []
    stack: List[_TocNode] = []

    for item, level in entries:
        node = _TocNode(item, max(1, level))
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def convert(nodes: Sequence[_TocNode]) -> tuple:
        result = []
        for node in nodes:
            if node.children:
                result.append((node.item, convert(node.children)))
            elif isinstance(node.item, epub.Section):
                result.append((node.item, ()))
            else:
                result.append(node.item)
        return tuple(result)

    return convert(roots)


FIRST_CLASS_RE = re.compile(r'^(<div class="page [^"]*)(")')


def _mark_first(item: epub.EpubHtml) -> None:
    item.content = FIRST_CLASS_RE.sub(r"\1 first\2", item.content, count=1)


def book_identifier(meta: BookMeta) -> str:
    """用书名+作者生成稳定的 uuid，重复转换时 id 不变。"""
    seed = "bookconv:%s|%s" % (meta.title, meta.author_text)
    return "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, seed)


def build_epub(out_path: str, meta: BookMeta, chapters: Sequence[Chapter], *,
               css: str, images: Sequence[EpubImage] = (),
               cover: Optional[EpubImage] = None, lang: str = "zh",
               include_titlepage: bool = True, include_intro: bool = True,
               intro_title: str = "简介", intro_html: str = "",
               verbose: bool = False) -> str:
    book = epub.EpubBook()
    book.set_identifier(book_identifier(meta))
    book.set_title(meta.title)
    book.set_language(lang)
    for author in meta.authors:
        book.add_author(author)
    if meta.comments:
        book.add_metadata("DC", "description", meta.comments)

    book.add_item(epub.EpubItem(uid="style", file_name=STYLE_PATH,
                                media_type="text/css",
                                content=css.encode("utf-8")))

    if cover is not None:
        # 只登记封面图（EPUB3 的 properties="cover-image" + EPUB2 的 meta cover），
        # 封面页由我们自己生成，这样才能完全用 CSS 控制
        book.set_cover(cover.path, cover.data, create_page=False)

    for index, image in enumerate(images, 1):
        if cover is not None and image.path == cover.path:
            continue                    # 正文里引用了封面图，避免重复写入
        book.add_item(epub.EpubItem(uid="image-%04d" % index,
                                    file_name=image.path,
                                    media_type=image.media_type,
                                    content=image.data))

    front: List[epub.EpubHtml] = []
    chapter_items: List[epub.EpubHtml] = []
    toc_entries: List[Tuple[object, int]] = []

    def add_page(kind: str, uid: str, file_name: str, title: str,
                 inner: str, semantics: str = "") -> epub.EpubHtml:
        item = epub.EpubHtml(uid=uid, file_name=file_name, title=title,
                             lang=lang)
        attrs = 'class="page %s"' % kind
        if semantics:
            attrs += ' epub:type="%s"' % semantics
        item.content = '<div %s>%s</div>' % (attrs, inner)
        item.add_link(href=_css_href(file_name), rel="stylesheet",
                      type="text/css")
        book.add_item(item)
        return item

    if cover is not None:
        front.append(add_page("cover", "cover", "cover.xhtml", "封面",
                              '<img class="cover-image" src="%s" alt="封面"/>'
                              % _escape(cover.path), semantics="cover"))

    if include_titlepage:
        front.append(add_page(
            "titlepage", "titlepage", "titlepage.xhtml", meta.title,
            '<div class="titlepage-inner">'
            '<h1 class="book-title">%s</h1><p class="book-author">%s</p>'
            "</div>"
            % (_escape(meta.title), _escape(meta.author_text)),
            semantics="titlepage"))

    if include_intro and intro_html:
        front.append(add_page(
            "intro", "intro", "intro.xhtml", intro_title,
            '<h2 class="intro-title">%s</h2>%s'
            % (_escape(intro_title), intro_html), semantics="preface"))

    page_index = 0
    for chapter in chapters:
        if chapter.virtual:
            # 只在目录里占分组，不生成正文页
            toc_entries.append((epub.Section(chapter.title), chapter.level))
            continue
        page_index += 1
        item = add_page("chapter", "chap-%04d" % page_index,
                        "%s/chapter-%04d.xhtml" % (CHAPTER_DIR, page_index),
                        chapter.title, chapter.html)
        chapter_items.append(item)
        toc_entries.append((item, chapter.level))

    # 第一页不分页
    first_pages = front + chapter_items
    if first_pages:
        _mark_first(first_pages[0])

    book.toc = build_toc(toc_entries)

    nav = epub.EpubNav(title="目录")
    nav.add_link(href="css/style.css", rel="stylesheet", type="text/css")
    book.add_item(nav)
    book.add_item(epub.EpubNcx())

    # 目录只做导航文档（reader 的目录跳转用），不排进正文；
    # 另外不生成 landmarks 那个多余的 nav
    book.spine = front + chapter_items

    book.guide = []
    if cover is not None:
        book.guide.append({"type": "cover", "href": "cover.xhtml",
                           "title": "封面"})
    if include_titlepage:
        # 告诉阅读器“扉页在哪”，有些阅读器找不到时会自己生成一页
        book.guide.append({"type": "title-page", "href": "titlepage.xhtml",
                           "title": meta.title})
    book.guide.append({"type": "toc", "href": NAV_PATH, "title": "目录"})

    if verbose:
        print("EPUB: %d 页, %d 张插图, 封面: %s"
              % (len(chapter_items), len(images), cover.path if cover else "无"))

    epub.write_epub(out_path, book, {"raise_exceptions": True,
                                     "epub3_landmark": False})
    return out_path
