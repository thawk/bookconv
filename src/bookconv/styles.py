"""样式：内置默认 CSS，以及用户自定义样式的合并。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CSS_NAME = "default.css"

#: 样式目录：$XDG_CONFIG_HOME/bookconv（默认 ~/.config/bookconv）
CONFIG_DIR_RELATIVE = Path("bookconv")
#: 存在时替换内置默认样式
CONFIG_STYLE_NAME = "style.css"
#: 存在时追加到最终样式后面
CONFIG_EXTRA_NAME = "extra.css"


class StyleError(Exception):
    """样式文件读取失败。"""


@dataclass
class StyleSheet:
    css: str
    sources: List[str] = field(default_factory=list)


def default_css() -> str:
    return (DATA_DIR / DEFAULT_CSS_NAME).read_text(encoding="utf-8")


def config_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(config_home) / CONFIG_DIR_RELATIVE


def user_style_path() -> Optional[Path]:
    """~/.config/bookconv/style.css：存在时替换默认样式。"""
    path = config_dir() / CONFIG_STYLE_NAME
    return path if path.is_file() else None


def user_extra_path() -> Optional[Path]:
    """~/.config/bookconv/extra.css：存在时追加到最终样式后面。"""
    path = config_dir() / CONFIG_EXTRA_NAME
    return path if path.is_file() else None


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as error:
        raise StyleError("读取样式文件 %s 失败: %s" % (path, error))


def resolve(style: Optional[str] = None,
            extra: Iterable[str] = ()) -> StyleSheet:
    """决定最终使用的 CSS。

    优先级：--style 指定的文件 > ~/.config/bookconv/style.css > 内置默认样式，
    最后按顺序追加 --extra-style 与 ~/.config/bookconv/extra.css 的内容。
    """
    sources: List[str] = []

    if style:
        css = _read(style)
        sources.append(style)
    else:
        config_style = user_style_path()
        if config_style is not None:
            css = _read(str(config_style))
            sources.append(str(config_style))
        else:
            css = default_css()
            sources.append("内置默认样式")

    extra_paths = list(extra)
    config_extra = user_extra_path()
    if config_extra is not None:
        extra_paths.append(str(config_extra))

    for path in extra_paths:
        css += "\n\n/* --- %s --- */\n" % os.path.basename(path)
        css += _read(path)
        sources.append(path)

    return StyleSheet(css=css, sources=sources)
