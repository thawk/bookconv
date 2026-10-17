"""cvbook —— 把 Markdown 小说转换成 EPUB。

包结构::

    frontmatter.py  解析文件头部的 YAML frontmatter（容错实现）
    metadata.py     书名/作者兜底、封面查找
    images.py       插图去重、格式处理
    styles.py       内置默认 CSS 与自定义样式合并
    epub.py         用 ebooklib 组装 EPUB（封面页/扉页/目录页/简介页/正文页）
    engines.py      calibre / pandoc 备用引擎
    cli.py          命令行入口

依赖放在项目内的 ``.venv`` 里，不需要装到 dotfiles。
"""

__version__ = "0.2.0"
