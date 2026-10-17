"""命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from typing import List, Optional, Sequence, Tuple

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
    1) 全局默认：~/.config/cvbook/style.css（存在时自动使用，整体替换）
    2) 全局微调：~/.config/cvbook/extra.css（存在时自动追加）
    3) 单次指定：cvbook -s my-style.css 某书.md
    4) 只追加：  cvbook --extra-style fix.css 某书.md
  可用的 CSS 钩子见 README（.page / .cover / .titlepage / .intro / .chapter ...）。

示例:
  cvbook 某书.md                    # 单个文件
  cvbook 卷一.md 卷二.md            # 每个文件各生成一个 epub
  cvbook --merge 卷一.md 卷二.md    # 合并成一本（顺序按命令行）
  cvbook --merge -o 全本.epub 卷一.md 卷二.md
  cvbook -s my-style.css 某书.md
  cvbook -m calibre 某书.md         # 用 calibre 兜底（此时 --style 无效）
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
    parser.add_argument("--merge", action="store_true",
                        help="把多个输入文件按顺序合并成一本书")
    parser.add_argument("-o", "--output", metavar="FILE", default=None,
                        help="输出文件名（默认用源文件名；合并时用第一个文件的名字）")
    parser.add_argument("--cover", metavar="FILE", default=None,
                        help="指定封面图（默认找与源文件同名的图片）")
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


def default_output(path: str) -> str:
    """输出到当前目录，文件名与源文件同名。"""
    return os.path.basename(os.path.splitext(path)[0] + ".epub")


def load_cover(image_path: str) -> Optional[EpubImage]:
    """读取封面图，webp 尽量转成 png。"""
    try:
        with open(image_path, "rb") as f:
            data = f.read()
    except OSError as error:
        print("!!! 读取封面失败 %s: %s" % (image_path, error), file=sys.stderr)
        return None

    ext = os.path.splitext(image_path)[1].lstrip(".").lower()
    if ext == "webp":
        converted = convert_image(data, image_path, "png")
        if converted is not None:
            data, ext = converted, "png"

    media_type = MEDIA_TYPES.get(ext)
    if media_type is None:
        print("!!! 不支持的封面格式: %s" % image_path, file=sys.stderr)
        return None

    return EpubImage(path="images/cover." + ext, media_type=media_type, data=data)


def pick_cover_path(args, path: str) -> Optional[str]:
    """--cover 优先，否则找与源文件同名的图片；--no-cover 时不要封面。"""
    if args.no_cover:
        return None
    return args.cover or find_cover(path)


def announce_start(meta: BookMeta, cover_path: Optional[str],
                   merged_files: int = 0) -> None:
    prefix = "合并 %d 个文件 → " % merged_files if merged_files > 1 else ""
    print("开始生成: %s《%s》 作者: %s 封面: %s"
          % (prefix, meta.title, meta.author_text,
             "有" if cover_path else "无"))


def announce_done(meta: BookMeta, out: str, started: float,
                  chapters: Optional[int] = None) -> None:
    detail = "%d 章，" % chapters if chapters is not None else ""
    print("生成完成: 《%s》 → %s（%s用时 %.1f 秒）"
          % (meta.title, out, detail, time.time() - started))


def parse_options(args) -> inputs.ParseOptions:
    return inputs.ParseOptions(keep_indent=args.keep_indent,
                               chapter_pattern=args.chapter_pattern)


def select_format(source: inputs.SourceFile, args) -> Optional[inputs.InputFormat]:
    if args.input:
        fmt = inputs.get(args.input)
        if fmt is None:
            print("!!! 未知输入格式 '%s'（可选: %s）"
                  % (args.input, ", ".join(inputs.names())), file=sys.stderr)
            return None
        if not fmt.matches(source) and args.verbose:
            print("提示: '%s' 的扩展名不像是 %s，仍按 %s 解析"
                  % (source.path, fmt.name, fmt.name), file=sys.stderr)
        return fmt

    fmt = inputs.detect(source)
    if fmt is None:
        fmt = inputs.get(inputs.DEFAULT_FORMAT)
        if args.verbose:
            print("未识别扩展名，按 %s 解析: %s" % (fmt.name, source.path),
                  file=sys.stderr)
    return fmt


def read_source(path: str, args) -> Optional[Tuple]:
    """读取文件、剥掉 frontmatter、选好输入插件。

    返回 (source, fmt, meta, has_frontmatter)；失败返回 None。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as error:
        print("!!! 读取 '%s' 失败: %s" % (path, error), file=sys.stderr)
        return None

    meta = BookMeta()
    body = raw
    has_frontmatter = False
    try:
        meta, body = read_frontmatter(raw)
        has_frontmatter = True
    except NoFrontMatter:
        pass

    source = inputs.SourceFile(path, body)
    fmt = select_format(source, args)
    if fmt is None:
        return None
    return source, fmt, meta, has_frontmatter


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


def report_build_error(error: Exception, args) -> None:
    print("!!! 生成 EPUB 失败: %s" % error, file=sys.stderr)
    if args.verbose:
        traceback.print_exc()


def build_book(chapters, images: ImageStore, meta: BookMeta, out: str, args,
               style, cover: Optional[EpubImage], started: float) -> bool:
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
        report_build_error(error, args)
        return False

    announce_done(meta, out, started, len(chapters))
    return True


def convert_native(path: str, source: inputs.SourceFile,
                   fmt: inputs.InputFormat, meta: BookMeta, out: str,
                   args) -> bool:
    cover_path = pick_cover_path(args, path)
    cover = load_cover(cover_path) if cover_path else None
    announce_start(meta, cover_path)
    started = time.time()

    images = ImageStore()
    chapters = fmt.parse(source, images=images, options=parse_options(args))
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

    return build_book(chapters, images, meta, out, args, style, cover, started)


def convert_merged(paths: Sequence[str], args) -> bool:
    """把多个文件按顺序合并成一本书。"""
    if args.method != "native":
        print("!!! --merge 目前只支持内建引擎（-m native）", file=sys.stderr)
        return False

    loaded = []
    for path in paths:
        item = read_source(path, args)
        if item is None:
            return False
        loaded.append(item)

    meta = BookMeta()
    for _, _, item_meta, _ in loaded:
        meta.title = meta.title or item_meta.title
        meta.authors = meta.authors or item_meta.authors
        meta.comments = meta.comments or item_meta.comments
    meta = resolve_meta(paths[0], meta)
    if not meta.complete:
        print("!!! 无法确定书名/作者: %s" % ", ".join(paths), file=sys.stderr)
        print("    可在第一个文件头部加 frontmatter（title / authors），"
              "或把文件命名为《书名》作者：xxx.md", file=sys.stderr)
        return False

    cover_path = pick_cover_path(args, paths[0])
    cover = load_cover(cover_path) if cover_path else None
    announce_start(meta, cover_path, len(loaded))
    started = time.time()

    images = ImageStore()
    options = parse_options(args)
    chapters = []
    for source, fmt, _, _ in loaded:
        chapters.extend(fmt.parse(source, images=images, options=options))
    if not chapters:
        print("!!! 没有解析出任何内容", file=sys.stderr)
        return False

    try:
        style = resolve_style(args.style, args.extra_style)
    except StyleError as error:
        print("!!! %s" % error, file=sys.stderr)
        return False

    if args.verbose:
        print("合并 %d 个文件，共 %d 页；样式: %s"
              % (len(loaded), len(chapters), ", ".join(style.sources)),
              file=sys.stderr)

    out = args.output or default_output(paths[0])
    return build_book(chapters, images, meta, out, args, style, cover, started)


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

    cover = pick_cover_path(args, path)
    announce_start(meta, cover)
    started = time.time()

    try:
        if args.method == "pandoc":
            ok = convert_pandoc(source, out, meta, cover, args.verbose)
        else:
            ok = convert_calibre(source, out, meta, cover, args.verbose)
    finally:
        if temp is not None:
            try:
                os.unlink(temp)
            except OSError:
                pass

    if ok:
        announce_done(meta, out, started)
    return ok


def convert_one(path: str, args) -> bool:
    loaded = read_source(path, args)
    if loaded is None:
        return False
    source, fmt, meta, has_frontmatter = loaded

    meta = resolve_meta(path, meta)
    if not meta.complete:
        print("!!! 无法确定书名/作者: %s" % path, file=sys.stderr)
        print("    可在文件头部加 frontmatter（title / authors），"
              "或把文件命名为《书名》作者：xxx.md", file=sys.stderr)
        return False

    out = args.output or default_output(path)

    if args.method == "native":
        return convert_native(path, source, fmt, meta, out, args)
    return convert_legacy(path, source.raw, meta, out, args, has_frontmatter)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.merge:
        return 0 if convert_merged(args.files, args) else 1

    if args.output and len(args.files) > 1:
        print("!!! 一次转换多个文件时不能用 --output；想合并成一本请加 --merge",
              file=sys.stderr)
        return 2

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
