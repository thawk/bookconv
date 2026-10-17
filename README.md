# cvbook

把 Markdown / 纯文本小说转换成 EPUB，不依赖 calibre 或 pandoc：EPUB 用
[ebooklib](https://github.com/aerkalov/ebooklib) 生成，Markdown 用
[python-markdown](https://python-markdown.github.io/) 解析。

- 书名、作者、简介优先取文件头部的 YAML frontmatter，缺的字段回退到文件名（`《书名》作者：xxx.md`）
- frontmatter 会自动从正文里剥离，不会再混进正文
- 输入格式是插件：目前有 `markdown` 和 `txt`，以后可以加别的
- 样式可定制：封面页 / 扉页 / 目录页 / 简介页 / 章节标题 / 各级标题 / 正文各有一段 CSS 钩子

## 依赖（一次性，装在项目里）

依赖装在项目自己的 `.venv` 里，**不需要装到 dotfiles，也不影响系统 Python**：

```bash
cd ~/Downloads/book/new/cvbook
python3 -m venv .venv
.venv/bin/pip install -e .
```

只有 `ebooklib` 和 `markdown`（`ebooklib` 会带上 `lxml`）。不想建 venv 也行：把这两个包装到
系统 Python，然后 `PYTHONPATH=src python3 -m cvbook 某书.md`。

## 使用

项目根目录的 `./cvbook` 会自动使用 `.venv` 里的解释器，所以直接跑就行：

```bash
./cvbook 某书.md                    # 默认样式
./cvbook -s my-style.css 某书.md    # 自定义样式（整体替换）
./cvbook --extra-style fix.css 某书.md
./cvbook -i txt 某书.txt            # 强制按 txt 解析
./cvbook -m calibre 某书.md         # 用 calibre 兜底

# 多个文件
./cvbook 卷一.md 卷二.md            # 每个文件各生成一个 epub
./cvbook --merge 卷一.md 卷二.md    # 按命令行顺序合并成一本
./cvbook --merge -o 全本.epub 卷一.md 卷二.md
```

合并成一本时：各文件的 frontmatter 会被剥掉，书名/作者/简介取第一个有值的文件
（一般只需要给第一个文件写 frontmatter）；章节顺序就是命令行顺序；只支持内建引擎。

从别的目录调用：`~/Downloads/book/new/cvbook/cvbook 某书.md`。
想让 `cvbook` 变成 PATH 里的命令（可选），`install -m 755 contrib/cvbook-shim.sh ~/.dotfiles/util/bin/cvbook`。

| 选项 | 说明 |
| --- | --- |
| `-m, --method` | `native`（默认，内建实现）/ `calibre` / `pandoc` |
| `-i, --input` | 输入格式 `markdown` / `txt`，默认按扩展名识别 |
| `--merge` | 把多个输入文件合并成一本书 |
| `-o, --output FILE` | 输出文件名（默认同源文件名；合并时用第一个文件的名字） |
| `--cover FILE` | 指定封面图（默认找与源文件同名的图片） |
| `-s, --style FILE` | 用该 CSS 替换内置默认样式 |
| `--extra-style FILE` | 在最终样式后追加 CSS，可重复 |
| `--lang` | 书籍语言，默认 `zh` |
| `--no-cover` / `--no-titlepage` / `--no-intro` | 不生成对应页面 |
| `--intro-title` | 简介页标题，默认“简介” |
| `--keep-indent` | 保留段落开头的全角空格（默认去掉，交给 CSS `text-indent`） |
| `--chapter-pattern REGEX` | txt 的章标题正则 |
| `-v, --verbose` | 打印解析到的元数据、使用的样式等 |

输出文件写在**当前目录**，文件名与源文件同名（`某书.md` → `某书.epub`）。

## frontmatter

```markdown
---

title: 大明文魁

authors: 幸福来敲门

comments: |

　　紫禁城前九重门，百官簪缨南阙来。

　　帽插宫花朝天颜，金殿传胪名声传。

---

# 第0001章 少年和媳妇
```

- `title` → 书名
- `authors` / `author` / `creator` → 作者（可以是列表，也可以写 `张三 & 李四`）
- `comments` / `description` / `abstract` / `summary` → 简介（写进 `dc:description`，并生成简介页）
- 解析是容错的：字段之间有空行、块标量内容没缩进、CRLF、BOM 都能处理

## 样式

生成的页面结构大致是这样（每个页面一个 XHTML 文件）：

```html
<body>
  <div class="page cover first">
    <img class="cover-image" src="images/cover.jpg" alt="封面"/>
  </div>
</body>
```

```html
<div class="page titlepage">
  <h1 class="book-title">书名</h1><p class="book-author">作者</p>
</div>
<div class="page intro">
  <h2 class="intro-title">简介</h2><p>…</p><p>…</p>
</div>
<div class="page chapter">
  <h1 id="第0001章-少年和媳妇">第0001章 少年和媳妇</h1>
  <p>正文段落</p>
</div>
```

目录不排进正文：`nav.xhtml` 只作为 EPUB 的导航文档，阅读器从它生成目录面板（`toc.ncx`
给老阅读器），所以正文里不会多出一页目录。

| 选择器 | 对应 |
| --- | --- |
| `.page` | 每一页的容器（默认 `page-break-before: always`） |
| `.page.first` | 全书第一页（不分页） |
| `.cover` / `.cover .cover-image` | 封面页 / 封面图 |
| `.titlepage` / `.book-title` / `.book-author` | 扉页 / 书名 / 作者 |
| `nav` / `nav h2` / `nav ol` / `nav a` | 导航文档（个别阅读器会显示它，一般看不到） |
| `.intro` / `.intro-title` | 简介页 / 简介标题 |
| `.chapter` / `.chapter.first` | 正文页 |
| `.chapter h1` | 章节标题 |
| `.chapter h2`、`.chapter h3` | 小节标题 |
| `.chapter p` | 正文段落 |
| `.chapter img`、`.chapter blockquote`、`.chapter hr`、`.chapter pre`、`.chapter code`、`.chapter table` | 对应元素 |

样式来源的优先级：

1. `--style` 指定的文件
2. `~/.config/cvbook/style.css`（存在时自动使用，**整体替换**默认样式）
3. 包内 `src/cvbook/data/default.css`

追加的样式（按顺序）：`--extra-style`，然后是 `~/.config/cvbook/extra.css`
（存在时自动追加）。所以日常微调只要写 `extra.css`，不用抄整个默认样式。

`examples/style.css` 是一个“无衬线、无首行缩进、标题左对齐”的完整示例：

```bash
./cvbook -s examples/style.css 某书.md
```

## 输入插件

`src/cvbook/inputs/` 下每个插件都实现同一个接口：

```python
class MyInput(InputFormat):
    name = "myformat"
    extensions = ("my",)

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        ...
```

- `SourceFile.text` 已经按 UTF-8 / GB18030 解码；`base_dir` 是源文件目录
- 返回 `Chapter(title, html, level)`
  - `html` 是页面内片段：章节标题 `<h1>`、小节 `<h2>/<h3>`、段落 `<p>`
  - `level` 是目录层级（1 顶层，2 挂在上一个顶层下面）
- 段落缩进用 `htmlutil.strip_paragraph_indent`，插图用 `htmlutil.rewrite_images`
- 新插件在 `inputs/__init__.py` 的 `FORMATS` 里注册即可

### txt 插件

按行切分，默认识别的标题：

```
第一卷 风起          第1章 少年和媳妇
第二部 …             第十二回 …
第一篇 …             Chapter 12
```

有“卷/部/篇”时，章标题在目录里作为二级条目挂在卷下面；没有时章标题就是一级。
自定义正则：

```bash
./cvbook -i txt --chapter-pattern '^第[0-9]+章' 某书.txt
```

## Markdown 支持

用 python-markdown，启用了 `extra` + `toc` 扩展，所以常见写法都支持：

- 标题（自动生成唯一 id）、段落、`---` 分隔线、`>` 引用、围栏/缩进代码块
- 表格、脚注、定义列表、属性列表（`extra`）
- 列表、图片、链接、粗体/斜体、行内代码、原始 HTML

`--keep-indent` 会把行首全角空格换成字符实体再渲染，避免被 Markdown 的段落处理吃掉。

## 项目结构

```
cvbook/
├── cvbook                 直接运行的入口（自动使用 .venv）
├── pyproject.toml         依赖与打包信息
├── src/cvbook/
│   ├── cli.py             命令行入口
│   ├── epub.py            用 ebooklib 组装 EPUB（nav / NCX / 封面）
│   ├── frontmatter.py     YAML frontmatter 容错解析
│   ├── metadata.py        书名/作者兜底、封面查找
│   ├── models.py          BookMeta / Chapter
│   ├── images.py          插图去重与格式处理
│   ├── htmlutil.py        XHTML 小工具
│   ├── styles.py          样式加载与合并
│   ├── engines.py         calibre / pandoc 兜底
│   ├── data/default.css   内置样式
│   └── inputs/            输入插件（markdown、txt）
├── contrib/cvbook-shim.sh 可选：装进 PATH 用的转发脚本
├── examples/style.css     示例样式
└── tests/
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 备注

- 转换开始时会打印书名、作者、有没有封面，结束打印“生成完成”和用时
- 生成的 EPUB 是 EPUB 3（带 `nav` 导航文档），同时写了 `toc.ncx`，老阅读器也能用
- 目录只作为导航文档（`nav.xhtml` + `toc.ncx`），不进正文；点击阅读器的目录即可跳转
- `webp` 封面/插图会尝试用 `sips`（macOS 自带）或 ImageMagick 转成 png，失败则按原格式嵌入
- calibre / pandoc 引擎保留作兜底，它们不使用 `--style`，页面结构也不同
