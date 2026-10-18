"""HTML 类输入（单 HTML / 目录 / URL / CHM 解包后的目录）的公共实现。

旧 bookconv 针对 HTMLBuilder、EasyCHM 等几种具体生成器写了一堆正则。这里
改成一套通用流程：

1. 先找目录：``page.js``（EasyCHM 的章节表）→ ``.hhc``（CHM 自带目录）
   → ``index.html`` 等入口页里的链接 → 实在没有就按文件名自然排序。
2. 再把每个 HTML 页面的 ``<body>`` 清洗成 XHTML 片段：去掉脚本/样式/导航，
   保留段落、标题、列表、表格、引用、代码和插图；相对链接因为 EPUB 里没有
   对应文件，统一去掉 ``href`` 只留文字。
3. 插图交给 :class:`cvbook.images.ImageStore`，本地文件、远程 URL、data URI
   都支持。

解析器不依赖 calibre/pandoc，只用到 lxml（ebooklib 也会依赖它）。
"""

from __future__ import annotations

import base64
import html as html_lib
import os
import posixpath
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urljoin, urlsplit

from lxml import etree, html as lxml_html

from ..htmlutil import escape, plain_text, strip_paragraph_indent
from ..images import ImageStore
from ..models import BookMeta, Chapter
from .base import InputError, ParseOptions, decode_text, is_url

HTML_EXTS = ("html", "htm", "xhtml", "shtml")
#: 网页里这些扩展名的链接肯定不是章节
BINARY_EXTS = {
    "jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico",
    "css", "js", "json", "xml", "rss", "pdf", "zip", "rar", "7z", "gz",
    "mp3", "mp4", "m4a", "avi", "mov", "wmv", "flv", "swf",
}
#: 常见的入口页文件名（不含扩展名）
INDEX_STEMS = ("index", "cover", "start", "toc", "mulu", "contents",
               "default", "home", "main", "tempbook")

#: 这些标签整个丢掉
DROP_TAGS = {
    "script", "style", "noscript", "iframe", "frame", "frameset", "object",
    "embed", "applet", "form", "input", "button", "select", "option",
    "textarea", "link", "meta", "base", "audio", "video", "canvas", "svg",
    "map", "area", "source", "track", "param", "template",
}
BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl",
    "table", "pre", "blockquote", "hr", "section", "article", "main",
    "aside", "figure",
}

NAV_WORD_RE = re.compile(
    r"上一?[页章]|下一?[页章]|返回目录|回目录|回封面|目录|封面|首页|尾页|"
    r"上页|下页|返回|next|prev(?:ious)?|contents?|toc|home|cover|back",
    re.IGNORECASE,
)
NAV_LINK_RE = re.compile(
    r"^(?:上一?页|下一?页|上一?章|下一?章|返回目录|回目录|目录|封面|首页|"
    r"尾页|上页|下页|next|prev(?:ious)?|contents?|toc|home|cover|"
    r"回封面|返回|back)\s*[»›>»…\.\-—]*$",
    re.IGNORECASE,
)
#: 这些 <title> 显然是占位符，不能当书名
GENERIC_TITLES = {
    "", "untitled", "untitled document", "无标题", "无标题文档", "index",
    "目录", "首页", "new page 1", "新建网页 1",
}

#: class/id 正好等于这些词的才算页面框架（chapter-header 这种要保留）
CHROME_NAMES = {
    "nav", "navbar", "navigation", "menu", "footer", "header", "sidebar",
    "breadcrumb", "pagination", "pager", "toolbar", "advert",
    "advertisement", "ad", "ads", "banner",
}
PAGES_ARRAY_RE = re.compile(
    r"\b\w*pages\s*\[\s*\d+\s*\]\s*=\s*\[(.*?)\]\s*;",
    re.IGNORECASE | re.DOTALL,
)
MARKER_STARTS = (
    (re.compile(r"<!--\s*HTMLBUILERPART[^>]*-->", re.IGNORECASE),
     re.compile(r"<!--\s*/HTMLBUILERPART[^>]*-->", re.IGNORECASE)),
    (re.compile(r"<!--\s*BookContent\s+Start[^>]*-->", re.IGNORECASE),
     re.compile(r"<!--\s*BookContent\s+End[^>]*-->", re.IGNORECASE)),
)

_DEFAULT_UA = "Mozilla/5.0 (compatible; cvbook/0.3; +https://github.com/)"


# ---------------------------------------------------------------------------
# 资源读取


def decode_html(raw: bytes) -> str:
    """按 HTML 里声明的 charset 解码，失败再退回 UTF-8/GB18030。"""
    for pattern in (rb"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)",
                    rb"encoding\s*=\s*[\"']?([A-Za-z0-9._-]+)"):
        matched = re.search(pattern, raw[:4096], re.IGNORECASE)
        if matched:
            encoding = matched.group(1).decode("ascii", "ignore")
            try:
                return raw.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                pass
    return decode_text(raw)


def _strip_fragment(href: str) -> str:
    return href.split("#", 1)[0]


def _same_host(left: str, right: str) -> bool:
    def host(netloc: str) -> str:
        value = netloc.lower().split(":", 1)[0]
        return value[4:] if value.startswith("www.") else value
    return host(left) == host(right)


class Loader(object):
    """页面/插图的定位与读取接口。"""

    def read_bytes(self, href: str) -> Optional[bytes]:
        raise NotImplementedError

    def read_text(self, href: str) -> Optional[str]:
        data = self.read_bytes(href)
        return decode_html(data) if data is not None else None

    def exists(self, href: str) -> bool:
        return self.read_bytes(href) is not None

    def files(self) -> List[str]:
        """能列出文件时返回相对路径（URL 无法列目录）。"""
        return []

    def resolve(self, from_href: str, target: str) -> str:
        raise NotImplementedError

    def key(self, href: str) -> str:
        return href


class DirLoader(Loader):
    """本地目录（也是 CHM 解包后的目录）。"""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self._files: Optional[Dict[str, str]] = None

    def _normalize(self, href: str) -> str:
        href = unquote(_strip_fragment(href)).replace("\\", "/")
        href = href.split("?", 1)[0]
        return href.lstrip("/")

    def _listed(self) -> Dict[str, str]:
        if self._files is None:
            files: Dict[str, str] = {}
            for dirpath, _dirnames, filenames in os.walk(self.root):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                    files[rel.lower()] = rel
            self._files = files
        return self._files

    def _find(self, href: str) -> Optional[str]:
        rel = self._normalize(href)
        if not rel:
            return None
        candidate = os.path.normpath(os.path.join(self.root, rel))
        if not (candidate == self.root
                or candidate.startswith(self.root + os.sep)):
            return None
        if os.path.isfile(candidate):
            return candidate
        listed = self._listed().get(rel.lower())
        if listed:
            return os.path.join(self.root, *listed.split("/"))
        return None

    def read_bytes(self, href: str) -> Optional[bytes]:
        path = self._find(href)
        if path is None:
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def exists(self, href: str) -> bool:
        return self._find(href) is not None

    def files(self) -> List[str]:
        return sorted(self._listed().values())

    def resolve(self, from_href: str, target: str) -> str:
        target = _strip_fragment(target).replace("\\", "/")
        if is_url(target):
            return target
        if target.startswith("/"):
            return posixpath.normpath(target.lstrip("/"))
        base = posixpath.dirname(_strip_fragment(from_href).replace("\\", "/"))
        return posixpath.normpath(posixpath.join(base, target))

    def key(self, href: str) -> str:
        return self._normalize(href).lower()


class UrlLoader(Loader):
    """http(s) 页面。"""

    def __init__(self, entry: str) -> None:
        self.entry = entry
        self._cache: Dict[str, Optional[Tuple[bytes, Optional[str]]]] = {}

    def _fetch(self, url: str) -> Optional[Tuple[bytes, Optional[str]]]:
        url = _strip_fragment(url)
        if url in self._cache:
            return self._cache[url]
        request = urllib.request.Request(url, headers={
            "User-Agent": _DEFAULT_UA,
            "Accept-Encoding": "identity",
        })
        result: Optional[Tuple[bytes, Optional[str]]] = None
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                charset = response.headers.get_content_charset()
                result = (response.read(), charset)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                ValueError):
            result = None
        self._cache[url] = result
        return result

    def read_bytes(self, href: str) -> Optional[bytes]:
        fetched = self._fetch(self.resolve(self.entry, href))
        return fetched[0] if fetched is not None else None

    def read_text(self, href: str) -> Optional[str]:
        fetched = self._fetch(self.resolve(self.entry, href))
        if fetched is None:
            return None
        data, charset = fetched
        if charset:
            try:
                return data.decode(charset)
            except (LookupError, UnicodeDecodeError):
                pass
        return decode_html(data)

    def exists(self, href: str) -> bool:
        return self.read_bytes(href) is not None

    def resolve(self, from_href: str, target: str) -> str:
        base = from_href if is_url(from_href) else self.entry
        target = target.strip()
        if target.startswith("//"):
            scheme = urlsplit(base).scheme or "https"
            target = scheme + ":" + target
        return _strip_fragment(urljoin(base, target))

    def key(self, href: str) -> str:
        return self.resolve(self.entry, href)


def fetch_url(url: str, timeout: int = 15) -> Optional[bytes]:
    """下载远程图片等资源。"""
    if url.startswith("//"):
        url = "https:" + url
    request = urllib.request.Request(url, headers={
        "User-Agent": _DEFAULT_UA,
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 目录发现


@dataclass
class TocEntry:
    title: str
    href: Optional[str]
    level: int = 1

    @property
    def virtual(self) -> bool:
        return not self.href


def _local_tag(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def parse_html(text: str):
    if not text or not text.strip():
        return None
    # XHTML/EPUB 常带 XML 声明，lxml 的 HTML 解析器不接受 str + 声明
    text = re.sub(r"^\ufeff?\s*<\?xml[^>]*\?>", "", text,
                  count=1, flags=re.IGNORECASE)
    parser = lxml_html.HTMLParser(encoding="utf-8", recover=True)
    try:
        return lxml_html.fromstring(text, parser=parser)
    except (etree.ParserError, ValueError):
        return None


def clean_title(title: str) -> str:
    if not title:
        return ""
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", title))
    title = re.sub(r"\s+", " ", title).strip(" 　\t·○")
    return title


def page_title(text: str) -> str:
    matched = re.search(r"<title[^>]*>(.*?)</title>", text,
                        re.IGNORECASE | re.DOTALL)
    if matched:
        title = clean_title(matched.group(1))
        if title:
            return title
    matched = re.search(r"<h[12][^>]*>(.*?)</h[12]>", text,
                        re.IGNORECASE | re.DOTALL)
    return clean_title(matched.group(1)) if matched else ""


def _is_index_name(href: str) -> bool:
    path = urlsplit(href).path if is_url(href) else href
    if path.endswith("/"):
        return True
    name = os.path.basename(path).lower()
    stem = name.rsplit(".", 1)[0]
    return stem in INDEX_STEMS or bool(re.fullmatch(r"index\d+", stem))


def _natural_key(path: str):
    result = []
    for part in re.split(r"(\d+)", path.lower()):
        result.append((0, int(part)) if part.isdigit() else (1, part))
    return result


def index_candidates(loader: Loader) -> List[str]:
    names: List[str] = []
    for stem in INDEX_STEMS:
        for ext in ("html", "htm"):
            names.append("%s.%s" % (stem, ext))
    found: List[str] = []
    for name in names:
        if loader.exists(name):
            found.append(name)
    number = 1
    while loader.exists("index%d.html" % number):
        if "index%d.html" % number not in found:
            found.append("index%d.html" % number)
        number += 1
    return found


def all_html_entries(loader: Loader, entry: Optional[str] = None) -> List[TocEntry]:
    files = loader.files()
    html_files = [name for name in files
                  if name.rsplit(".", 1)[-1].lower() in HTML_EXTS]
    if not html_files and entry:
        html_files = [entry]
    if not html_files:
        # 少数 CHM 只有 txt/ 正文，没有 page.js/.hhc
        html_files = [name for name in files
                      if name.lower().endswith(".txt")]

    selected: List[str] = []
    for name in sorted(html_files, key=_natural_key):
        base = posixpath.basename(name).lower()
        stem = base.rsplit(".", 1)[0]
        if stem in INDEX_STEMS or re.fullmatch(r"index\d+", stem):
            continue
        if base.startswith("_"):
            continue
        selected.append(name)

    if not selected:
        selected = sorted(html_files, key=_natural_key)
    return [TocEntry("", name, 1) for name in selected]


def find_hhc(loader: Loader) -> List[str]:
    files = loader.files()
    return sorted((name for name in files if name.lower().endswith(".hhc")),
                  key=lambda name: (name.count("/"), _natural_key(name)))


def parse_hhc(loader: Loader, href: str) -> List[TocEntry]:
    text = loader.read_text(href)
    if not text:
        return []
    tree = parse_html(text)
    if tree is None:
        return []

    entries: List[TocEntry] = []

    def walk(ul, level: int) -> None:
        for li in ul:
            if _local_tag(li.tag) != "li":
                continue
            title = ""
            target = ""
            for child in li:
                tag = _local_tag(child.tag)
                if tag == "object":
                    params: Dict[str, str] = {}
                    for param in child:
                        if _local_tag(param.tag) != "param":
                            continue
                        name = (param.get("name") or "").strip().lower()
                        value = param.get("value") or ""
                        if name:
                            params[name] = value
                    title = params.get("name", "") or title
                    target = params.get("local", "") or target
                elif tag == "a" and not target:
                    target = child.get("href") or ""
                    title = title or child.text_content()
            title = clean_title(title)
            target = target.strip()
            if title or target:
                virtual = (not target
                               or target.startswith(("#", "javascript:")))
                entries.append(TocEntry(
                    title=title or clean_title(target),
                    href=None if virtual else target,
                    level=level,
                ))
            for child in li:
                if _local_tag(child.tag) in ("ul", "ol"):
                    walk(child, level + 1)

    for ul in tree.iter():
        if _local_tag(ul.tag) in ("ul", "ol"):
            parent = ul.getparent()
            if parent is None or _local_tag(parent.tag) not in ("ul", "ol", "li"):
                walk(ul, 1)
            if entries:
                break

    if not entries:
        for anchor in tree.iter("a"):
            target = (anchor.get("href") or "").strip()
            title = clean_title(anchor.text_content())
            if target and not target.startswith(("#", "javascript:")):
                entries.append(TocEntry(title, target, 1))
    return entries


def _split_js_strings(body: str) -> List[str]:
    """从 ``['a','b','c']`` 里取出字符串字段（支持转义）。"""
    fields: List[str] = []
    pos = 0
    length = len(body)
    while pos < length:
        char = body[pos]
        if char not in ("'", '"'):
            pos += 1
            continue
        value, pos = _read_js_string(body, pos)
        if value is not None:
            fields.append(value)
    return fields


def _read_js_string(text: str, pos: int) -> Tuple[Optional[str], int]:
    if pos >= len(text) or text[pos] not in ("'", '"'):
        return None, pos
    quote = text[pos]
    pos += 1
    out: List[str] = []
    while pos < len(text):
        char = text[pos]
        if char == quote:
            return "".join(out), pos + 1
        if char == "\\" and pos + 1 < len(text):
            nxt = text[pos + 1]
            mapping = {"n": "\n", "r": "\r", "t": "\t",
                       "\\": "\\", "'": "'", '"': '"'}
            if nxt in mapping:
                out.append(mapping[nxt])
                pos += 2
                continue
            if nxt == "x" and pos + 3 < len(text):
                try:
                    out.append(chr(int(text[pos + 2:pos + 4], 16)))
                    pos += 4
                    continue
                except ValueError:
                    pass
            if nxt == "u" and pos + 5 < len(text):
                try:
                    out.append(chr(int(text[pos + 2:pos + 6], 16)))
                    pos += 6
                    continue
                except ValueError:
                    pass
            out.append(nxt)
            pos += 2
            continue
        if char == "\n":
            break
        out.append(char)
        pos += 1
    return "".join(out), pos


def _pagejs_hierarchy(fields: Sequence[str], title: str) -> List[str]:
    """从 ``page.js`` 的字段里猜卷/部层级，最多两层。"""
    hierarchy: List[str] = []
    for index, value in enumerate(fields):
        if index == 0:
            continue
        raw = (value or "").strip()
        if not raw:
            continue
        if raw.startswith("<") or "<" in raw:
            continue
        text = clean_title(raw)
        if not text:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?[kKmM]?", text):
            continue
        if text.lower() in ("finish", "目录"):
            continue
        if "★" in text or text.startswith("A～"):
            continue
        if text == title or text in hierarchy:
            continue
        hierarchy.append(text)
        if len(hierarchy) >= 2:
            break
    return hierarchy


def discover_pagejs(loader: Loader) -> List[TocEntry]:
    if not loader.files():
        return []
    candidates = (
        ("js/page.js", "txt"),
        ("js/pages.js", "data"),
        ("index/page.js", "index"),
        ("page.js", "txt"),
        ("pages.js", "txt"),
        ("Home1.htm", "txt"),
    )
    for index_file, text_dir in candidates:
        if not loader.exists(index_file):
            continue
        text = loader.read_text(index_file)
        if not text:
            continue
        pages: List[List[str]] = []
        for matched in PAGES_ARRAY_RE.finditer(text):
            fields = _split_js_strings(matched.group(1))
            if len(fields) >= 2:
                pages.append(fields)
        if not pages:
            continue

        entries: List[TocEntry] = []
        last_by_level: Dict[int, str] = {}
        for idx, fields in enumerate(pages):
            filename = fields[0].strip()
            if not filename:
                continue

            title = ""
            hierarchy: List[str] = []
            if (len(fields) >= 6 and fields[5].strip().lower() == "finish"
                    and clean_title(fields[2])):
                # 莫言作品集那类：['1-3','纯文学','酒国','莫言','简介','finish']
                title = clean_title(fields[2])
            else:
                title = clean_title(fields[1]) if len(fields) > 1 else ""
                hierarchy = _pagejs_hierarchy(fields, title)

            content_candidates = [
                posixpath.join(text_dir, filename + ".txt"),
                filename + ".txt",
                filename + ".html",
                filename + ".htm",
                filename + "/index.html",
                filename + "/index.htm",
                filename + "/start.html",
            ]
            target = next((candidate for candidate in content_candidates
                           if loader.exists(candidate)), content_candidates[0])

            for level_index, volume in enumerate(hierarchy):
                level = level_index + 1
                if last_by_level.get(level) != volume:
                    entries.append(TocEntry(volume, None, level))
                    last_by_level[level] = volume
                    for deeper in [key for key in last_by_level if key > level]:
                        del last_by_level[deeper]
            chapter_level = len(hierarchy) + 1
            if _is_index_name(target) and loader.exists(target):
                sub = parse_index(loader, target)
                if len(sub) >= 2:
                    entries.append(TocEntry(title, None, chapter_level))
                    for item in sub:
                        entries.append(TocEntry(item.title, item.href,
                                                chapter_level + item.level))
                    continue
            entries.append(TocEntry(title, target, level=chapter_level))
        if entries:
            return entries
    return []


def _link_level(anchor) -> int:
    level = 0
    parent = anchor.getparent()
    while parent is not None:
        if _local_tag(parent.tag) in ("ul", "ol"):
            level += 1
        parent = parent.getparent()
    return min(max(level, 1), 3)


def _anchor_title(anchor) -> str:
    title = clean_title(anchor.text_content())
    if title:
        return title
    title = clean_title(anchor.get("title") or "")
    if title:
        return title
    image = anchor.find(".//img")
    if image is not None:
        return clean_title(image.get("alt") or image.get("title") or "")
    return ""


def _candidate_links(loader: Loader, href: str, text: str):
    tree = parse_html(text)
    if tree is None:
        return []
    link_base = href
    base = tree.find(".//base")
    if base is not None and (base.get("href") or "").strip():
        link_base = loader.resolve(href, base.get("href").strip())
    result = []
    for anchor in tree.iter("a"):
        target = (anchor.get("href") or "").strip()
        if not target or target.startswith(("#", "javascript:", "mailto:",
                                            "tel:", "data:")):
            continue
        title = _anchor_title(anchor)
        if not title or NAV_LINK_RE.match(title):
            continue
        resolved = loader.resolve(link_base, target)
        if loader.key(resolved) == loader.key(link_base):
            continue
        suffix = posixpath.basename(urlsplit(resolved).path).rsplit(".", 1)
        ext = suffix[1].lower() if len(suffix) > 1 else ""
        if is_url(resolved):
            # 只跟同一个站点的章节链接，避免把广告/外链当正文去抓
            if not is_url(link_base):
                continue
            if not _same_host(urlsplit(resolved).netloc,
                              urlsplit(link_base).netloc):
                continue
            # 网页上章节可能是 .php/.asp/无扩展名，只排除明显的静态资源
            if ext in BINARY_EXTS:
                continue
        elif ext and ext not in HTML_EXTS:
            continue
        result.append((title, resolved, _link_level(anchor)))
    return result


def follow_redirect(loader: Loader, href: str,
                    text: Optional[str] = None) -> Optional[str]:
    """识别 iframe / frame / meta refresh 跳转，返回跳转目标。"""
    if text is None:
        text = loader.read_text(href)
    if not text:
        return None
    visible = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ",
                     text, flags=re.IGNORECASE | re.DOTALL)
    visible = clean_title(re.sub(r"<[^>]+>", " ", visible))
    if len(visible) > 300:
        return None                 # 正文页里的 iframe 广告不算跳转
    patterns = (
        r'<iframe\b[^>]*\bsrc=["\']([^"\']+)',
        r'<frame\b[^>]*\bsrc=["\']([^"\']+)',
        r'<meta\b[^>]*http-equiv=["\']?refresh["\']?[^>]*'
        r'content=["\'][^"\']*?url=([^"\'>;\s]+)',
        r'<meta\b[^>]*content=["\'][^"\']*?url=([^"\'>;\s]+)[^>]*'
        r'http-equiv=["\']?refresh',
    )
    for pattern in patterns:
        matched = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not matched:
            continue
        target = loader.resolve(href, html_lib.unescape(matched.group(1)))
        if loader.key(target) == loader.key(href):
            continue
        if loader.exists(target):
            return target
    return None


def _looks_like_index(loader: Loader, href: str, text: str) -> bool:
    links = _candidate_links(loader, href, text)
    if len(links) >= 3:
        return len(plain_text(text)) < 3000 or len(links) >= 8
    # 封面页可能只链接到两三个子书目录
    return any(_is_index_name(target) for _, target, _ in links)


def parse_index(loader: Loader, href: str,
                depth: int = 0,
                visited: Optional[Set[str]] = None) -> List[TocEntry]:
    if visited is None:
        visited = set()
    key = loader.key(href)
    if key in visited:
        return []
    visited.add(key)

    text = loader.read_text(href)
    if not text:
        return []
    redirected = follow_redirect(loader, href, text)
    if redirected and loader.key(redirected) not in visited:
        return parse_index(loader, redirected, depth, visited)
    entries: List[TocEntry] = []
    for title, target, level in _candidate_links(loader, href, text):
        target_key = loader.key(target)
        if target_key in visited:
            continue
        if _is_index_name(target):
            if is_url(target):
                same_site = (is_url(href)
                             and _same_host(urlsplit(target).netloc,
                                            urlsplit(href).netloc))
                if depth >= 2 or not same_site:
                    continue
            else:
                same_dir = (posixpath.dirname(target)
                            == posixpath.dirname(href))
                if same_dir or depth >= 2:
                    # 同级 index1.html 之类由 index_candidates 统一收
                    continue
            sub = parse_index(loader, target, depth + 1, visited)
            if len(sub) >= 2:
                entries.append(TocEntry(title, None, level))
                for item in sub:
                    entries.append(TocEntry(item.title, item.href,
                                            level + item.level))
                visited.add(target_key)
            continue
        visited.add(target_key)
        entries.append(TocEntry(title, target, level))
    return entries


def discover(loader: Loader, entry: Optional[str] = None) -> List[TocEntry]:
    if entry:
        entry = follow_redirect(loader, entry) or entry
        if not _is_index_name(entry):
            text = loader.read_text(entry)
            if text and _looks_like_index(loader, entry, text):
                entries = parse_index(loader, entry)
                if entries:
                    return entries
            return [TocEntry("", entry, 1)]

    # EasyCHM 的 page.js 通常比 .hhc 更细，先试它
    entries = discover_pagejs(loader)
    if entries:
        return entries

    for hhc in find_hhc(loader)[:3]:
        entries = parse_hhc(loader, hhc)
        if entries:
            return entries

    candidates = [entry] if entry else index_candidates(loader)
    entries = []
    visited: Set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        entries.extend(parse_index(loader, candidate, visited=visited))
    if entries:
        return entries

    return all_html_entries(loader, entry)


# ---------------------------------------------------------------------------
# 正文清洗


class _RenderContext(object):
    def __init__(self, loader: Loader, href: str, images: ImageStore,
                 options: ParseOptions) -> None:
        self.loader = loader
        self.href = href
        self.images = images
        self.options = options
        self._image_warned: Set[str] = set()


def _slice_marked_content(text: str) -> str:
    for start_re, end_re in MARKER_STARTS:
        start = start_re.search(text)
        if not start:
            continue
        end = end_re.search(text, start.end())
        content = text[start.end():end.start() if end else len(text)]
        if content.strip():
            return content
    return text


def _unwrap_document_write(text: str) -> str:
    if "document.write" not in text:
        return text
    out: List[str] = []
    pos = 0
    for matched in re.finditer(r"document\.write\s*\(\s*", text):
        out.append(text[pos:matched.start()])
        cursor = matched.end()
        parts: List[str] = []
        while True:
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            value, next_pos = _read_js_string(text, cursor)
            if value is None:
                break
            parts.append(value)
            cursor = next_pos
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor < len(text) and text[cursor] == "+":
                cursor += 1
                continue
            break
        if parts:
            out.append("".join(parts))
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor < len(text) and text[cursor] == ")":
                cursor += 1
                if cursor < len(text) and text[cursor] == ";":
                    cursor += 1
            pos = cursor
        else:
            out.append(text[matched.start():matched.end()])
            pos = matched.end()
    out.append(text[pos:])
    result = "".join(out)
    return result if result.strip() else text


def _is_chrome(node) -> bool:
    style = (node.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if node.get("hidden") is not None:
        return True
    marker = " ".join(filter(None, (node.get("class"), node.get("id"))))
    return any(token.lower() in CHROME_NAMES for token in marker.split())


def _attrs_for_cell(node) -> str:
    attrs = ""
    for name in ("colspan", "rowspan"):
        value = node.get(name)
        if value and value.strip().isdigit():
            attrs += ' %s="%s"' % (name, value.strip())
    return attrs


def _image_src(node) -> str:
    for name in ("data-src", "data-original", "src"):
        value = node.get(name)
        if value and value.strip():
            return value.strip()
    srcset = (node.get("srcset") or "").strip()
    if srcset:
        return srcset.split(",", 1)[0].strip().split(" ", 1)[0]
    return ""


def _data_uri_bytes(src: str) -> Optional[Tuple[str, bytes]]:
    matched = re.match(r"data:([^;,]+)(?:;charset=[^;,]+)?(;base64)?,(.*)",
                       src, re.IGNORECASE | re.DOTALL)
    if not matched:
        return None
    media_type, base64_flag, data = matched.groups()
    ext = media_type.split("/")[-1].lower()
    ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(ext, ext)
    try:
        if base64_flag:
            return ext, base64.b64decode(data, validate=False)
        return ext, unquote(data).encode("utf-8")
    except (ValueError, TypeError):
        return None


def _store_image(ctx: _RenderContext, src: str) -> Optional[str]:
    if not src:
        return None
    src = html_lib.unescape(src).strip()
    if not src or src.startswith("#"):
        return None

    if src.startswith("data:"):
        decoded = _data_uri_bytes(src)
        if decoded is None:
            return None
        ext, data = decoded
        return ctx.images.add_bytes("image." + ext, data,
                                    source="data:" + str(hash(data)))

    if src.startswith("//"):
        scheme = urlsplit(ctx.href).scheme if is_url(ctx.href) else "https"
        src = scheme + ":" + src
    if is_url(src):
        data = fetch_url(src)
        if data is None:
            if src not in ctx._image_warned:
                ctx._image_warned.add(src)
                print("!!! 下载插图失败: %s（页面 %s）" % (src, ctx.href),
                      file=sys.stderr)
            return None
        name = posixpath.basename(urlsplit(src).path) or "image"
        return ctx.images.add_bytes(name, data, source=ctx.loader.key(src))

    target = ctx.loader.resolve(ctx.href, src)
    data = ctx.loader.read_bytes(target)
    if data is None:
        if src not in ctx._image_warned:
            ctx._image_warned.add(src)
            print("!!! 找不到插图: %s（页面 %s）" % (src, ctx.href),
                  file=sys.stderr)
        return None
    name = posixpath.basename(urlsplit(target.replace("\\", "/")).path) or "image"
    return ctx.images.add_bytes(name, data, source=ctx.loader.key(target))


def _render_inner(node, ctx: _RenderContext) -> str:
    parts: List[str] = []
    if node.text:
        parts.append(escape(node.text))
    for child in node:
        parts.append(_render_node(child, ctx))
        if child.tail:
            parts.append(escape(child.tail))
    return "".join(parts)


def _render_flow(node, ctx: _RenderContext) -> str:
    """按块/行内分组渲染：零散文本和 ``<br>`` 会被包成 ``<p>``。"""
    parts: List[str] = []
    buffer: List[str] = []

    def flush() -> None:
        if not buffer:
            return
        text = "".join(buffer).strip()
        buffer.clear()
        if text:
            parts.append(_paragraphize_br(text))

    if node.text:
        buffer.append(escape(node.text))
    for child in node:
        tag = _local_tag(child.tag)
        child_html = _render_node(child, ctx)
        if tag in BLOCK_TAGS or tag in ("nav", "header", "footer"):
            flush()
            if child_html:
                parts.append(child_html)
        else:
            buffer.append(child_html)
        if child.tail:
            buffer.append(escape(child.tail))
    flush()
    return "\n".join(parts)


def _render_node(node, ctx: _RenderContext) -> str:
    tag = _local_tag(node.tag)
    if not tag or tag in DROP_TAGS:
        return ""
    if tag in ("nav", "header", "footer") or _is_chrome(node):
        return ""

    if tag == "div" or tag in ("section", "article", "main", "aside",
                                "figure"):
        return "<div>%s</div>" % _render_flow(node, ctx)
    if tag == "blockquote":
        return "<blockquote>%s</blockquote>" % _render_flow(node, ctx)

    if tag == "img":
        src = _image_src(node)
        stored = _store_image(ctx, src) if src else None
        if stored is None:
            alt = clean_title(node.get("alt") or "")
            return escape(alt) if alt else ""
        attrs = ' src="%s" alt="%s"' % (
            escape("../" + stored),
            escape(node.get("alt") or ""),
        )
        for name in ("width", "height"):
            value = node.get(name)
            if value and value.strip().isdigit():
                attrs += ' %s="%s"' % (name, value.strip())
        return "<img%s/>" % attrs

    inner = _render_inner(node, ctx)

    if tag in ("br", "hr"):
        return "<%s/>" % tag
    if tag in ("p", "div"):
        return "<%s>%s</%s>" % (tag, inner, tag)
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = min(6, int(tag[1]) + 1)      # 页面标题由我们加，正文标题降一级
        return "<h%d>%s</h%d>" % (level, inner, level)
    if tag in ("ul", "ol", "li", "dl", "dt", "dd", "blockquote", "pre",
               "code", "b", "strong", "i", "em", "s", "strike", "del",
               "sub", "sup", "kbd", "samp", "var", "ruby", "rt", "rp"):
        if tag == "strike":
            tag = "s"
        elif tag == "del":
            tag = "s"
        return "<%s>%s</%s>" % (tag, inner, tag)
    if tag in ("table", "thead", "tbody", "tfoot", "tr", "caption"):
        return "<%s>%s</%s>" % (tag, inner, tag)
    if tag in ("th", "td"):
        return "<%s%s>%s</%s>" % (tag, _attrs_for_cell(node), inner, tag)
    if tag == "a":
        label = clean_title(inner)
        if not label:
            return inner if "<img" in inner.lower() else ""
        if NAV_LINK_RE.match(label):
            return ""
        href = (node.get("href") or "").strip()
        if is_url(href):
            return '<a href="%s">%s</a>' % (escape(href), inner)
        return inner
    return inner


def _paragraphize_br(fragment: str) -> str:
    if not fragment.strip():
        return ""
    if re.search(r"<p\b", fragment, re.IGNORECASE):
        return fragment
    if re.search(r"<(?:div|table|ul|ol|dl|pre|blockquote|h[1-6])\b",
                 fragment, re.IGNORECASE):
        return fragment
    if not re.search(r"<br\b", fragment, re.IGNORECASE):
        return "<p>%s</p>" % fragment.strip() if plain_text(fragment).strip() else fragment
    parts = re.split(r"<br\s*/?>", fragment, flags=re.IGNORECASE)
    paragraphs = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not plain_text(part).strip() and "<img" not in part.lower():
            continue
        paragraphs.append("<p>%s</p>" % part)
    return "\n".join(paragraphs)


def _normalize_fragment(fragment: str) -> str:
    """用 lxml 再解析一遍，修掉 ``<br>`` 切段等操作可能造成的标签错位。"""
    if not fragment.strip():
        return ""
    try:
        wrapper = lxml_html.fragment_fromstring(fragment, create_parent="div")
    except (etree.ParserError, ValueError):
        return fragment
    parts: List[str] = []
    if wrapper.text:
        parts.append(escape(wrapper.text))
    for child in wrapper:
        parts.append(etree.tostring(child, encoding="unicode", method="xml",
                                           with_tail=False))
        if child.tail:
            parts.append(escape(child.tail))
    return "".join(parts)


def _split_br_paragraphs(fragment: str) -> str:
    """把 ``<p>a<br><br>b</p>`` 拆成两个段落。"""
    paragraph = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
    double_break = re.compile(r"(?:<br\s*/?>\s*){2,}", re.IGNORECASE)

    def replace(matched: "re.Match[str]") -> str:
        inner = matched.group(1)
        if not double_break.search(inner):
            return matched.group(0)
        parts = [part for part in double_break.split(inner) if part.strip()]
        return "".join("<p>%s</p>" % part for part in parts)

    return paragraph.sub(replace, fragment)


def _strip_nav_paragraphs(fragment: str) -> str:
    """去掉“上一章 目录 下一章”这种纯导航段落。"""
    paragraph = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)

    def replace(matched: "re.Match[str]") -> str:
        text = plain_text(matched.group(1)).strip()
        if len(text) > 40 or len(NAV_WORD_RE.findall(text)) < 2:
            return matched.group(0)
        rest = NAV_WORD_RE.sub("", text)
        if not rest.strip(" \t\u3000»›>….-—|/\\"):
            return ""
        return matched.group(0)

    return paragraph.sub(replace, fragment)


def _strip_heading_duplicate(fragment: str, title: str) -> str:
    if not title:
        return fragment
    matched = re.match(r"\s*<h[1-6][^>]*>(.*?)</h[1-6]>\s*",
                       fragment, re.DOTALL | re.IGNORECASE)
    if matched and clean_title(matched.group(1)) == title:
        return fragment[matched.end():]
    return fragment


def render_page(text: str, href: str, loader: Loader, images: ImageStore,
                options: ParseOptions, title: str = "") -> str:
    text = _slice_marked_content(text)
    text = _unwrap_document_write(text)
    if text and not re.search(r"<[A-Za-z!/]", text):
        # 纯文本页（EasyCHM 的 txt 有时没有标签）：一行一段
        paragraphs = []
        for line in text.splitlines():
            line = line if options.keep_indent else line.strip()
            if line.strip():
                paragraphs.append("<p>%s</p>" % escape(line))
        return "\n".join(paragraphs)

    tree = parse_html(text)
    if tree is None:
        return ""

    body = tree.find(".//body")
    if body is None:
        body = tree

    page_href = href
    base = tree.find(".//base")
    if base is not None and (base.get("href") or "").strip():
        page_href = loader.resolve(href, base.get("href").strip())

    ctx = _RenderContext(loader, page_href, images, options)
    fragment = _render_flow(body, ctx)
    fragment = _paragraphize_br(fragment)
    fragment = re.sub(r"<p>\s*</p>", "", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<div>\s*</div>", "", fragment, flags=re.IGNORECASE)
    fragment = _normalize_fragment(fragment)
    fragment = _split_br_paragraphs(fragment)
    fragment = _strip_nav_paragraphs(fragment)
    fragment = _strip_heading_duplicate(fragment, title)
    if not options.keep_indent:
        fragment = strip_paragraph_indent(fragment)
    return fragment.strip()


def build_chapters(loader: Loader, entries: Sequence[TocEntry],
                   images: ImageStore, options: ParseOptions) -> List[Chapter]:
    chapters: List[Chapter] = []
    for entry in entries:
        level = max(1, entry.level)
        if entry.virtual:
            title = clean_title(entry.title)
            if not title:
                continue
            html = '<h1 class="chapter-title">%s</h1>' % escape(title)
            chapters.append(Chapter(title, html, level))
            continue

        href = entry.href or ""
        text = loader.read_text(href)
        if text is None:
            print("!!! 读不到页面: %s" % href, file=sys.stderr)
            continue
        redirected = follow_redirect(loader, href, text)
        if redirected:
            href = redirected
            text = loader.read_text(href)
            if text is None:
                print("!!! 读不到页面: %s" % href, file=sys.stderr)
                continue
        title = clean_title(entry.title)
        if not title:
            title = page_title(text)
        if not title:
            title = os.path.splitext(posixpath.basename(href))[0]
        body = render_page(text, href, loader, images, options, title=title)
        if not body.strip() and not title:
            continue
        heading = ('<h1 class="chapter-title">%s</h1>' % escape(title)
                   if title else "")
        html = heading + ("\n" + body if body else "")
        chapters.append(Chapter(title=title or "正文", html=html, level=level))
    return chapters


# ---------------------------------------------------------------------------
# 元数据


def read_metadata(loader: Loader, entry: Optional[str],
                  depth: int = 0) -> BookMeta:
    meta = BookMeta()
    if not entry:
        return meta
    text = loader.read_text(entry)
    if not text:
        return meta
    if depth < 3:
        redirected = follow_redirect(loader, entry, text)
        if redirected:
            return read_metadata(loader, redirected, depth + 1)

    meta.title = page_title(text)
    if meta.title.lower() in GENERIC_TITLES:
        meta.title = ""
    if not meta.title:
        matched = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            text, re.IGNORECASE)
        if matched:
            candidate = clean_title(matched.group(1))
            if candidate.lower() not in GENERIC_TITLES:
                meta.title = candidate

    for pattern in (
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']author["\']',
    ):
        matched = re.search(pattern, text, re.IGNORECASE)
        if matched:
            author = clean_title(matched.group(1))
            if author:
                meta.authors = [author]
                break

    if not meta.authors:
        matched = re.search(r"作\s*者\s*[:：]\s*([^\s<]{1,30})", text)
        if matched:
            author = clean_title(matched.group(1))
            if author:
                meta.authors = [author]

    matched = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)',
        text, re.IGNORECASE)
    if matched:
        meta.comments = clean_title(matched.group(1))
    return meta


def _metadata_entry(loader: Loader) -> Optional[str]:
    for candidate in index_candidates(loader):
        return candidate
    for entry in discover(loader):
        if entry.href:
            return entry.href
    return None


def metadata_for_dir(root: str) -> BookMeta:
    loader = DirLoader(root)
    return read_metadata(loader, _metadata_entry(loader))


# ---------------------------------------------------------------------------
# 对外入口


def parse_directory(root: str, images: ImageStore,
                    options: ParseOptions,
                    entry: Optional[str] = None) -> List[Chapter]:
    loader = DirLoader(root)
    entries = discover(loader, entry)
    if not entries:
        raise InputError("在目录里没有找到可解析的 HTML 页面: %s" % root)
    return build_chapters(loader, entries, images, options)


def parse_source(source, images: ImageStore,
                 options: ParseOptions) -> List[Chapter]:
    if source.is_url:
        loader: Loader = UrlLoader(source.path)
        entry: Optional[str] = source.path
    elif source.is_dir:
        loader = DirLoader(source.path)
        entry = None
    else:
        loader = DirLoader(source.base_dir)
        entry = source.name
    entries = discover(loader, entry)
    if not entries:
        raise InputError("没有找到可解析的 HTML 页面: %s" % source.path)
    return build_chapters(loader, entries, images, options)


def metadata_for_source(source) -> BookMeta:
    if source.is_url:
        loader: Loader = UrlLoader(source.path)
        entry: Optional[str] = source.path
    elif source.is_dir:
        loader = DirLoader(source.path)
        entry = None
    else:
        loader = DirLoader(source.base_dir)
        entry = source.name
    if entry is None:
        entry = _metadata_entry(loader)
    return read_metadata(loader, entry)


__all__ = [
    "DirLoader", "Loader", "TocEntry", "UrlLoader",
    "all_html_entries", "build_chapters", "clean_title", "discover",
    "discover_pagejs", "metadata_for_dir", "metadata_for_source",
    "parse_directory", "parse_hhc", "parse_index", "parse_source",
    "read_metadata", "render_page",
]
