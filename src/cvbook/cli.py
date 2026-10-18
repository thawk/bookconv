"""命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import traceback
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from . import __version__, inputs
from .engines import convert_calibre, convert_pandoc
from .epub import build_epub
from .frontmatter import NoFrontMatter, read_frontmatter
from .htmlutil import paragraphs
from .images import (MEDIA_TYPES, EpubImage, ImageStore, convert_image,
                     image_size)
from .inputs.base import is_url
from .markdown_output import write_markdown
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
  cvbook 某书.txt                   # 纯文本（按章标题切）
  cvbook 某书.adoc                  # AsciiDoc
  cvbook 某书.chm                   # CHM（需要 7z 或 unar）
  cvbook 某书.epub                  # EPUB
  cvbook 某书目录/                   # 整本 HTML 目录
  cvbook https://example.com/book/  # 网页（抓入口页里的链接）
  cvbook -f md 某书.epub            # 输出 Markdown（默认仍然输出 EPUB）
  cvbook -f md -o 某书.md 某书.chm
  cvbook 卷一.md 卷二.md            # 每个文件各生成一个 epub
  cvbook --merge 卷一.md 卷二.md    # 合并成一本（顺序按命令行）
  cvbook --merge -o 全本.epub 卷一.md 卷二.md
  cvbook -s my-style.css 某书.md
  cvbook -m calibre 某书.md         # 用 calibre 兜底（此时 --style 无效）
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cvbook",
        description="把 Markdown / 纯文本 / AsciiDoc / HTML / EPUB / CHM "
                    "转换成 EPUB（或 Markdown），样式可定制。",
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
                        help="把多个输入（文件/目录/URL）按顺序合并成一本书")
    parser.add_argument("-f", "--format", "--output-format", dest="output_format",
                        choices=("epub", "md"), default="epub",
                        help="输出格式：epub（默认）或 md")
    parser.add_argument("--no-frontmatter", action="store_true",
                        help="md 输出不写 YAML frontmatter")
    parser.add_argument("-o", "--output", metavar="FILE", default=None,
                        help="输出文件名（默认用源文件名；合并时用第一个文件的名字）")
    parser.add_argument("--cover", metavar="FILE", default=None,
                        help="指定封面图（默认找同名图片/目录 cover；EPUB 用内嵌封面）")
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
    parser.add_argument("files", nargs="+", metavar="<source>")
    return parser


_INDEX_STEMS = {"index", "cover", "start", "toc", "mulu", "contents",
                "default", "home", "main", "tempbook"}


def default_output(path: str, output_format: str = "epub") -> str:
    """输出到当前目录，文件名与源文件/目录同名。"""
    suffix = ".md" if output_format == "md" else ".epub"
    if is_url(path):
        parsed = urlsplit(path)
        trailing = parsed.path.endswith("/") or not parsed.path
        clean = parsed.path.rstrip("/")
        name = os.path.basename(clean) or parsed.netloc or "book"
        stem = os.path.splitext(name)[0] or name
        if not trailing and stem.lower() in _INDEX_STEMS:
            parent = os.path.basename(os.path.dirname(clean))
            stem = parent or parsed.netloc or stem
    else:
        clean = path.rstrip(os.sep)
        name = os.path.basename(clean) or "book"
        stem = os.path.splitext(name)[0] or name
    candidate = (stem or "book") + suffix
    if (not is_url(path)
            and os.path.realpath(candidate) == os.path.realpath(path)):
        candidate = (stem or "book") + "-converted" + suffix
    return candidate


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


def load_input_cover(args, path: str, fmt: Optional[inputs.InputFormat],
                     source: Optional[inputs.SourceFile]):
    """返回 (封面文件路径, 封面图)。先找本地同名图，再用源文件内嵌封面。"""
    cover_path = pick_cover_path(args, path)
    if cover_path:
        return cover_path, load_cover(cover_path)
    if args.no_cover or fmt is None or source is None:
        return None, None
    try:
        cover = fmt.cover(source)
    except Exception as error:
        if args.verbose:
            print("提示: 读取内嵌封面失败: %s" % error, file=sys.stderr)
        return None, None
    return (None, cover) if cover is not None else (None, None)


def announce_start(meta: BookMeta, cover_path: Optional[str],
                   cover_image: Optional[EpubImage] = None,
                   merged_files: int = 0) -> None:
    prefix = "合并 %d 个文件 → " % merged_files if merged_files > 1 else ""
    cover_text = "无"
    size = None
    if cover_path or cover_image is not None:
        cover_text = "有"
        if cover_image is not None:
            size = image_size(cover_image.data)
            if size:
                cover_text = "有（%d×%d）" % size
    print("开始生成: %s《%s》 作者: %s 封面: %s"
          % (prefix, meta.title, meta.author_text or "无", cover_text),
          flush=True)


def announce_done(meta: BookMeta, out: str, started: float,
                  chapters: Optional[int] = None) -> None:
    detail = "%d 章，" % chapters if chapters is not None else ""
    print("    生成完成: 《%s》（%s用时 %.1f 秒）"
          % (meta.title, detail, time.time() - started))


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
        if source.is_url:
            print("!!! 无法从 URL 识别输入格式: %s" % source.path,
                  file=sys.stderr)
            return None
        if source.is_dir:
            print("!!! 目录里没有找到支持的输入文件: %s" % source.path,
                  file=sys.stderr)
            return None
        if source.binary:
            print("!!! 不支持的二进制格式: %s" % source.path, file=sys.stderr)
            return None
        fmt = inputs.get(inputs.DEFAULT_FORMAT)
        if args.verbose:
            print("未识别扩展名，按 %s 解析: %s" % (fmt.name, source.path),
                  file=sys.stderr)
    return fmt


def merge_meta(meta: BookMeta, extra: Optional[BookMeta]) -> BookMeta:
    if extra is None:
        return meta
    if not meta.title:
        meta.title = extra.title
    if not meta.authors:
        meta.authors = extra.authors
    if not meta.comments:
        meta.comments = extra.comments
    return meta


def read_source(path: str, args) -> Optional[Tuple]:
    """读取文件/目录/URL、剥掉 frontmatter、选好输入插件。

    返回 (source, fmt, meta, has_frontmatter)；失败返回 None。
    """
    meta = BookMeta()
    body = b""
    has_frontmatter = False

    if not (is_url(path) or os.path.isdir(path)):
        if not path.lower().endswith((".chm", ".epub")):
            # CHM/EPUB 由插件按路径读取，不需要整个读进内存
            try:
                with open(path, "rb") as f:
                    raw = f.read()
            except OSError as error:
                print("!!! 读取 '%s' 失败: %s" % (path, error),
                      file=sys.stderr)
                return None
            body = raw
            if b"\x00" not in raw[:4096]:   # 二进制（CHM 等）没有 frontmatter
                try:
                    meta, body = read_frontmatter(raw)
                    has_frontmatter = True
                except NoFrontMatter:
                    pass

    source = inputs.SourceFile(path, body)
    fmt = select_format(source, args)
    if fmt is None:
        return None

    if fmt.name == "epub":
        # EPUB 自带权威元数据，优先于文件名
        try:
            meta = merge_meta(meta, fmt.metadata(source))
        except Exception as error:
            if args.verbose:
                print("提示: 读取 EPUB 元数据失败: %s" % error, file=sys.stderr)
        meta = resolve_meta(path, meta)
    else:
        meta = resolve_meta(path, meta)
        if not meta.title or not meta.authors:
            try:
                meta = merge_meta(meta, fmt.metadata(source))
            except Exception as error:  # 元数据只是兜底，失败不影响正文转换
                if args.verbose:
                    print("提示: 读取书籍信息失败: %s" % error, file=sys.stderr)
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

    announce_done(meta, out, started,
                  len([chapter for chapter in chapters
                       if not getattr(chapter, "virtual", False)]))
    return True


def convert_native(path: str, source: inputs.SourceFile,
                   fmt: inputs.InputFormat, meta: BookMeta, out: str,
                   args) -> bool:
    cover_path, cover = load_input_cover(args, path, fmt, source)
    announce_start(meta, cover_path, cover)
    started = time.time()

    images = ImageStore()
    try:
        chapters = fmt.parse(source, images=images, options=parse_options(args))
    except inputs.InputError as error:
        print("!!! %s" % error, file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return False
    if not chapters:
        print("!!! 没有解析出任何内容: %s" % path, file=sys.stderr)
        return False

    if args.output_format == "md":
        if args.style or args.extra_style:
            print("!!! --style / --extra-style 只对 EPUB 输出生效，已忽略",
                  file=sys.stderr)
        try:
            write_markdown(out, meta, chapters, images, cover=cover,
                           include_frontmatter=not args.no_frontmatter,
                           verbose=args.verbose)
        except Exception as error:
            print("!!! 生成 Markdown 失败: %s" % error, file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            return False
        announce_done(meta, out, started, len(chapters))
        return True

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
        print("!!! 无法确定书名: %s" % ", ".join(paths), file=sys.stderr)
        print("    可在第一个文件头部加 frontmatter（title），"
              "或把文件命名为《书名》…", file=sys.stderr)
        return False

    first_source, first_fmt, _, _ = loaded[0]
    cover_path, cover = load_input_cover(args, paths[0], first_fmt,
                                         first_source)
    announce_start(meta, cover_path, cover, len(loaded))
    started = time.time()

    images = ImageStore()
    options = parse_options(args)
    chapters = []
    for source, fmt, _, _ in loaded:
        try:
            chapters.extend(fmt.parse(source, images=images, options=options))
        except inputs.InputError as error:
            print("!!! %s" % error, file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            return False
    if not chapters:
        print("!!! 没有解析出任何内容", file=sys.stderr)
        return False

    out = args.output or default_output(paths[0], args.output_format)
    out_real = os.path.realpath(out)
    collision = any(not is_url(item_path)
                    and os.path.realpath(item_path) == out_real
                    for item_path in paths)
    if collision:
        if args.output:
            print("!!! 输出文件不能与输入相同: %s" % out,
                  file=sys.stderr)
            return False
        stem, ext = os.path.splitext(out)
        out = stem + "-converted" + ext

    if args.output_format == "md":
        if args.style or args.extra_style:
            print("!!! --style / --extra-style 只对 EPUB 输出生效，已忽略",
                  file=sys.stderr)
        try:
            write_markdown(out, meta, chapters, images, cover=cover,
                           include_frontmatter=not args.no_frontmatter,
                           verbose=args.verbose)
        except Exception as error:
            print("!!! 生成 Markdown 失败: %s" % error, file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            return False
        announce_done(meta, out, started, len(chapters))
        return True

    try:
        style = resolve_style(args.style, args.extra_style)
    except StyleError as error:
        print("!!! %s" % error, file=sys.stderr)
        return False

    if args.verbose:
        print("合并 %d 个文件，共 %d 页；样式: %s"
              % (len(loaded), len(chapters), ", ".join(style.sources)),
              file=sys.stderr)

    return build_book(chapters, images, meta, out, args, style, cover, started)


def convert_legacy(path: str, body: bytes, meta: BookMeta, out: str, args,
                   has_frontmatter: bool) -> bool:
    """calibre / pandoc 引擎，需要把正文落到临时文件。"""
    if args.output_format != "epub":
        print("!!! Markdown 输出只支持内建引擎（-m native）", file=sys.stderr)
        return False
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
        print("!!! 无法确定书名: %s" % path, file=sys.stderr)
        print("    可在文件头部加 frontmatter（title），"
              "把文件命名为《书名》…，或给 HTML/CHM/EPUB 加书名", file=sys.stderr)
        return False

    out = args.output or default_output(path, args.output_format)
    if (args.output and not is_url(path)
            and os.path.realpath(out) == os.path.realpath(path)):
        print("!!! 输出文件不能与输入相同: %s" % out, file=sys.stderr)
        return False

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
