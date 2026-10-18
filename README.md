# bookconv

把 Markdown / 纯文本 / AsciiDoc / HTML / EPUB / CHM 转换成 EPUB，也可以把
任意输入输出成 Markdown（`-f md`）。不依赖 calibre 或 pandoc：EPUB 用
[ebooklib](https://github.com/aerkalov/ebooklib) 生成和读取，Markdown 用
[python-markdown](https://python-markdown.github.io/) 解析，HTML/CHM/EPUB
用 [lxml](https://lxml.de/) 清洗，HTML→Markdown 用
[html2text](https://github.com/Alir3z4/html2text/)。

- 书名、作者、简介优先取文件头部的 YAML frontmatter，缺的字段回退到文件名（`《书名》作者：xxx.md`），
  HTML/CHM/EPUB 还会从页面 `<title>` / `<meta name="author">` / EPUB 元数据里再兜一次
- frontmatter 会自动从正文里剥离，不会再混进正文
- 输入格式是插件：`markdown` / `txt` / `asciidoc` / `html` / `epub` / `chm`
  （HTML 同时支持目录和 URL）
- 输出格式用 `-f/--format` 控制：`epub`（默认）或 `md`
- 样式可定制：封面页 / 扉页 / 目录页 / 简介页 / 章节标题 / 各级标题 / 正文各有一段 CSS 钩子

## 依赖（一次性，装在项目里）

依赖装在项目自己的 `.venv` 里，**不需要装到 dotfiles，也不影响系统 Python**：

```bash
cd ~/workspace/bookconv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

依赖是 `ebooklib`、`markdown`、`lxml` 和 `html2text`（`ebooklib` 本来也会带
`lxml`，这里显式写上，因为 HTML/CHM/EPUB 插件直接用它；`html2text` 只在
`-f md` 时用到）。不想建 venv 也行：把这些包装到系统 Python，然后
`PYTHONPATH=src python3 -m bookconv 某书.md`。

**CHM 额外依赖一个解包工具**（按顺序尝试，有一个就够）：

```bash
# macOS
brew install p7zip        # 提供 7z；或者 brew install unar
# Debian / Ubuntu
sudo apt install p7zip-full
```

CHM 本身是微软的压缩帮助格式，纯 Python 解 LZX 太折腾，所以这里调用系统工具解包，
解出来的目录再交给 HTML 插件。

## 使用

项目根目录的 `./bookconv` 会自动使用 `.venv` 里的解释器，所以直接跑就行：

```bash
./bookconv 某书.md                    # 默认样式
./bookconv 某书.txt                   # 纯文本（按章标题切）
./bookconv 某书.adoc                  # AsciiDoc
./bookconv 某书.chm                   # CHM（需要 7z 或 unar）
./bookconv 某书.epub                  # EPUB（默认输出 EPUB）
./bookconv 某书目录/                   # 整本 HTML 目录
./bookconv http://example.com/book/   # 网页入口页（抓页面里的章节链接）
./bookconv -f md 某书.epub            # 输出 Markdown（EPUB → MD）
./bookconv -f md -o 某书.md 某书.chm  # CHM → Markdown
./bookconv -f md --no-frontmatter 某书.epub
./bookconv -s my-style.css 某书.md    # 自定义样式（整体替换）
./bookconv --extra-style fix.css 某书.md
./bookconv -i txt 某书.txt            # 强制按 txt 解析
./bookconv -m calibre 某书.md         # 用 calibre 兜底

# 多个文件
./bookconv 卷一.md 卷二.md            # 每个文件各生成一个 epub
./bookconv --merge 卷一.md 卷二.md    # 按命令行顺序合并成一本
./bookconv --merge -o 全本.epub 卷一.md 卷二.md
```

输出文件写在**当前目录**，文件名与源文件/目录同名（`某书.md` → `某书.epub`，
`某书目录/` → `某书目录.epub`；`-f md` 时 `某书.epub` → `某书.md`）。如果默认
输出名和输入文件相同（例如 `某书.epub` 再输出 EPUB），会写成 `某书-converted.epub`，
不会覆盖原文件；显式用 `-o` 指定和输入相同的路径则直接报错。

合并成一本时：各文件的 frontmatter 会被剥掉，书名/作者/简介取第一个有值的文件
（一般只需要给第一个文件写 frontmatter）；章节顺序就是命令行顺序；只支持内建引擎。

从别的目录调用：`~/workspace/bookconv/bookconv 某书.md`。
想让 `bookconv` 变成 PATH 里的命令（可选），`install -m 755 contrib/bookconv-shim.sh ~/.dotfiles/util/bin/bookconv`。

| 选项 | 说明 |
| --- | --- |
| `-m, --method` | `native`（默认，内建实现）/ `calibre` / `pandoc` |
| `-i, --input` | 输入格式 `markdown` / `txt` / `asciidoc` / `html` / `epub` / `chm`，默认按扩展名/目录内容识别 |
| `-f, --format` | 输出格式 `epub`（默认）或 `md`；`--output-format` 是别名 |
| `--no-frontmatter` | `-f md` 时不写 YAML frontmatter |
| `--merge` | 把多个输入（文件/目录/URL）合并成一本书 |
| `-o, --output FILE` | 输出文件名（默认同源文件名；合并时用第一个文件的名字） |
| `--cover FILE` | 指定封面图（默认找同名图片/目录里的 `cover.*`；EPUB 用内嵌封面） |
| `-s, --style FILE` | 用该 CSS 替换内置默认样式（仅 EPUB 输出） |
| `--extra-style FILE` | 在最终样式后追加 CSS，可重复（仅 EPUB 输出） |
| `--lang` | 书籍语言，默认 `zh` |
| `--no-cover` / `--no-titlepage` / `--no-intro` | 不生成对应页面 |
| `--intro-title` | 简介页标题，默认“简介” |
| `--keep-indent` | 保留段落开头的全角空格（默认去掉，交给 CSS `text-indent`） |
| `--chapter-pattern REGEX` | txt 的章标题正则 |
| `-v, --verbose` | 打印解析到的元数据、使用的样式等 |

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
  <div class="titlepage-inner">
    <h1 class="book-title">书名</h1><p class="book-author">作者</p>
  </div>
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
| `.titlepage` / `.titlepage-inner` / `.book-title` / `.book-author` | 扉页（默认上下居中） / 内容块 / 书名 / 作者 |
| `nav` / `nav h2` / `nav ol` / `nav a` | 导航文档（个别阅读器会显示它，一般看不到） |
| `.intro` / `.intro-title` | 简介页 / 简介标题 |
| `.chapter` / `.chapter.first` | 正文页 |
| `.chapter h1` | 章节标题 |
| `.chapter h2`、`.chapter h3` | 小节标题 |
| `.chapter p` | 正文段落 |
| `.chapter img`、`.chapter blockquote`、`.chapter hr`、`.chapter pre`、`.chapter code`、`.chapter table` | 对应元素 |

默认字体：正文用宋体（Songti SC / 思源宋体），书名和各级标题用黑体
（PingFang SC / 思源黑体 / 微软雅黑 / SimHei），这样标题和正文能明显区分开；
想换字体就覆盖对应选择器的 `font-family`。

样式来源的优先级：

1. `--style` 指定的文件
2. `~/.config/bookconv/style.css`（存在时自动使用，**整体替换**默认样式）
3. 包内 `src/bookconv/data/default.css`

追加的样式（按顺序）：`--extra-style`，然后是 `~/.config/bookconv/extra.css`
（存在时自动追加）。所以日常微调只要写 `extra.css`，不用抄整个默认样式。

`examples/style.css` 是一个“无衬线、无首行缩进、标题左对齐”的完整示例：

```bash
./bookconv -s examples/style.css 某书.md
```

## 输入插件

`src/bookconv/inputs/` 下每个插件都实现同一个接口：

```python
class MyInput(InputFormat):
    name = "myformat"
    extensions = ("my",)

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        ...
```

- `SourceFile.path` 可以是文件、目录或 http(s) URL；目录/URL 的 `raw` 为空，
  由插件自己读
- `SourceFile.text` 已经按 UTF-8 / GB18030 解码；`base_dir` 是源文件目录
- 返回 `Chapter(title, html, level)`
  - `html` 是页面内片段：章节标题 `<h1>`、小节 `<h2>/<h3>`、段落 `<p>`
  - `level` 是目录层级（1 顶层，2 挂在上一个顶层下面）
  - `virtual=True` 表示只占目录分组、不生成正文页（例如下面没有正文的卷名）
- 段落缩进用 `htmlutil.strip_paragraph_indent`，插图用 `htmlutil.rewrite_images`
- 可选实现 `metadata()`，在文件名猜不出书名/作者时从内容里补
- 可选实现 `cover()`，返回源文件内嵌的封面（EPUB 用；HTML/CHM 返回 None）
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
./bookconv -i txt --chapter-pattern '^第[0-9]+章' 某书.txt
```

### AsciiDoc 插件

支持小说/技术书里常见的 AsciiDoc 子集：

- 文档头：`= 书名`、`:author:` / `:authors:`、`:description:`
- 章节：`== 第一章`（一级）、`=== 第一节`（二级）……
- 段落、`*` / `-` / `.` 列表、定义列表、`____` 引用块、`****` 侧栏、`====` 示例
- `----` / `....` 代码块、`|===` 表格、`image::` / `image:` 插图
- `*粗体*`、`_斜体_`、`` `等宽` ``、`#高亮#`、`^上标^`、`~下标~`、`link:...[]`

```bash
./bookconv 某书.adoc
./bookconv -i asciidoc 某书.txt        # 显式把 .txt 按 AsciiDoc 解析
```

刻意不支持 `include::`、条件指令、属性替换、脚注编号引用等——它们要么依赖完整的
Asciidoctor，要么对小说转换没有意义。`.txt` 默认仍走 txt 插件（和旧 bookconv 的
行为不同），只有显式 `-i asciidoc` 才会按 AsciiDoc 解析。

### HTML 插件

三种输入都支持：

```bash
./bookconv 某书.html                  # 单个页面
./bookconv 某书目录/                   # 整本 HTML 目录
./bookconv http://example.com/book/   # 网页
```

目录发现顺序：

1. `page.js` / `pages.js`（EasyCHM 生成的章节表，正文在 `txt/*.txt` 里也能读）
2. `.hhc`（CHM 自带的 HTML Help Contents）
3. `index.html` / `cover.html` / `start.html` 等入口页里的链接（会识别子目录里的子书）
4. 都没有时按文件名自然排序

正文清洗：去掉 `script/style/iframe/form`、导航/页眉页脚、`display:none` 的元素；
把 `<br><br>` 还原成段落；保留段落、标题、列表、表格、引用、代码和插图。生成的
EPUB 里没有对应的页面文件，所以相对链接只保留文字，外部链接保留。

插图支持本地相对路径、远程 URL 和 `data:` URI；目录输入会找 `cover.jpg/png/webp`
作为封面。网页只抓静态 HTML，不执行 JavaScript；旧 bookconv 里针对凤凰读书、南方周末、
南都周刊的站点专用解析器没有迁移（这些页面结构早已失效），现在用通用入口页链接发现。

### CHM 插件

```bash
./bookconv 某书.chm
```

先用 `7z` / `7za` / `7zz` / `unar` / `bsdtar` 把 CHM 解包到临时目录（见上面的依赖），之后完全
复用 HTML 插件：优先 EasyCHM 的 `page.js` + `txt/`，其次 `.hhc`，最后入口页/文件名排序。

限制：加密或损坏的 CHM 可能解不开；解包工具报错时会把错误原样打印出来。作者信息经常
提取不到，这时只要求有书名，作者留空，不会因此拒绝转换。

### EPUB 插件

```bash
./bookconv 某书.epub                  # EPUB → EPUB
./bookconv -f md 某书.epub            # EPUB → Markdown
```

用 ebooklib 读 EPUB：书名/作者/简介从 OPF 的 DC 元数据取；目录优先用 NCX/NAV，
没有目录时按 spine 顺序；EPUB 漏在目录外的正文文档会补在最后。章节正文和插图复用
HTML 插件的清洗逻辑，封面根据 `properties="cover-image"`、OPF `meta name="cover"`、
guide 和文件名依次查找，输出 EPUB 时会带上。

限制：

- 加密/DRM 的 EPUB 读不了（ebooklib 会直接报错）
- 目录里指向同一个 XHTML 文件不同锚点（`chapter.xhtml#sec1`）的情况，按文件只取一次，
  不会把每个锚点拆成独立章节
- EPUB 自带 CSS 不保留，统一用 bookconv 的样式
- 文字方向、脚注弹窗等 EPUB3 特性不会特殊处理

## Markdown 输出（`-f md`）

```bash
./bookconv -f md 某书.epub
./bookconv -f md -o 某书.md 某书.chm
./bookconv -f md --no-frontmatter 某书.epub
```

输出内容：

- 文件头默认写 YAML frontmatter（`title` / `authors` / `comments`），可以直接被
  bookconv 的 Markdown 输入读回；加 `--no-frontmatter` 就不写
- 章节标题按目录层级写成 `#` / `##` / `###`
- 插图写到 `<md 文件名>.images/` 目录，Markdown 里的路径同步改写
  （例如 `某书.md` 的图片在 `某书.images/`；目录名里的标点会替换成 `_`）
- 如果输入自带封面，会写成与 md 同名的图片（`某书.jpg` / `某书.png`），
  这样再把 md 转回 EPUB 时能自动识别为封面
- `-f md` 只支持内建引擎（`-m native`）；`--style` / `--extra-style` 对 md 输出无效

注意：Markdown 输出会保留 `##` 等层级。bookconv 的 Markdown **输入**把每个标题都作为
独立页面（标题 + 该标题下面的正文），标题级别按文档里的最高一级换算成 1、2、3……
所以 `# 卷` / `## 章` / `### 节` 的 EPUB → MD → EPUB 能保留分卷和章节层级。
如果某个标题下面没有正文、直接就是下一级标题，它只作为目录分组，不生成空页；
既没有正文也没有子标题的标题才会生成一个只有标题的页面。

## Markdown 支持

用 python-markdown，启用了 `extra` + `toc` 扩展，所以常见写法都支持：

- 标题（自动生成唯一 id）、段落、`---` 分隔线、`>` 引用、围栏/缩进代码块
- 表格、脚注、定义列表、属性列表（`extra`）
- 列表、图片、链接、粗体/斜体、行内代码、原始 HTML

每个标题都会成为章节页或目录分组，页面内容是“标题 + 下一个标题之前的正文”。
标题级别是相对的：文档里最高一级标题算 1 级，下一级算 2 级，依此类推。例如：

```markdown
# 卷一          → 1 级：有正文时是页面，没有正文时只是目录分组
## 第一章        → 2 级页面（正文是第一章正文）
### 第一节       → 3 级页面
## 第二章        → 2 级页面
```

只有 `##` 的文档会把 `##` 当 1 级、`###` 当 2 级，依此类推。第一个标题之前的内容
会成为“前言”页；完全没有标题的文档仍然只有一页“正文”。

如果卷名下面没有正文、直接就是 `## 第一章`，卷名只会出现在目录里（作为分组），
不会生成一个只有“卷一”的空白页；如果卷名下面有“卷首语”之类的正文，就会生成
卷首页。既没有正文也没有子标题的标题仍会生成只有标题的页面。

`--keep-indent` 会把行首全角空格换成字符实体再渲染，避免被 Markdown 的段落处理吃掉。

## 项目结构

```
bookconv/
├── bookconv                 直接运行的入口（自动使用 .venv）
├── pyproject.toml         依赖与打包信息
├── src/bookconv/
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
│   ├── markdown_output.py Markdown 输出（-f md）
│   └── inputs/            输入插件（markdown、txt、asciidoc、html、epub、chm）
│       ├── htmlbook.py    HTML 目录发现 / 正文清洗（HTML/CHM/EPUB 共用）
│       ├── html.py        单文件 / 目录 / URL
│       ├── epub.py        EPUB 读取、目录/封面
│       └── chm.py         CHM 解包
├── contrib/bookconv-shim.sh 可选：装进 PATH 用的转发脚本
├── examples/style.css     示例样式
└── tests/
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 备注

- 转换开始时会打印书名、作者、有没有封面（附封面像素尺寸），结束打印“生成完成”和用时
- 封面原样嵌入、不做缩放或再压缩；封面偏小（宽 < 1000）时会提示，可用 `--cover` 换更大的图
- 扉页默认上下居中（flex + `min-height: 100vh`；老阅读器不支持 flex 时退回顶部，可用 `--style` 换成固定上边距）
- 封面页/扉页/简介页标了 `epub:type`（`cover` / `titlepage` / `preface`），guide 里也声明了
  `title-page`，帮助阅读器认出扉页、不要自己再生成一页
- 生成的 EPUB 是 EPUB 3（带 `nav` 导航文档），同时写了 `toc.ncx`，老阅读器也能用
- 目录只作为导航文档（`nav.xhtml` + `toc.ncx`），不进正文；点击阅读器的目录即可跳转
- `webp` 封面/插图会尝试用 `sips`（macOS 自带）或 ImageMagick 转成 png，失败则按原格式嵌入
- calibre / pandoc 引擎保留作兜底，它们不使用 `--style`，页面结构也不同
- 书名必须有（frontmatter `title`、文件名 `《书名》…`、HTML/CHM 的 `<title>`，或 EPUB 元数据）；
  作者可以没有，不会因此拒绝转换
- HTML/CHM/EPUB 里的相对链接不会改写指向 EPUB 内部页面，统一去掉 `href` 只留文字；
  站内锚点、脚注跳转也会失效
- 从旧 bookconv 迁移了 CHM、AsciiDoc、HTML、HTML 目录、URL 这几种输入；`.txt` 仍由
  原有 txt 插件处理。旧程序里针对具体网站的抓取逻辑没有保留
