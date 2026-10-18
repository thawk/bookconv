"""AsciiDoc 输入插件的测试。"""

import base64
import os
import tempfile
import unittest

from cvbook.images import ImageStore
from cvbook.inputs.asciidoc import AsciiDocInput, _BlockRenderer, split_document
from cvbook.inputs.base import ParseOptions, SourceFile

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class SplitDocumentTest(unittest.TestCase):
    def test_header_and_sections(self):
        attrs, sections = split_document("""\
= 书名
:author: 张三
:description: 简介

前言。

== 第一章

正文一。

=== 第一节

正文二。

== 第二章

正文三。
""")
        self.assertEqual(attrs["title"], "书名")
        self.assertEqual(attrs["author"], "张三")
        self.assertEqual(attrs["description"], "简介")
        self.assertEqual([s.title for s in sections],
                         ["", "第一章", "第一节", "第二章"])
        self.assertEqual([s.level for s in sections], [0, 1, 2, 1])
        self.assertIn("前言", "\n".join(sections[0].lines))

    def test_no_document_title(self):
        attrs, sections = split_document(":author: 李四\n\n== 章\n\n正文\n")
        self.assertEqual(attrs["author"], "李四")
        self.assertEqual(sections[-1].title, "章")


class AsciiDocInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        with open(os.path.join(self.root, "pic.png"), "wb") as f:
            f.write(PNG)
        self.text = """\
= 测试书
:author: 张三, 李四
:description: 一本测试书。

前言段落。

== 第一章 开始

　　第一段正文。

第二段有 *粗体*、_斜体_、`代码` 和 link:https://example.com[链接]。

* 列表一
* 列表二
** 子项

. 有序一
. 有序二

----
code line 1
code line 2
----

image::pic.png[插图]

=== 第一节 小节

____
引用块。
____

== 第二章 继续

最后一段。
"""
        self.source = SourceFile(os.path.join(self.root, "book.adoc"),
                                 self.text.encode("utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self):
        images = ImageStore()
        chapters = AsciiDocInput().parse(
            self.source, images=images, options=ParseOptions())
        return chapters, images

    def test_metadata(self):
        meta = AsciiDocInput().metadata(self.source)
        self.assertEqual(meta.title, "测试书")
        self.assertEqual(meta.authors, ["张三", "李四"])
        self.assertEqual(meta.comments, "一本测试书。")

    def test_chapters_and_levels(self):
        chapters, _images = self.parse()
        self.assertEqual([c.title for c in chapters],
                         ["前言", "第一章 开始", "第一节 小节",
                          "第二章 继续"])
        self.assertEqual([c.level for c in chapters], [1, 1, 2, 1])
        self.assertIn("前言段落", chapters[0].html)

    def test_inline_and_blocks(self):
        chapters, images = self.parse()
        chapter = chapters[1]
        self.assertIn("<strong>粗体</strong>", chapter.html)
        self.assertIn("<em>斜体</em>", chapter.html)
        self.assertIn("<code>代码</code>", chapter.html)
        self.assertIn('href="https://example.com"', chapter.html)
        self.assertIn("<ul><li>列表一</li><li>列表二<ul><li>子项</li></ul></li></ul>",
                      chapter.html)
        self.assertIn("<ol><li>有序一</li><li>有序二</li></ol>",
                      chapter.html)
        self.assertIn("<pre>code line 1\ncode line 2</pre>", chapter.html)
        self.assertIn('src="../images/pic.png"', chapter.html)
        self.assertEqual([image.path for image in images.items],
                         ["images/pic.png"])

    def test_quote_block(self):
        chapters, _images = self.parse()
        self.assertIn("<blockquote><p>引用块。</p></blockquote>",
                      chapters[2].html)

    def test_table(self):
        html = _BlockRenderer().render([
            "|===",
            "|甲|乙|",
            "|丙|丁|",
            "|===",
        ])
        self.assertIn("<table><tbody>", html)
        self.assertIn("<tr><td>甲</td><td>乙</td></tr>", html)
        self.assertIn("<tr><td>丙</td><td>丁</td></tr>", html)

    def test_keep_indent(self):
        chapters = AsciiDocInput().parse(
            self.source, images=ImageStore(),
            options=ParseOptions(keep_indent=True))
        self.assertIn("\u3000\u3000第一段正文", chapters[1].html)


if __name__ == "__main__":
    unittest.main()
