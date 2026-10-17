"""用标准库写 EPUB 3（同时带 NCX，兼容老阅读器）。

目录结构::

    mimetype
    META-INF/container.xml
    EPUB/content.opf
    EPUB/nav.xhtml          目录页（epub:type="toc"）
    EPUB/toc.ncx            给 EPUB 2 阅读器
    EPUB/css/style.css
    EPUB/cover.xhtml
    EPUB/titlepage.xhtml
    EPUB/intro.xhtml
    EPUB/text/chapter-0001.xhtml ...
    EPUB/images/...
"""

from __future__ import annotations

import html as html_lib
import posixpath
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

from .images import EpubImage
from .models import BookMeta, Chapter

FOLDER = "EPUB"
CHAPTER_DIR = "text"
STYLE_PATH = "css/style.css"
NAV_PATH = "nav.xhtml"
NCX_PATH = "toc.ncx"
OPF_PATH = "content.opf"

PAGE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
  <head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="{css}"/>
  </head>
  <body>
{body}
  </body>
</html>
"""

CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class Page:
    """EPUB 里的一个 XHTML 页面。"""

    id: str
    href: str                 #: 相对 EPUB 根目录，如 text/chapter-0001.xhtml
    title: str
    body: str                 #: 页面内 XHTML
    level: int = 1            #: 目录层级


@dataclass
class _TocNode:
    page: Page
    level: int
    children: List["_TocNode"] = field(default_factory=list)


def _attr(text: str) -> str:
    return html_lib.escape(text, quote=True)


def _css_href(href: str) -> str:
    return posixpath.relpath(STYLE_PATH, posixpath.dirname(href) or ".")


def book_identifier(meta: BookMeta) -> str:
    """用书名+作者生成稳定的 uuid，重复转换时 id 不变。"""
    seed = "cvbook:%s|%s" % (meta.title, meta.author_text)
    return "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, seed)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _page_document(page: Page, lang: str) -> str:
    return PAGE_TEMPLATE.format(lang=lang, title=xml_escape(page.title),
                                css=_css_href(page.href), body=page.body)


def _toc_tree(entries: Sequence[Tuple[Page, int]]) -> List[_TocNode]:
    roots: List[_TocNode] = []
    stack: List[_TocNode] = []
    for page, level in entries:
        node = _TocNode(page, max(1, level))
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _nav_list(nodes: Sequence[_TocNode]) -> str:
    items = []
    for node in nodes:
        item = ('<li><a href="%s">%s</a>'
                % (_attr(node.page.href), xml_escape(node.page.title)))
        if node.children:
            item += _nav_list(node.children)
        item += "</li>"
        items.append(item)
    return "<ol>%s</ol>" % "".join(items)


def _ncx_points(nodes: Sequence[_TocNode]) -> str:
    points = []
    for node in nodes:
        points.append(
            '<navPoint id="%s"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/>%s</navPoint>'
            % (_attr(node.page.id), xml_escape(node.page.title),
               _attr(node.page.href), _ncx_points(node.children)))
    return "".join(points)


def _nav_body(entries: Sequence[Tuple[Page, int]], first: bool) -> str:
    """目录页：既是 EPUB 的导航文档，也是书里的“目录”页。"""
    return ('    <div class="page toc%s">\n'
            '      <nav epub:type="toc" id="toc">\n'
            "        <h1>目录</h1>\n        %s\n"
            "      </nav>\n    </div>"
            % (" first" if first else "", _nav_list(_toc_tree(entries))))


def _ncx_document(meta: BookMeta, entries: Sequence[Tuple[Page, int]],
                  lang: str) -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{lang}">
  <head>
    <meta name="dtb:uid" content="{uid}"/>
    <meta name="dtb:depth" content="3"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>{points}</navMap>
</ncx>
""".format(lang=lang, uid=_attr(book_identifier(meta)),
           title=xml_escape(meta.title),
           points=_ncx_points(_toc_tree(entries)))


def _opf_document(meta: BookMeta, lang: str, pages: Sequence[Page],
                  cover: Optional[EpubImage],
                  images: Sequence[EpubImage]) -> str:
    metadata = [
        '<dc:identifier id="bookid">%s</dc:identifier>' % xml_escape(book_identifier(meta)),
        "<dc:title>%s</dc:title>" % xml_escape(meta.title),
        "<dc:language>%s</dc:language>" % xml_escape(lang),
    ]
    for index, author in enumerate(meta.authors, 1):
        metadata.append('<dc:creator id="creator%d">%s</dc:creator>'
                        % (index, xml_escape(author)))
        metadata.append('<meta refines="#creator%d" property="role" '
                        'scheme="marc:relators">aut</meta>' % index)
    if meta.comments:
        metadata.append("<dc:description>%s</dc:description>"
                        % xml_escape(meta.comments))
    metadata.append('<meta property="dcterms:modified">%s</meta>' % _now())
    if cover is not None:
        metadata.append('<meta name="cover" content="cover-image"/>')

    manifest = [
        '<item id="nav" href="%s" media-type="application/xhtml+xml" properties="nav"/>' % NAV_PATH,
        '<item id="ncx" href="%s" media-type="application/x-dtbncx+xml"/>' % NCX_PATH,
        '<item id="style" href="%s" media-type="text/css"/>' % STYLE_PATH,
    ]
    if cover is not None:
        manifest.append('<item id="cover-image" href="%s" media-type="%s" '
                        'properties="cover-image"/>' % (_attr(cover.path), cover.media_type))
    for index, image in enumerate(images, 1):
        manifest.append('<item id="image-%04d" href="%s" media-type="%s"/>'
                        % (index, _attr(image.path), image.media_type))
    for page in pages:
        if page.id == "nav":             # 导航文档单独登记
            continue
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>'
                        % (_attr(page.id), _attr(page.href)))

    spine = "".join('<itemref idref="%s"/>' % _attr(page.id) for page in pages)

    guide = ["<guide>"]
    if cover is not None:
        guide.append('<reference type="cover" title="封面" href="cover.xhtml"/>')
    guide.append('<reference type="toc" title="目录" href="%s"/>' % NAV_PATH)
    guide.append("</guide>")

    return """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    {metadata}
  </metadata>
  <manifest>
    {manifest}
  </manifest>
  <spine toc="ncx">{spine}</spine>
  {guide}
</package>
""".format(lang=lang, metadata="\n    ".join(metadata),
           manifest="\n    ".join(manifest), spine=spine,
           guide="\n  ".join(guide))


def build_epub(out_path: str, meta: BookMeta, chapters: Sequence[Chapter], *,
               css: str, images: Sequence[EpubImage] = (),
               cover: Optional[EpubImage] = None, lang: str = "zh",
               include_titlepage: bool = True, include_intro: bool = True,
               intro_title: str = "简介", intro_html: str = "",
               verbose: bool = False) -> str:
    pages: List[Page] = []
    toc_entries: List[Tuple[Page, int]] = []

    def add_page(kind: str, uid: str, href: str, title: str, inner: str,
                 level: int = 1) -> Page:
        classes = "page " + kind + (" first" if not pages else "")
        page = Page(uid, href, title,
                    '    <div class="%s">%s</div>' % (classes, inner), level)
        pages.append(page)
        return page

    if cover is not None:
        add_page("cover", "cover", "cover.xhtml", "封面",
                 '<img class="cover-image" src="%s" alt="封面"/>'
                 % _attr(cover.path))

    if include_titlepage:
        add_page("titlepage", "titlepage", "titlepage.xhtml", meta.title,
                 '<h1 class="book-title">%s</h1><p class="book-author">%s</p>'
                 % (xml_escape(meta.title), xml_escape(meta.author_text)))

    if include_intro and intro_html:
        add_page("intro", "intro", "intro.xhtml", intro_title,
                 '<h2 class="intro-title">%s</h2>%s'
                 % (xml_escape(intro_title), intro_html))

    front_count = len(pages)

    for index, chapter in enumerate(chapters, 1):
        page = add_page("chapter", "chap-%04d" % index,
                        "%s/chapter-%04d.xhtml" % (CHAPTER_DIR, index),
                        chapter.title, chapter.html, chapter.level)
        toc_entries.append((page, chapter.level))

    # 目录页放在扉页/简介之后、正文之前
    nav_page = Page("nav", NAV_PATH, "目录",
                    _nav_body(toc_entries, first=not pages))
    pages.insert(front_count, nav_page)

    if verbose:
        print("EPUB: %d 页, %d 张插图, 封面: %s"
              % (len(chapters), len(images), cover.path if cover else "无"))

    with zipfile.ZipFile(out_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip",
                         compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml",
                         CONTAINER_XML.format(opf=FOLDER + "/" + OPF_PATH),
                         compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(FOLDER + "/" + OPF_PATH,
                         _opf_document(meta, lang, pages, cover, images),
                         compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(FOLDER + "/" + NCX_PATH,
                         _ncx_document(meta, toc_entries, lang),
                         compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(FOLDER + "/" + STYLE_PATH, css,
                         compress_type=zipfile.ZIP_DEFLATED)
        for page in pages:
            archive.writestr(FOLDER + "/" + page.href,
                             _page_document(page, lang),
                             compress_type=zipfile.ZIP_DEFLATED)
        if cover is not None:
            archive.writestr(FOLDER + "/" + cover.path, cover.data,
                             compress_type=zipfile.ZIP_STORED)
        for image in images:
            archive.writestr(FOLDER + "/" + image.path, image.data,
                             compress_type=zipfile.ZIP_STORED)

    return out_path
