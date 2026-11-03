"""``bookcover`` 命令行入口：按书名或 bookconv 风格的文件名下载封面和简介。"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import __version__
from .cover import (PROVIDERS, DEFAULT_TIMEOUT, HttpClient, SITE_LABELS,
                    download, normalize, search_sites, select_book)
from .metadata import filename_author, filename_title

#: 出现在文件名末尾、可以安全去掉的输入扩展名
SOURCE_EXTS = ("md", "markdown", "txt", "text", "adoc", "asciidoc",
               "html", "htm", "xhtml", "epub", "chm")

EPILOG = """\
站点:
  qidian=起点中文网  zongheng=纵横中文网  17k=17K小说网  jjwxc=晋江文学城

示例:
  bookcover 凡人修仙传
  bookcover 剑来 -a 烽火戏诸侯 -o ./books
  bookcover "《剑来》作者：烽火戏诸侯.md"
  bookcover "《剑来》作者：烽火戏诸侯" "《雪中悍刀行》作者：烽火戏诸侯.md"
  bookcover 雪中 -s zongheng --pick 1
  bookcover 撒野 -s jjwxc --cover-only

退出码:
  0  成功
  1  下载失败
  2  没有选中（需要交互选择、主动跳过或没有相关结果；多个输入时任一本未选中）
"""


@dataclass(frozen=True)
class BookQuery:
    """一本书的查询条件（书名 + 可选作者）。"""

    title: str
    author: str = ""


def _source_stem(value: str) -> str:
    """取文件名主体：兼容 URL、目录和常见电子书扩展名。"""
    if value.lower().startswith(("http://", "https://")):
        value = urllib.parse.urlsplit(value).path
    name = os.path.basename(value.rstrip("/" + os.sep))
    stem, extension = os.path.splitext(name)
    if extension.lower().lstrip(".") in SOURCE_EXTS:
        return stem
    return name


def parse_query(value: str) -> BookQuery:
    """从书名或 bookconv 风格的文件名/字符串里解析书名和作者。

    ``bookconv`` 认得的文件名形如 ``《书名》作者：xxx.md``；普通书名
    （``凡人修仙传``）以及不带书名号的 ``剑来 作者：烽火戏诸侯.md``
    也能解析。解析不出书名时返回书名空串。
    """
    text = (value or "").strip()
    if not text:
        return BookQuery("")
    title = filename_title(text)
    author = filename_author(text)
    if title:
        return BookQuery(title, author)

    # 没有《书名》时，把去掉扩展名的部分当书名，并去掉“作者：xxx”
    title = _source_stem(text)
    if author:
        title = re.split(r"\s*作者[:：].*$", title, maxsplit=1)[0]
    title = title.strip().strip("《》〈〉「」『』\"'“”‘’ ").strip()
    return BookQuery(title, author)


def parse_queries(values: List[str],
                  author: Optional[str] = None) -> List[BookQuery]:
    """解析多个书名/文件名并去重，保持首次出现的顺序。

    完全相同的书名 + 作者会合并；同名但一方没写作者时，保留带作者的那条；
    同名不同作者视为不同的书，都保留。``author`` 给定时覆盖解析出的作者。
    """
    queries: List[BookQuery] = []
    by_title: Dict[str, List[int]] = {}
    seen = set()

    for value in values:
        query = parse_query(value)
        if not query.title:
            continue
        if author:
            query = BookQuery(query.title, author)

        title_key = normalize(query.title)
        author_key = normalize(query.author)
        key = (title_key, author_key)
        if key in seen:
            continue

        indexes = by_title.setdefault(title_key, [])
        merged = False
        for index in indexes:
            current = queries[index]
            if not current.author or not query.author:
                if not current.author and query.author:
                    queries[index] = BookQuery(current.title, query.author)
                    seen.add((title_key, author_key))
                merged = True
                break
        if merged:
            continue

        seen.add(key)
        indexes.append(len(queries))
        queries.append(query)

    return queries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookcover",
        description="从起点中文网等原创小说站点下载封面和简介。书名可以直接"
                    "给，也可以用 bookconv 认得的文件名/字符串（自动解析书名和"
                    "作者）。封面按“《书名》作者：xxx.扩展名”命名，简介保存为"
                    "同名 .desc（UTF-8）。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version="bookcover %s" % __version__)
    parser.add_argument("sources", nargs="+", metavar="<书名或文件名>",
                        help="书名，或 bookconv 风格的文件名/字符串"
                             "（如 《书名》作者：xxx.md）；可提供多个")
    parser.add_argument("-a", "--author", metavar="NAME",
                        help="作者（可选；提供时覆盖从文件名解析出的作者）")
    parser.add_argument("-o", "--output", metavar="DIR", default=".",
                        help="输出目录（默认当前目录）")
    parser.add_argument("-s", "--site", action="append", choices=sorted(PROVIDERS),
                        metavar="SITE",
                        help="只在这些站点搜索（%s），可重复指定（默认全部）"
                             % " / ".join("%s=%s" % (key, SITE_LABELS[key])
                                          for key in sorted(PROVIDERS)))
    parser.add_argument("--cover-only", action="store_true", help="只下载封面")
    parser.add_argument("--desc-only", action="store_true", help="只下载简介")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="有多个结果时自动选择第一个")
    parser.add_argument("--pick", type=int, metavar="N",
                        help="有多个结果时直接选择第 N 个（非交互）")
    parser.add_argument("-f", "--force", action="store_true",
                        help="覆盖已存在的文件")
    parser.add_argument("-t", "--timeout", type=float, default=DEFAULT_TIMEOUT,
                        metavar="SEC", help="单次请求超时秒数（默认 %(default)s）")
    parser.add_argument("--proxy", metavar="URL",
                        help="HTTP(S) 代理，如 http://127.0.0.1:7890")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="输出更多日志")
    return parser


def process_query(query: BookQuery, args, client: HttpClient,
                  site_keys: List[str], index: int = 1,
                  total: int = 1) -> int:
    """搜索并下载一本，返回 0 成功 / 1 失败 / 2 跳过 / 130 中断。"""
    prefix = "[%d/%d] " % (index, total) if total > 1 else ""
    print("%s正在搜索: %s%s"
          % (prefix, query.title,
             "（作者：%s）" % query.author if query.author else ""),
          flush=True)
    books, errors = search_sites(query.title, site_keys, client, args.verbose)
    if not books:
        for error in errors:
            print("!!! %s%s" % (prefix, error), file=sys.stderr)
        print("!!! %s所有站点都没有找到结果。" % prefix, file=sys.stderr)
        return 1

    try:
        book = select_book(query.title, query.author, books,
                           auto_yes=args.yes, pick=args.pick)
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    if book is None:
        return 2

    print("%s选中: 《%s》作者：%s（%s）"
          % (prefix, book.title, book.author or "未知", book.site_label))
    try:
        book.enrich()
    except Exception as error:          # 详情只是补充，失败不影响下载
        if args.verbose:
            print("提示: 获取详情失败: %s" % error, file=sys.stderr)

    try:
        ok = download(book, client, args.output,
                      want_cover=not args.desc_only,
                      want_desc=not args.cover_only,
                      force=args.force, verbose=args.verbose)
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    except OSError as error:
        print("!!! 写入文件失败: %s" % error, file=sys.stderr)
        return 1
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = build_parser().parse_args(argv)
    if args.cover_only and args.desc_only:
        print("!!! --cover-only 与 --desc-only 不能同时使用", file=sys.stderr)
        return 2

    queries = parse_queries(args.sources, args.author)
    if not queries:
        print("!!! 没有从输入里解析出书名。", file=sys.stderr)
        return 2

    client = HttpClient(timeout=args.timeout, proxy=args.proxy,
                        verbose=args.verbose)
    site_keys = args.site or list(PROVIDERS)

    statuses: List[int] = []
    for index, query in enumerate(queries, 1):
        status = process_query(query, args, client, site_keys,
                               index, len(queries))
        if status == 130:
            return 130
        statuses.append(status)

    if len(queries) > 1:
        print("完成: 成功 %d 本，失败 %d 本，跳过 %d 本。"
              % (statuses.count(0), statuses.count(1), statuses.count(2)))
    if 1 in statuses:
        return 1
    if 2 in statuses:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
