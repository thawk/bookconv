"""EPUB 输入插件。

直接用 ebooklib 读 EPUB，再把每个章节文档交给 HTML 清洗器（``htmlbook``），
所以 EPUB 里的插图、表格、标题层级都能沿用 HTML/CHM 的处理逻辑。

目录优先用 EPUB 的 NCX/NAV 目录；没有目录时按 spine 顺序。EPUB 自带的 CSS
不会保留（cvbook 统一用自己的样式），封面会通过 ``cover()`` 交给 CLI。
"""

from __future__ import annotations

import os
import posixpath
import sys
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote

import ebooklib
from ebooklib import epub

from ..htmlutil import escape
from ..images import (MEDIA_TYPES, EpubImage, ImageStore, convert_image,
                      sniff_image_ext)
from ..models import BookMeta, Chapter
from . import htmlbook
from .base import InputError, InputFormat, ParseOptions, SourceFile

#: 这些页面是 EPUB 的结构页，不当正文
FRONT_NAMES = {"nav", "toc", "contents", "cover", "titlepage", "title-page"}


def _normalize_name(name: str) -> str:
    name = unquote(name.split("#", 1)[0]).replace("\\", "/")
    name = name.split("?", 1)[0].lstrip("/")
    if not name:
        return ""
    return posixpath.normpath(name)


class _EpubLoader(htmlbook.Loader):
    """把 EPUB 里的 item 当成一个只读目录交给 htmlbook。"""

    def __init__(self, book: epub.EpubBook) -> None:
        self.book = book
        self._items: Dict[str, object] = {}
        self._by_basename: Dict[str, object] = {}
        for item in book.get_items():
            name = _normalize_name(item.get_name())
            if not name:
                continue
            self._items[name.lower()] = item
            base = posixpath.basename(name).lower()
            if base in self._by_basename:
                self._by_basename[base] = None     # 同名文件不猜
            else:
                self._by_basename[base] = item

    def item(self, href: str):
        name = _normalize_name(href)
        if not name:
            return None
        item = self._items.get(name.lower())
        if item is not None:
            return item
        # 有些 EPUB 的 TOC href 和 item name 层级不一致，唯一同名时兜底
        return self._by_basename.get(posixpath.basename(name).lower())

    def read_bytes(self, href: str) -> Optional[bytes]:
        item = self.item(href)
        if item is None:
            return None
        try:
            return item.get_content()
        except Exception:
            return None

    def read_text(self, href: str) -> Optional[str]:
        data = self.read_bytes(href)
        return htmlbook.decode_html(data) if data is not None else None

    def exists(self, href: str) -> bool:
        return self.item(href) is not None

    def files(self) -> List[str]:
        return sorted(item.get_name() for item in self._items.values())

    def resolve(self, from_href: str, target: str) -> str:
        absolute = target.startswith("/")
        target = _normalize_name(target)
        if not target:
            return ""
        if absolute:
            return target
        base = posixpath.dirname(_normalize_name(from_href))
        resolved = posixpath.normpath(posixpath.join(base, target))
        if self.exists(resolved):
            return resolved
        if self.exists(target):             # 有些 EPUB 的图片按根目录写
            return target
        return resolved

    def key(self, href: str) -> str:
        return _normalize_name(href).lower()


def _item_title(item) -> str:
    title = htmlbook.clean_title(getattr(item, "title", "") or "")
    if title:
        return title
    try:
        text = htmlbook.decode_html(item.get_content())
    except Exception:
        return os.path.splitext(posixpath.basename(item.get_name()))[0]
    return (htmlbook.page_title(text)
            or os.path.splitext(posixpath.basename(item.get_name()))[0])


def _is_front_item(item) -> bool:
    if getattr(item, "get_type", lambda: None)() != ebooklib.ITEM_DOCUMENT:
        return True
    name = posixpath.basename(item.get_name()).lower()
    stem = os.path.splitext(name)[0]
    if stem in FRONT_NAMES:
        return True
    if "nav" in (getattr(item, "properties", None) or []):
        return True
    return False


def _toc_entries(book: epub.EpubBook,
                 loader: _EpubLoader) -> List[Tuple[str, Optional[str], int]]:
    raw: List[Tuple[str, Optional[str], int]] = []

    def walk(items, level: int) -> None:
        for item in items or []:
            if isinstance(item, epub.Link):
                raw.append((getattr(item, "title", "") or "",
                            getattr(item, "href", "") or "", level))
            elif isinstance(item, tuple):
                section, children = item
                title = getattr(section, "title", "") or ""
                href = getattr(section, "href", "") or ""
                if href:
                    raw.append((title, href, level))
                elif title:
                    raw.append((title, None, level))
                walk(children, level + 1)

    toc = book.toc
    if isinstance(toc, (epub.Link, epub.Section)):
        toc = [toc]
    walk(toc or [], 1)

    entries: List[Tuple[str, Optional[str], int]] = []
    seen: Set[str] = set()
    for title, href, level in raw:
        title = htmlbook.clean_title(title)
        if not href:
            if title and title.lower() not in FRONT_NAMES:
                entries.append((title, None, level))
            continue
        key = loader.key(href)
        if not key or key in seen:
            continue
        item = loader.item(href)
        if item is None or _is_front_item(item):
            continue
        if not title:
            title = _item_title(item)
        seen.add(key)
        entries.append((title or _item_title(item), href, level))

    # TOC 漏掉的 spine 文档补在最后，避免丢正文
    for spine_item in book.spine or []:
        if isinstance(spine_item, tuple):
            idref = spine_item[0]
        else:
            idref = spine_item
        item = book.get_item_with_id(idref)
        if item is None or _is_front_item(item):
            continue
        key = loader.key(item.get_name())
        if not key or key in seen:
            continue
        seen.add(key)
        entries.append((_item_title(item), item.get_name(), 1))

    if not any(href for _title, href, _level in entries):
        # 连 spine 都没有的坏 EPUB，最后按文档顺序收一遍
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            if _is_front_item(item):
                continue
            key = loader.key(item.get_name())
            if not key or key in seen:
                continue
            seen.add(key)
            entries.append((_item_title(item), item.get_name(), 1))

    return entries


def _find_cover_item(book: epub.EpubBook):
    images = [item for item in book.get_items()
              if item.get_type() in (ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER)
              and item.get_content()]
    if not images:
        return None

    # EPUB3: properties="cover-image"
    for item in images:
        if "cover-image" in (getattr(item, "properties", None) or []):
            return item

    # EPUB2: <meta name="cover" content="...">
    for _value, others in book.get_metadata("OPF", "meta"):
        if (isinstance(others, dict)
                and str(others.get("name", "")).lower() == "cover"):
            cover_id = others.get("content")
            if cover_id:
                for item in images:
                    if item.get_id() == cover_id:
                        return item

    # guide 里的 cover 页，取页面第一张图
    loader = _EpubLoader(book)
    for ref in getattr(book, "guide", None) or []:
        if str(ref.get("type", "")).lower() != "cover":
            continue
        href = ref.get("href") or ""
        doc = loader.item(href)
        if doc is None:
            continue
        text = loader.read_text(href)
        tree = htmlbook.parse_html(text or "")
        if tree is None:
            continue
        image = tree.find(".//img")
        src = image.get("src") if image is not None else None
        if not src:
            continue
        target = loader.resolve(href, src)
        item = loader.item(target)
        if item is not None and item.get_type() in (ebooklib.ITEM_IMAGE,
                                                    ebooklib.ITEM_COVER):
            return item

    # 最后的回退：文件名里带 cover 的图片
    for item in images:
        if "cover" in item.get_name().lower():
            return item
    return None


def _cover_image(item) -> Optional[EpubImage]:
    try:
        data = item.get_content()
    except Exception:
        return None
    if not data:
        return None
    name = posixpath.basename(item.get_name())
    ext = os.path.splitext(name)[1].lstrip(".").lower()
    if ext not in MEDIA_TYPES:
        sniffed = sniff_image_ext(data)
        if sniffed is None:
            return None
        ext = sniffed
    if ext == "webp":
        converted = convert_image(data, name, "png")
        if converted is not None:
            data, ext = converted, "png"
    return EpubImage(path="images/cover." + ext,
                     media_type=MEDIA_TYPES[ext], data=data)


class EpubInput(InputFormat):
    name = "epub"
    extensions = ("epub",)

    def __init__(self) -> None:
        self._books: Dict[str, epub.EpubBook] = {}

    def _book(self, source: SourceFile) -> epub.EpubBook:
        path = os.path.abspath(source.path)
        if path in self._books:
            return self._books[path]
        if not os.path.isfile(path):
            raise InputError("EPUB 文件不存在: %s" % path)
        try:
            book = epub.read_epub(path)
        except Exception as error:
            raise InputError("无法读取 EPUB '%s': %s" % (path, error))
        self._books[path] = book
        return book

    def metadata(self, source: SourceFile) -> BookMeta:
        book = self._book(source)
        meta = BookMeta()

        titles = book.get_metadata("DC", "title")
        if titles:
            title = htmlbook.clean_title(titles[0][0] or "")
            if title.lower() not in htmlbook.GENERIC_TITLES:
                meta.title = title

        authors: List[str] = []
        for value, _others in book.get_metadata("DC", "creator"):
            author = htmlbook.clean_title(value or "")
            if author and author not in authors:
                authors.append(author)
        meta.authors = authors

        descriptions = [value for value, _others
                        in book.get_metadata("DC", "description") if value]
        if descriptions:
            meta.comments = htmlbook.clean_title(descriptions[0])
        return meta

    def cover(self, source: SourceFile) -> Optional[EpubImage]:
        item = _find_cover_item(self._book(source))
        return _cover_image(item) if item is not None else None

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        book = self._book(source)
        loader = _EpubLoader(book)
        entries = _toc_entries(book, loader)
        if not entries:
            raise InputError("EPUB 里没有找到可解析的正文页面: %s" % source.path)

        chapters: List[Chapter] = []
        for title, href, level in entries:
            level = max(1, level)
            title = htmlbook.clean_title(title)
            if not href:
                if title:
                    chapters.append(Chapter(
                        title,
                        '<h1 class="chapter-title">%s</h1>' % escape(title),
                        level))
                continue

            text = loader.read_text(href)
            if text is None:
                print("!!! 读不到 EPUB 页面: %s" % href, file=sys.stderr)
                continue
            if not title:
                title = htmlbook.page_title(text)
            if not title:
                title = os.path.splitext(posixpath.basename(href))[0]
            body = htmlbook.render_page(text, href, loader, images, options,
                                        title=title)
            if not body.strip() and not title:
                continue
            heading = ('<h1 class="chapter-title">%s</h1>' % escape(title)
                       if title else "")
            chapters.append(Chapter(
                title=title or "正文",
                html=heading + ("\n" + body if body else ""),
                level=level))
        return chapters


__all__ = ["EpubInput"]
