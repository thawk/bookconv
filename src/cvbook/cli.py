"""命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
from typing import List, Optional

from . import __version__, inputs
from .engines import convert_calibre, convert_pandoc
from .epub import build_epub
from .frontmatter import NoFrontMatter, read_frontmatter
from .htmlutil import paragraphs
from .images import MEDIA_TYPES, EpubImage, ImageStore, convert_image
from .metadata import find_cover, resolve_meta
from .models import BookMeta
from .styles import StyleError
from .styles import resolve as resolve_style

EPILOG = """\
样式:
  默认样式内置在包里，想改就复制一份再改，例如：
    1) 全局默认：~/.config/cvbook/style.css（存在时自动使用）
    2) 单次指定：cvbook -s my-style.css 某书.md
    3) 只追加：  cvbook --extra-style fix.css 某书.md
  可用的 CSS 钩子见 README（.page / .cover / .titlepage / .intro / .chapter ...）。

示例:
  cvbook 某书.md                 # 内建引擎 + 默认样式
  cvbook -s my-style.css 某书.md
  cvbook -i txt 某书.txt         # 强制按 txt 解析
  cvbook -m calibre 某书.md      # 用 calibre 兜底（此时 --style 无效）
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cvbook",
        description="把 Markdown / 纯文本小说转换成 EPUB，样式可定制。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version="cvbook %s" % __version__)
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="输出更多日志")
    parser.add_argument("-m", "--method", choices=("native", "calibre", "pandoc"),
                        default="native",
                        help="转换引擎：native 为内建实现（默认），"
                             "calibre/pandoc 兜底但不支持 --style")
    parser.add_argument("-i", "--input", choices=inputs.names(), default=None,
                        metavar="FORMAT",
                        help="输入格式，默认按扩展名自动识别（%s）"
                             % " / ".join(inputs.names()))
    parser.add_argument("-s", "--style", metavar="FILE",
                        help="自定义 CSS，替换内置默认样式")
    parser.add_argument("--extra-style", metavar="FILE", action="append",
                        default=[], help="追加 CSS（可重复）")
    parser.add_argument("--lang", default="zh", help="书籍语言，默认 zh")
    parser.add_argument("--no-cover", action="store_true", help="不生成封面页")
    parser.add_argument("--no-titlepage", action="store_true",
                        help="不生成扉页")
    parser.add_argument("--no-intro", action="store_true", help="不生成简介页")
    parser.add_argument("--intro-title", default="简介",
                        help="简介页标题，默认“简介”")
    parser.add_argument("--keep-indent", action="store_true",
                        help="保留段落开头的全角空格（默认去掉，交给 CSS）")
    parser.add_argument("--chapter-pattern", default="", metavar="REGEX",
                        help="txt 章节标题正则（默认识别 第N章/节/回/卷 等）")
    parser.add_argument("files", nargs="+", metavar="<filename>")
    return parser


def load_cover(path: str) -> Optional[EpubImage]:
    """读取同名封面图，webp 尽量转成 png。"""
    cover = find_cover(path)
    if cover is None:
        return None

    try:
        with open(cover, "rb") as f:
            data = f.read()
    except OSError as error:
        print("!!! 读取封面失败 %s: %s" % (cover, error), file=sys.stderr)
        return None

    ext = os.path.splitext(cover)[1].lstrip(".").lower()
    if ext == "webp":
        converted = convert_image(data, cover, "png")
        if converted is not None:
            data, ext = converted, "png"

    media_type = MEDIA_TYPES.get(ext)
    if media_type is None:
        print("!!! 不支持的封面格式: %s" % cover, file=sys.stderr)
        return None

    return EpubImage(path="images/cover." + ext, media_type=media_type, data=data)


def make_body_copy(path: str, body: bytes) -> Optional[str]:
    """把去掉 frontmatter 的正文写到源文件同目录（保住插图的相对路径）。"""
    src_dir = os.path.dirname(os.path.abspath(path))
    ext = os.path.splitext(path)[1].lstrip(".") or "md"
    suffix = "." + ext

    try:
        fd, temp = tempfile.mkstemp(prefix=".cvbook-body.", suffix=suffix,
                                    dir=src_dir)
    except OSError:
        print("!!! 无法在 '%s' 中创建临时文件，改用临时目录"
              "（相对图片链接可能失效）" % src_dir, file=sys.stderr)
        fd, temp = tempfile.mkstemp(prefix=".cvbook-body.", suffix=suffix)

    with os.fdopen(fd, "wb") as f:
        f.write(body)
    return temp


def convert_native(path: str, source: inputs.SourceFile, fmt: inputs.InputFormat,
                   meta: BookMeta, out: str, args) -> bool:
    images = ImageStore()
    options = inputs.ParseOptions(keep_indent=args.keep_indent,
                                  chapter_pattern=args.chapter_pattern)
    chapters = fmt.parse(source, images=images, options=options)
    if not chapters:
        print("!!! 没有解析出任何内容: %s" % path, file=sys.stderr)
        return False

    try:
        style = resolve_style(args.style, args.extra_style)
    except StyleError as error:
        print("!!! %s" % error, file=sys.stderr)
        return False

    if args.verbose:
        print("输入格式: %s，%d 页；样式: %s"
              % (fmt.name, len(chapters), ", ".join(style.sources)),
              file=sys.stderr)

    cover = None if args.no_cover else load_cover(path)
    intro_html = "" if args.no_intro else paragraphs(meta.comments,
                                                    args.keep_indent)

    try:
        build_epub(out, meta, chapters, css=style.css, images=images.items,
                   cover=cover, lang=args.lang,
                   include_titlepage=not args.no_titlepage,
                   include_intro=not args.no_intro,
                   intro_title=args.intro_title, intro_html=intro_html,
                   verbose=args.verbose)
    except Exception as error:          # ebooklib / lxml 的异常
        print("!!! 生成 EPUB 失败: %s" % error, file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return False

    print("生成: %s（%d 页）" % (out, len(chapters)))
    return True


def convert_legacy(path: str, body: bytes, meta: BookMeta, out: str, args,
                   has_frontmatter: bool) -> bool:
    """calibre / pandoc 引擎，需要把正文落到临时文件。"""
    if args.style or args.extra_style:
        print("!!! --style / --extra-style 只对内建引擎（-m native）生效，"
              "已忽略", file=sys.stderr)

    source = path
    temp = None
    if has_frontmatter:
        temp = make_body_copy(path, body)
        if temp is None:
            return False
        source = temp

    try:
        cover = find_cover(path)
        if args.method == "pandoc":
            return convert_pandoc(source, out, meta, cover, args.verbose)
        return convert_calibre(source, out, meta, cover, args.verbose)
    finally:
        if temp is not None:
            try:
                os.unlink(temp)
            except OSError:
                pass


def convert_one(path: str, args) -> bool:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as error:
        print("!!! 读取 '%s' 失败: %s" % (path, error), file=sys.stderr)
        return False

    meta = BookMeta()
    body = raw
    has_frontmatter = False
    try:
        meta, body = read_frontmatter(raw)
        has_frontmatter = True
    except NoFrontMatter:
        pass

    meta = resolve_meta(path, meta)
    if not meta.complete:
        print("!!! 无法确定书名/作者: %s" % path, file=sys.stderr)
        print("    可在文件头部加 frontmatter（title / authors），"
              "或把文件命名为《书名》作者：xxx.md", file=sys.stderr)
        return False

    source = inputs.SourceFile(path, body)
    if args.input:
        fmt = inputs.get(args.input)
        if fmt is None:
            print("!!! 未知输入格式 '%s'（可选: %s）"
                  % (args.input, ", ".join(inputs.names())), file=sys.stderr)
            return False
        if not fmt.matches(source):
            print("!!! '%s' 看起来不是 %s 格式，仍按 %s 解析"
                  % (path, fmt.name, fmt.name), file=sys.stderr)
    else:
        fmt = inputs.detect(source)
        if fmt is None:
            fmt = inputs.get(inputs.DEFAULT_FORMAT)
            if args.verbose:
                print("未识别扩展名，按 %s 解析: %s" % (fmt.name, path),
                      file=sys.stderr)

    out = os.path.basename(os.path.splitext(path)[0] + ".epub")

    if args.method == "native":
        return convert_native(path, source, fmt, meta, out, args)
    return convert_legacy(path, body, meta, out, args, has_frontmatter)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    failed: List[str] = []
    try:
        for path in args.files:
            if not convert_one(path, args):
                failed.append(path)
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130

    if failed:
        print("!!! %d 个文件转换失败: %s"
              % (len(failed), ", ".join(failed)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
