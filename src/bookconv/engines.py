"""备用转换引擎：calibre 的 ebook-convert 和 pandoc。

内置引擎（native）才能用 --style 自定义样式；这两个引擎保留下来做兜底，
因为它们各自解析 markdown，样式由它们自己生成。
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from .images import convert_image
from .models import BookMeta

_DEFAULT_COVER_EXT = "jpg"


def _run(cmd, verbose: bool) -> bool:
    if verbose:
        print("+ " + " ".join(shlex.quote(part) for part in cmd),
              file=sys.stderr)
    try:
        returncode = subprocess.call(cmd)
    except FileNotFoundError:
        print("!!! 找不到命令 '%s'，请先安装" % cmd[0], file=sys.stderr)
        return False
    if returncode != 0:
        print("!!! '%s' 退出码 %d" % (cmd[0], returncode), file=sys.stderr)
        return False
    return True


def convert_calibre(src: str, out: str, meta: BookMeta,
                    cover: Optional[str], verbose: bool = False) -> bool:
    args = [
        "ebook-convert", src, out,
        "--level1-toc=//h:h1",
        "--level2-toc=//h:h2",
        "--level3-toc=//h:h3",
        "--disable-font-rescaling",
        "--epub-max-image-size=1200x1800",
    ]
    if meta.title:
        args.append("--title=%s" % meta.title)
    if meta.authors:
        args.append("--authors=%s" % meta.author_text)
    if cover:
        args.append("--cover=%s" % cover)
    if meta.comments:
        args.append("--comments=%s" % meta.comments)
    if verbose:
        args.append("--verbose")
    return _run(args, verbose)


def _yaml_scalar(value: str) -> str:
    value = (value.replace("\\", "\\\\")
                  .replace('"', '\\"')
                  .replace("\r", "")
                  .replace("\n", "\\n"))
    return '"%s"' % value


def _pandoc_metadata(meta: BookMeta, cover: Optional[str]) -> str:
    lines = ["title: %s" % _yaml_scalar(meta.title)]
    if meta.authors:
        lines.append("author:")
        lines.extend("  - %s" % _yaml_scalar(author) for author in meta.authors)
    if meta.comments:
        lines.append("description: %s" % _yaml_scalar(meta.comments))
    if cover:
        lines.append("cover-image: %s" % _yaml_scalar(cover))

    fd, path = tempfile.mkstemp(prefix="bookconv-meta.", suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _prepare_cover(cover: str, workdir: str) -> str:
    ext = os.path.splitext(cover)[1].lstrip(".").lower() or _DEFAULT_COVER_EXT
    target_ext = ext

    if ext == "webp":
        with open(cover, "rb") as f:
            data = f.read()
        converted = convert_image(data, cover, "png")
        if converted is not None:
            target = os.path.join(workdir, "cover.png")
            with open(target, "wb") as f:
                f.write(converted)
            return target
        print("!!! webp 封面转换失败，直接使用原文件", file=sys.stderr)

    target = os.path.join(workdir, "cover." + target_ext)
    shutil.copyfile(cover, target)
    return target


def convert_pandoc(src: str, out: str, meta: BookMeta,
                   cover: Optional[str], verbose: bool = False) -> bool:
    workdir = tempfile.mkdtemp(prefix="bookconv-pandoc.")
    try:
        cover_path = _prepare_cover(cover, workdir) if cover else None
        metadata = _pandoc_metadata(meta, cover_path)
        args = ["pandoc", "-o", out, "--metadata-file=%s" % metadata]
        if verbose:
            args.append("--verbose")
        args.append(src)
        return _run(args, verbose)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
