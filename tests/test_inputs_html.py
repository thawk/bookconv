"""HTML / URL / CHM 输入插件的测试。"""

import base64
import functools
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from cvbook.images import ImageStore
from cvbook.inputs.base import ParseOptions, SourceFile
from cvbook.inputs.chm import ChmInput
from cvbook.inputs.html import HtmlInput

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class HtmlBookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.write("index.html", """\
<html><head><title>测试书</title>
<meta name="author" content="张三"></head><body>
<h1>测试书</h1>
<ul>
  <li><a href="001.html">第一章 开始</a></li>
  <li><a href="002.html">第二章 继续</a></li>
</ul>
</body></html>
""")
        self.write("001.html", """\
<html><head><title>第一章 开始</title></head><body>
<div class="nav">上一章 目录 下一章</div>
<h1>第一章 开始</h1>
<p>　　正文一。</p>
<img src="pic.png" alt="插图">
</body></html>
""")
        self.write("002.html", """\
<html><head><title>第二章 继续</title></head><body>
<font size=3>　　正文二第一行<br><br>　　正文二第二行</font>
<p><a href="http://example.com/x">外部链接</a> <a href="001.html">内部链接</a></p>
</body></html>
""")
        self.write_bytes("pic.png", PNG)
        self.fmt = HtmlInput()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_bytes(self, name, data):
        with open(os.path.join(self.root, name), "wb") as f:
            f.write(data)

    def parse(self, path):
        images = ImageStore()
        chapters = self.fmt.parse(SourceFile(path, b""), images=images,
                                  options=ParseOptions())
        return chapters, images

    def test_directory_links(self):
        chapters, images = self.parse(self.root)
        self.assertEqual([c.title for c in chapters],
                         ["第一章 开始", "第二章 继续"])
        self.assertEqual([c.level for c in chapters], [1, 1])
        self.assertIn("正文一", chapters[0].html)
        self.assertIn("正文二第二行", chapters[1].html)
        # <br><br> 应该变成两个段落；导航文字要丢掉
        self.assertIn("<p>正文二第一行</p>", chapters[1].html)
        self.assertNotIn("上一章", chapters[0].html)
        # 内部链接去 href，外部链接保留
        self.assertIn('href="http://example.com/x"', chapters[1].html)
        self.assertNotIn('href="001.html"', chapters[1].html)
        # 插图
        self.assertIn('src="../images/pic.png"', chapters[0].html)
        self.assertEqual([image.path for image in images.items],
                         ["images/pic.png"])

    def test_metadata(self):
        meta = self.fmt.metadata(SourceFile(self.root, b""))
        self.assertEqual(meta.title, "测试书")
        self.assertEqual(meta.authors, ["张三"])

    def test_single_html_file(self):
        chapters, _images = self.parse(os.path.join(self.root, "001.html"))
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "第一章 开始")
        self.assertIn("正文一", chapters[0].html)

    def test_hhc_toc(self):
        os.remove(os.path.join(self.root, "index.html"))
        self.write("toc.hhc", """\
<HTML><BODY><UL>
<LI><OBJECT type="text/sitemap"><param name="Name" value="第一卷"></OBJECT>
<UL>
<LI><OBJECT type="text/sitemap"><param name="Name" value="第一章 开始">
<param name="Local" value="001.html"></OBJECT>
<LI><OBJECT type="text/sitemap"><param name="Name" value="第二章 继续">
<param name="Local" value="002.html"></OBJECT>
</UL>
</UL></BODY></HTML>
""")
        chapters, _images = self.parse(self.root)
        self.assertEqual([c.title for c in chapters],
                         ["第一卷", "第一章 开始", "第二章 继续"])
        self.assertEqual([c.level for c in chapters], [1, 2, 2])
        self.assertIn("正文一", chapters[1].html)

    def test_pagejs_and_txt_content(self):
        os.remove(os.path.join(self.root, "index.html"))
        os.remove(os.path.join(self.root, "001.html"))
        os.remove(os.path.join(self.root, "002.html"))
        os.makedirs(os.path.join(self.root, "js"))
        os.makedirs(os.path.join(self.root, "txt"))
        self.write("js/page.js", """\
pages[0]=['01_01','第一章 开始','1520','第一卷 风起'];
pages[1]=['01_02','第二章 继续','1480','第一卷 风起'];
pages[2]=['02_01','第三章 新卷','1200','第二卷 云涌'];
""")
        self.write("txt/01_01.txt",
                   "document.write('<font>　　正文一<br><br>正文一第二段</font>');")
        self.write("txt/01_02.txt", "document.write('正文二');")
        self.write("txt/02_01.txt", "document.write('正文三');")

        chapters, _images = self.parse(self.root)
        self.assertEqual([c.title for c in chapters],
                         ["第一卷 风起", "第一章 开始", "第二章 继续",
                          "第二卷 云涌", "第三章 新卷"])
        self.assertEqual([c.level for c in chapters], [1, 2, 2, 1, 2])
        self.assertIn("<p>正文一</p>", chapters[1].html)
        self.assertIn("<p>正文一第二段</p>", chapters[1].html)
        self.assertNotIn("document.write", chapters[1].html)

    def test_iframe_redirect(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "chm", "list"))
            with open(os.path.join(root, "cover.html"), "w",
                      encoding="utf-8") as f:
                f.write('<html><body><iframe src="chm/list/index.html">'
                        '</iframe></body></html>')
            with open(os.path.join(root, "chm", "list", "index.html"), "w",
                      encoding="utf-8") as f:
                f.write('<html><head><title>重定向书</title></head><body>'
                        '<a href="001.html">第一章</a>'
                        '<a href="002.html">第二章</a></body></html>')
            for index in (1, 2):
                with open(os.path.join(root, "chm", "list",
                                       "%03d.html" % index), "w",
                          encoding="utf-8") as f:
                    f.write('<html><body><h1>第%d章</h1><p>正文</p>'
                            '</body></html>' % index)
            source = SourceFile(root, b"")
            self.assertEqual(self.fmt.metadata(source).title, "重定向书")
            chapters, _images = self.parse(root)
            self.assertEqual([c.title for c in chapters],
                             ["第一章", "第二章"])

    def test_url(self):
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        handler = functools.partial(Quiet, directory=self.root)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%d/index.html" % httpd.server_address[1]
            source = SourceFile(url, b"")
            self.assertTrue(self.fmt.matches(source))
            meta = self.fmt.metadata(source)
            self.assertEqual(meta.title, "测试书")
            images = ImageStore()
            chapters = self.fmt.parse(source, images=images,
                                      options=ParseOptions())
            self.assertEqual([c.title for c in chapters],
                             ["第一章 开始", "第二章 继续"])
            self.assertEqual([image.path for image in images.items],
                             ["images/pic.png"])
        finally:
            httpd.shutdown()
            httpd.server_close()


@unittest.skipUnless(shutil.which("7z"), "需要 7z 才能测试 CHM 解包")
class ChmInputTest(unittest.TestCase):
    def test_fake_chm_archive(self):
        """用 7z 造一个扩展名为 .chm 的 7z 包，测试解包和后续解析流程。"""
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "index.html"), "w",
                      encoding="utf-8") as f:
                f.write('<html><head><title>CHM 书</title></head><body>'
                        '<a href="001.html">第一章</a></body></html>')
            with open(os.path.join(src, "001.html"), "w",
                      encoding="utf-8") as f:
                f.write('<html><body><h1>第一章</h1><p>正文</p></body></html>')
            chm = os.path.join(tmp, "book.chm")
            result = subprocess.run(
                ["7z", "a", "-t7z", "-y", chm, "."],
                cwd=src, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result.returncode != 0:
                self.skipTest("7z 无法创建测试包")

            with open(chm, "rb") as f:
                raw = f.read()
            fmt = ChmInput()
            source = SourceFile(chm, raw)
            self.assertTrue(fmt.matches(source))
            self.assertEqual(fmt.metadata(source).title, "CHM 书")
            chapters = fmt.parse(source, images=ImageStore(),
                                 options=ParseOptions())
            self.assertEqual([c.title for c in chapters], ["第一章"])
            self.assertIn("正文", chapters[0].html)


if __name__ == "__main__":
    unittest.main()
