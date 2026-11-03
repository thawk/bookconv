"""从原创小说站点抓取封面和简介。

站点包括起点中文网、纵横中文网、17K小说网和晋江文学城。搜索页的解析都写成
纯函数（``parse_*``），方便测试；网络请求集中在 :class:`HttpClient` 和各
Provider 里。

封面统一取站点能提供的大图（起点 / 纵横 / 17K 都能到 600×800，晋江取原图），
简介保存成 UTF-8 纯文本。
"""

from __future__ import annotations

import concurrent.futures
import difflib
import gzip
import html as html_mod
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .images import image_size, sniff_image_ext
from .metadata import bookcover_base_name

UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

DEFAULT_TIMEOUT = 20
#: 原样沿用的图片扩展名（不含点）
IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp", "bmp")


class FetchError(Exception):
    """网络请求失败。"""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

@dataclass
class Response:
    url: str
    status: int
    content: bytes
    headers: Dict[str, str]

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")


class HttpClient:
    """带重试、gzip 解压和自定义 UA 的极简 HTTP 客户端。"""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT,
                 proxy: Optional[str] = None, retries: int = 2,
                 verbose: bool = False) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.verbose = verbose
        if proxy:
            handlers = [urllib.request.ProxyHandler({"http": proxy,
                                                     "https": proxy})]
        else:
            # 不读取系统代理，避免被本机代理配置带偏
            handlers = [urllib.request.ProxyHandler({})]
        self.opener = urllib.request.build_opener(*handlers)

    def get(self, url: str, referer: Optional[str] = None,
            ua: str = UA_DESKTOP, binary: bool = False) -> Response:
        headers = {
            "User-Agent": ua,
            "Accept": "*/*" if binary else
                      ("text/html,application/xhtml+xml,"
                       "application/json;q=0.9,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            "Accept-Encoding": "gzip, deflate",
        }
        if referer:
            headers["Referer"] = referer

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(0.6 * attempt)
            request = urllib.request.Request(url, headers=headers)
            try:
                with self.opener.open(request, timeout=self.timeout) as resp:
                    raw = self._decompress(resp.read(), resp.headers)
                    return Response(resp.geturl(), resp.status, raw,
                                    {key.lower(): value
                                     for key, value in resp.headers.items()})
            except urllib.error.HTTPError as error:
                raw = b""
                try:
                    raw = self._decompress(error.read(), error.headers)
                except Exception:
                    pass
                return Response(url, error.code, raw,
                                {key.lower(): value
                                 for key, value in (error.headers or {}).items()})
            except (urllib.error.URLError, OSError, ValueError) as error:
                last_error = error
                if self.verbose:
                    print("提示: 请求失败（%d/%d）: %s — %s"
                          % (attempt + 1, self.retries + 1, url, error),
                          file=sys.stderr)
        raise FetchError(str(last_error))

    @staticmethod
    def _decompress(raw: bytes, headers) -> bytes:
        encoding = (headers.get("Content-Encoding") or "").lower()
        if encoding == "gzip":
            try:
                return gzip.decompress(raw)
            except OSError:
                return raw
        if encoding == "deflate":
            try:
                return zlib.decompress(raw)
            except zlib.error:
                try:
                    return zlib.decompress(raw, -zlib.MAX_WBITS)
                except zlib.error:
                    return raw
        return raw


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------

def decode_body(resp: Response, fallback: str = "utf-8") -> str:
    """按响应头或页面里的 charset 解码，最后依次退回 utf-8 / gb18030。"""
    charset = None
    match = re.search(r"charset=([\w-]+)", resp.content_type, re.I)
    if match:
        charset = match.group(1)
    if not charset:
        head = resp.content[:4096].decode("ascii", "ignore")
        match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", head, re.I)
        if match:
            charset = match.group(1)
    for encoding in filter(None, [charset, fallback, "utf-8", "gb18030"]):
        try:
            return resp.content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return resp.content.decode("utf-8", "replace")


def text_of(fragment: str) -> str:
    """把 HTML 片段转成保留段落的纯文本。"""
    if not fragment:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", fragment)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h\d)\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html_mod.unescape(text)
    text = text.replace("\xa0", " ").replace("\u3000", " ")

    lines: List[str] = []
    blank = 0
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)
            blank = 0
        elif lines:
            blank += 1
            if blank == 1:
                lines.append("")
    return "\n".join(lines).strip()


def inline_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", text_of(fragment)).strip()


def clean_title(value: str) -> str:
    """去掉标题里自带的书名号，统一由展示 / 命名逻辑添加。"""
    return inline_text(value).strip("《》〈〉 ")


def html_attr(tag: str, name: str) -> Optional[str]:
    """从单个 HTML 标签里取属性值（属性顺序任意）。"""
    match = re.search(
        r'\b%s\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))' % re.escape(name),
        tag, re.I)
    if not match:
        return None
    value = match.group(2) or match.group(3) or match.group(4) or ""
    return html_mod.unescape(value)


def quote_query(value: str, encoding: str = "utf-8") -> str:
    """按指定编码转义查询参数（晋江的搜索参数是 GBK）。"""
    try:
        raw = value.encode(encoding)
    except UnicodeEncodeError:
        raw = value.encode("utf-8")
    return urllib.parse.quote(raw)


def normalize(value: str) -> str:
    """比较书名 / 作者用：全半角归一、去空白与书名号、忽略大小写。"""
    value = unicodedata.normalize("NFKC", value or "")
    value = value.strip()
    value = re.sub(r"[《》〈〉「」『』“”‘’\"']", "", value)
    value = re.sub(r"\s+", "", value)
    return value.casefold()


def image_info(data: bytes) -> Optional[Tuple[str, int, int]]:
    """返回 (格式, 宽, 高)；不是图片时返回 None。"""
    fmt = sniff_image_ext(data)
    if fmt is None:
        return None
    if fmt == "gif" and len(data) >= 10:
        return fmt, (int.from_bytes(data[6:8], "little"),
                     int.from_bytes(data[8:10], "little"))
    if fmt == "webp" and len(data) >= 30:
        kind = data[12:16]
        if kind == b"VP8X":
            return fmt, (int.from_bytes(data[24:27], "little") + 1,
                         int.from_bytes(data[27:30], "little") + 1)
        if kind == b"VP8 ":
            return fmt, (int.from_bytes(data[26:28], "little") & 0x3FFF,
                         int.from_bytes(data[28:30], "little") & 0x3FFF)
        if kind == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return fmt, ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        return fmt, 0, 0
    size = image_size(data)
    if size:
        return fmt, size[0], size[1]
    return fmt, 0, 0


def url_extension(url: str) -> Optional[str]:
    """取 URL 里的图片扩展名（带点）。"""
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in IMAGE_EXTS:
        return "." + ext
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    for values in query.values():
        for value in values:
            extension = value.lower().lstrip(".")
            if extension in IMAGE_EXTS:
                return "." + extension
    return None


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Book:
    site_key: str
    site_label: str
    title: str
    author: str
    description: str = ""
    cover_urls: List[str] = field(default_factory=list)
    page_url: str = ""
    cover_referer: str = ""
    detail: Optional[Callable[["Book"], None]] = None

    def enrich(self) -> None:
        """补充搜索结果里没有的字段（目前只有晋江需要）。"""
        if self.detail is not None:
            self.detail(self)


# ---------------------------------------------------------------------------
# 站点解析
# ---------------------------------------------------------------------------

def parse_qidian(page: str) -> List[Book]:
    """解析 m.qidian.com 的搜索结果页。"""
    books: List[Book] = []
    for chunk in re.split(r'<div class="y-list__item"', page)[1:]:
        bid_match = re.search(r'data-bid="(\d+)"', chunk)
        title_match = re.search(
            r'<h2 class="_searchBookName[^"]*"[^>]*>(.*?)</h2>', chunk, re.S)
        if not (bid_match and title_match):
            continue
        desc_match = re.search(
            r'<p class="_searchBookDesc[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
        author_match = re.search(
            r'<p class="_searchBookAuthor[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
        bid = bid_match.group(1)
        books.append(Book(
            site_key="qidian",
            site_label="起点中文网",
            title=clean_title(title_match.group(1)),
            author=inline_text(author_match.group(1)) if author_match else "",
            description=text_of(desc_match.group(1)) if desc_match else "",
            # 起点封面 CDN 支持 600×800，180×240 是小图兜底
            cover_urls=[
                "https://bookcover.yuewen.com/qdbimg/349573/%s/600" % bid,
                "https://bookcover.yuewen.com/qdbimg/349573/%s/180" % bid,
            ],
            page_url="https://m.qidian.com/book/%s/" % bid,
            cover_referer="https://m.qidian.com/",
        ))
    return books


def parse_qidian_detail(book: Book, page: str) -> None:
    """从起点详情页补全简介（搜索结果的简介没有换行）。"""
    matched = re.search(
        r'<script id="vite-plugin-ssr_pageContext" type="application/json">'
        r'(.*?)</script>', page, re.S)
    if not matched:
        return
    try:
        description = json.loads(matched.group(1))[
            "pageContext"]["pageProps"]["pageData"]["bookInfo"]["desc"]
    except (TypeError, KeyError, ValueError):
        return
    if not isinstance(description, str):
        return
    description = text_of(description)
    if description:
        book.description = description


def parse_zongheng(data) -> List[Book]:
    """解析 search.zongheng.com/search/book 返回的 JSON。"""
    books: List[Book] = []
    seen = set()
    items = (((data or {}).get("data") or {}).get("datas") or {}).get("list") or []
    for item in items:
        bid = str(item.get("bookId") or "")
        if not bid or bid in seen:
            continue
        seen.add(bid)
        cover = (item.get("coverUrl") or "").strip()
        if cover.startswith("//"):
            cover_url = "https:" + cover
        elif cover.startswith("http"):
            cover_url = cover
        elif cover:
            cover_url = "https://static.zongheng.com/upload" + cover
        else:
            cover_url = ""
        books.append(Book(
            site_key="zongheng",
            site_label="纵横中文网",
            title=clean_title(item.get("name") or ""),
            author=inline_text(item.get("authorName") or ""),
            description=text_of(item.get("description") or ""),
            cover_urls=[cover_url] if cover_url else [],
            page_url="https://www.zongheng.com/detail/%s" % bid,
            cover_referer="https://www.zongheng.com/",
        ))
    return books


def parse_17k(page: str) -> List[Book]:
    """解析 search.17k.com 的搜索结果页。"""
    books: List[Book] = []
    for chunk in re.split(r'<div class="textlist"', page)[1:]:
        bid_match = re.search(r'//www\.17k\.com/book/(\d+)\.html', chunk)
        title_match = re.search(r"<dt>\s*<a[^>]*>(.*?)</a>", chunk, re.S)
        if not (bid_match and title_match):
            continue
        author_match = re.search(
            r'class="ls">\s*作者：\s*<a[^>]*>(.*?)</a>', chunk, re.S)
        desc_match = re.search(
            r"<strong>简介：</strong>\s*<p>\s*<a[^>]*>(.*?)</a>", chunk, re.S)
        img_match = re.search(r'<img\s+src="([^"]+)"', chunk)
        bid = bid_match.group(1)

        cover_urls: List[str] = []
        if img_match:
            original = html_mod.unescape(img_match.group(1))
            if original.startswith("//"):
                original = "https:" + original
            # 17K 的封面按尺寸分目录，600x800 是大图
            big = re.sub(r"/(\d+x\d+)/", "/600x800/", original)
            big = re.sub(r"-(\d+x\d+)(?=$|[?&])", "-600x800", big)
            if big != original:
                cover_urls.append(big)
            cover_urls.append(original)

        books.append(Book(
            site_key="17k",
            site_label="17K小说网",
            title=clean_title(title_match.group(1)),
            author=inline_text(author_match.group(1)) if author_match else "",
            description=text_of(desc_match.group(1)) if desc_match else "",
            cover_urls=cover_urls,
            page_url="https://www.17k.com/book/%s.html" % bid,
            cover_referer="https://www.17k.com/",
        ))
    return books


def parse_jjwxc(page: str) -> List[Book]:
    """解析晋江搜索结果页（调用方已按 GBK 解码）。"""
    books: List[Book] = []
    for chunk in re.split(r'<h3 class="title">', page)[1:]:
        id_match = re.search(r"onebook\.php\?novelid=(\d+)", chunk)
        title_match = re.search(r">(.*?)</a>", chunk, re.S)
        if not (id_match and title_match):
            continue
        author_match = re.search(
            r"作者：\s*<a[^>]*>\s*(?:<span[^>]*>)?(.*?)(?:</span>)?\s*</a>",
            chunk, re.S)
        intro_match = re.search(r'<div class="intro">(.*?)</div>', chunk, re.S)
        novel_id = id_match.group(1)
        books.append(Book(
            site_key="jjwxc",
            site_label="晋江文学城",
            title=clean_title(title_match.group(1)),
            author=inline_text(author_match.group(1)) if author_match else "",
            description=text_of(intro_match.group(1)) if intro_match else "",
            page_url="https://www.jjwxc.net/onebook.php?novelid=%s" % novel_id,
            cover_referer="https://www.jjwxc.net/",
        ))
    return books


def parse_jjwxc_detail(book: Book, page: str) -> None:
    """从晋江书籍详情页补全封面、简介和作者。"""
    # 封面有 _src（novelimage.php 动态图）和 src（静态缩略图）两个地址，
    # 分辨率因书而异，统一交给 fetch_cover 取最大的一张
    cover_tag = re.search(r'<img[^>]*class="noveldefaultimage"[^>]*>', page,
                          re.I | re.S)
    if cover_tag:
        candidates: List[str] = []
        for attribute in ("_src", "src"):
            cover = html_attr(cover_tag.group(0), attribute)
            if cover:
                if cover.startswith("//"):
                    cover = "https:" + cover
                candidates.append(cover)
        for cover in reversed(candidates):
            if cover not in book.cover_urls:
                book.cover_urls.insert(0, cover)

    intro_match = re.search(r'<div id="novelintro"[^>]*>(.*?)</div>', page, re.S)
    if intro_match:
        description = text_of(intro_match.group(1))
        if description:
            book.description = description

    if not book.author:
        author_match = re.search(
            r'oneauthor\.php\?authorid=\d+"[^>]*>\s*(?:<span[^>]*>)?'
            r'(.*?)(?:</span>)?\s*</a>', page, re.S)
        if author_match:
            book.author = inline_text(author_match.group(1))


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class Provider:
    key = ""
    label = ""

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def search(self, keyword: str) -> List[Book]:
        raise NotImplementedError


class QidianProvider(Provider):
    key = "qidian"
    label = "起点中文网"

    def search(self, keyword: str) -> List[Book]:
        url = "https://m.qidian.com/soushu/%s.html" % urllib.parse.quote(keyword)
        resp = self.client.get(url, referer="https://m.qidian.com/",
                               ua=UA_MOBILE)
        if resp.status != 200:
            raise FetchError("起点搜索返回 HTTP %d" % resp.status)
        books = parse_qidian(decode_body(resp))
        for book in books:
            book.detail = self._detail_filler(book.page_url)
        return books

    def _detail_filler(self, page_url: str) -> Callable[[Book], None]:
        def fill(book: Book) -> None:
            resp = self.client.get(page_url, referer="https://m.qidian.com/",
                                   ua=UA_MOBILE)
            if resp.status != 200:
                return
            parse_qidian_detail(book, decode_body(resp))
        return fill


class ZonghengProvider(Provider):
    key = "zongheng"
    label = "纵横中文网"

    def search(self, keyword: str) -> List[Book]:
        books: List[Book] = []
        seen = set()
        for huayu in (0, 1):        # 1 = 纵横女生网（花语）
            url = ("https://search.zongheng.com/search/book?keyword=%s"
                   "&sort=&pageNo=1&pageNum=30&isFromHuayu=%d"
                   % (urllib.parse.quote(keyword), huayu))
            resp = self.client.get(
                url, referer="https://search.zongheng.com/s?keyword=%s"
                             % urllib.parse.quote(keyword))
            if resp.status != 200:
                continue
            try:
                data = json.loads(decode_body(resp))
            except ValueError:
                continue
            for book in parse_zongheng(data):
                # 女生网的搜索结果里会重复出现主站的书
                if book.page_url in seen:
                    continue
                seen.add(book.page_url)
                books.append(book)
        return books


class SeventeenKProvider(Provider):
    key = "17k"
    label = "17K小说网"

    def search(self, keyword: str) -> List[Book]:
        url = ("https://search.17k.com/search.xhtml?cKey=%s"
               % urllib.parse.quote(keyword))
        resp = self.client.get(url, referer="https://www.17k.com/")
        if resp.status != 200:
            raise FetchError("17K 搜索返回 HTTP %d" % resp.status)
        return parse_17k(decode_body(resp))


class JjwxcProvider(Provider):
    key = "jjwxc"
    label = "晋江文学城"

    def search(self, keyword: str) -> List[Book]:
        # 晋江的搜索参数按 GBK 编码
        url = ("https://www.jjwxc.net/search.php?kw=%s&t=1"
               % quote_query(keyword, "gb18030"))
        resp = self.client.get(url, referer="https://www.jjwxc.net/")
        if resp.status != 200:
            raise FetchError("晋江搜索返回 HTTP %d" % resp.status)
        books = parse_jjwxc(resp.content.decode("gb18030", "replace"))
        for book in books:
            novel_id = book.page_url.rsplit("=", 1)[-1]
            book.detail = self._detail_filler(novel_id)
        return books

    def _detail_filler(self, novel_id: str) -> Callable[[Book], None]:
        def fill(book: Book) -> None:
            url = "https://www.jjwxc.net/onebook.php?novelid=%s" % novel_id
            resp = self.client.get(url, referer="https://www.jjwxc.net/")
            if resp.status != 200:
                return
            parse_jjwxc_detail(book, resp.content.decode("gb18030", "replace"))
        return fill


PROVIDERS: Dict[str, Callable[[HttpClient], Provider]] = {
    "qidian": QidianProvider,
    "zongheng": ZonghengProvider,
    "17k": SeventeenKProvider,
    "jjwxc": JjwxcProvider,
}
SITE_LABELS: Dict[str, str] = {key: cls.label for key, cls in PROVIDERS.items()}


# ---------------------------------------------------------------------------
# 搜索、选择与下载
# ---------------------------------------------------------------------------

def search_sites(keyword: str, site_keys: Sequence[str], client: HttpClient,
                 verbose: bool = False) -> Tuple[List[Book], List[str]]:
    """并发搜索各站点，返回 (结果, 错误信息)。"""
    books: List[Book] = []
    errors: List[str] = []

    def run(key: str):
        provider = PROVIDERS[key](client)
        try:
            return key, provider.search(keyword), None
        except FetchError as error:
            return key, [], "%s: %s" % (provider.label, error)
        except Exception as error:      # 单个站点出错不影响其它站点
            return key, [], "%s: %s: %s" % (provider.label,
                                            type(error).__name__, error)

    workers = max(1, min(len(site_keys), 4))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run, key) for key in site_keys]
        for future in concurrent.futures.as_completed(futures):
            key, found, error = future.result()
            if error:
                errors.append(error)
                if verbose:
                    print("提示: %s" % error, file=sys.stderr)
            if found and verbose:
                print("提示: %s 搜到 %d 条结果"
                      % (SITE_LABELS[key], len(found)), file=sys.stderr)
            books.extend(found)
    return books, errors


def is_related(wanted: str, title: str) -> bool:
    """判断搜索结果是否与查询书名相关（用来过滤站点的推荐位）。"""
    if not wanted or not title:
        return False
    if wanted in title or title in wanted:
        return True
    return difflib.SequenceMatcher(None, wanted, title).ratio() >= 0.6


def site_priority(book: Book) -> int:
    order = list(PROVIDERS)
    return order.index(book.site_key) if book.site_key in order else len(order)


def select_book(title: str, author: Optional[str], books: List[Book],
                auto_yes: bool = False, pick: Optional[int] = None,
                interactive: Optional[bool] = None) -> Optional[Book]:
    """按书名 / 作者选择；完全匹配直接返回，否则让用户确认或选择。

    返回 ``None`` 表示跳过。``interactive=None`` 时按 stdin 是否为终端判断。
    """
    wanted_title = normalize(title)
    wanted_author = normalize(author) if author else ""

    exact_title = [book for book in books
                   if normalize(book.title) == wanted_title]
    matched = [book for book in exact_title
               if not wanted_author or normalize(book.author) == wanted_author]

    if matched:
        # 同一本书在多个站点都有时按站点优先级取一个，视为完全匹配
        distinct = {(normalize(book.title), normalize(book.author))
                    for book in matched}
        if len(distinct) == 1:
            return min(matched, key=site_priority)

    if not exact_title:
        pool = [book for book in books
                if is_related(wanted_title, normalize(book.title))]
    else:
        pool = exact_title

    def score(book: Book):
        normalized_title = normalize(book.title)
        return (
            0 if normalized_title == wanted_title else 1,
            0 if wanted_author and normalize(book.author) == wanted_author else 1,
            0 if normalized_title.startswith(wanted_title) else 1,
            site_priority(book),
        )

    pool = sorted(pool, key=score)[:20]

    if not pool:
        print("!!! 未找到与“%s”相关的作品。" % title, file=sys.stderr)
        return None

    if pick is not None:
        if not 1 <= pick <= len(pool):
            print("!!! --pick 超出范围（1-%d）。" % len(pool), file=sys.stderr)
            return None
        return pool[pick - 1]

    if auto_yes:
        return pool[0]

    print("找到以下结果：" if len(pool) == 1 else "找到多个可能的结果：")
    if wanted_author and exact_title and not matched:
        print("    （没有找到作者为“%s”的《%s》，以下为同名作品）"
              % (author, title))
    for index, book in enumerate(pool, 1):
        print("  %2d. 《%s》作者：%s    〔%s〕"
              % (index, book.title, book.author or "未知", book.site_label))
    print("   0. 跳过")

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print("提示: 当前不是交互终端，请使用 --pick 序号 或 --yes 自动选择。",
              file=sys.stderr)
        return None

    while True:
        try:
            answer = input("请选择序号（0=跳过，回车默认 1）：").strip()
        except EOFError:
            print()
            return None
        if answer in ("q", "Q", "quit", "exit"):
            raise KeyboardInterrupt
        if answer == "":
            answer = "1"
        if not answer.isdigit():
            print("请输入数字序号。")
            continue
        choice = int(answer)
        if choice == 0:
            print("已跳过。")
            return None
        if 1 <= choice <= len(pool):
            return pool[choice - 1]
        print("请输入 1-%d 之间的序号。" % len(pool))


def fetch_cover(book: Book, client: HttpClient,
                verbose: bool = False) -> Optional[Tuple[bytes, str, int, int]]:
    """下载所有候选封面，返回分辨率最高的一张。"""
    best: Optional[Tuple[bytes, str, int, int]] = None
    best_area = -1
    for url in book.cover_urls:
        try:
            resp = client.get(url, referer=book.cover_referer or book.page_url,
                              binary=True)
        except FetchError as error:
            if verbose:
                print("提示: 封面下载失败: %s — %s" % (url, error),
                      file=sys.stderr)
            continue
        if resp.status != 200 or not resp.content:
            continue
        info = image_info(resp.content)
        if info is None:
            if verbose:
                print("提示: 不是图片: %s" % url, file=sys.stderr)
            continue
        fmt, width, height = info
        if width and height and (width < 80 or height < 80):
            if verbose:
                print("提示: 跳过占位图 %d×%d: %s" % (width, height, url),
                      file=sys.stderr)
            continue
        area = width * height if width and height else len(resp.content)
        if area > best_area:
            extension = url_extension(url) or ("." + fmt)
            best = (resp.content, extension, width, height)
            best_area = area
    return best


def safe_base_name(title: str, author: str) -> str:
    """生成“《书名》作者：xxx”形式的文件名（保留中文，替换斜杠）。"""
    return bookcover_base_name(title, author)


def write_file(path: str, data: bytes, force: bool = False) -> bool:
    if os.path.exists(path) and not force:
        print("提示: 已存在，跳过: %s" % path)
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def download(book: Book, client: HttpClient, directory: str,
             want_cover: bool = True, want_desc: bool = True,
             force: bool = False, verbose: bool = False) -> bool:
    """把封面和简介写进目录，返回是否全部成功。"""
    os.makedirs(directory, exist_ok=True)
    base = safe_base_name(book.title, book.author)
    ok = True

    if want_cover:
        result = fetch_cover(book, client, verbose)
        if result is None:
            print("!!! 没有获取到封面。", file=sys.stderr)
            ok = False
        else:
            data, extension, width, height = result
            path = os.path.join(directory, base + extension)
            if write_file(path, data, force):
                size = "（%d×%d）" % (width, height) if width and height else ""
                print("    封面: %s%s" % (path, size))

    if want_desc:
        if not book.description:
            print("!!! 没有获取到简介。", file=sys.stderr)
            ok = False
        else:
            path = os.path.join(directory, base + ".desc")
            text = (book.description.strip() + "\n").encode("utf-8")
            if write_file(path, text, force):
                print("    简介: %s" % path)

    return ok
