"""cvbook —— 把 Markdown 小说转换成 EPUB。

包结构::

    frontmatter.py  解析文件头部的 YAML frontmatter（容错实现）
    metadata.py     书名/作者兜底、封面查找
    markdown_lite.py  Markdown 子集 -> XHTML（标准库实现）
    images.py       插图去重、格式处理
    styles.py       内置默认 CSS 与自定义样式合并
    epub.py         用标准库写 EPUB（封面页/扉页/简介页/正文页）
    engines.py      calibre / pandoc 备用引擎
    cli.py          命令行入口

整个包只用 Python 标准库，拷到任何地方都能直接跑（见项目根目录的 ``cvbook``）。
"""

__version__ = "0.2.0"
