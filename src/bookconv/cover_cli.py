"""``bookcover`` 命令行入口：按书名下载封面和简介。"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .cover import (PROVIDERS, DEFAULT_TIMEOUT, HttpClient, SITE_LABELS,
                    download, search_sites, select_book)

EPILOG = """\
站点:
  qidian=起点中文网  zongheng=纵横中文网  17k=17K小说网  jjwxc=晋江文学城

示例:
  bookcover 凡人修仙传
  bookcover 剑来 -a 烽火戏诸侯 -o ./books
  bookcover 雪中 -s zongheng --pick 1
  bookcover 撒野 -s jjwxc --cover-only

退出码:
  0  成功
  1  下载失败
  2  没有选中（需要交互选择、主动跳过或没有相关结果）
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookcover",
        description="从起点中文网等原创小说站点下载封面和简介。封面按"
                    "“《书名》作者：xxx.扩展名”命名，简介保存为同名 .desc"
                    "（UTF-8）。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version="bookcover %s" % __version__)
    parser.add_argument("title", metavar="<书名>", help="书名")
    parser.add_argument("-a", "--author", metavar="NAME",
                        help="作者（可选，提供后会优先精确匹配）")
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


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = build_parser().parse_args(argv)
    if args.cover_only and args.desc_only:
        print("!!! --cover-only 与 --desc-only 不能同时使用", file=sys.stderr)
        return 2

    client = HttpClient(timeout=args.timeout, proxy=args.proxy,
                        verbose=args.verbose)
    site_keys = args.site or list(PROVIDERS)
    query = args.title.strip().strip("《》〈〉「」").strip() or args.title

    print("正在搜索: %s%s"
          % (query, "（作者：%s）" % args.author if args.author else ""),
          flush=True)
    books, errors = search_sites(query, site_keys, client, args.verbose)
    if not books:
        for error in errors:
            print("!!! %s" % error, file=sys.stderr)
        print("!!! 所有站点都没有找到结果。", file=sys.stderr)
        return 1

    try:
        book = select_book(query, args.author, books,
                           auto_yes=args.yes, pick=args.pick)
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    if book is None:
        return 2

    print("选中: 《%s》作者：%s（%s）"
          % (book.title, book.author or "未知", book.site_label))
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


if __name__ == "__main__":
    sys.exit(main())
