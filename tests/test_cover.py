"""封面 / 简介抓取测试（不访问网络，只测解析与选择逻辑）。"""

import base64
import contextlib
import io
import os
import tempfile
import unittest

from bookconv.cover import (Book, Response, clean_title, download, image_info,
                            is_related, normalize, parse_17k, parse_jjwxc,
                            parse_jjwxc_detail, parse_qidian, parse_zongheng,
                            quote_query, safe_base_name, select_book, text_of,
                            url_extension, write_file)
from bookconv.cover_cli import BookQuery, parse_query, parse_queries

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)

QIDIAN_PAGE = """
<div class="y-list__item" data-index="0"><a class="_bookWrapper_e9qzy_9"
 href="//m.qidian.com/chapter/107580/0/" data-bid="107580">
 <div><img data-src="//bookcover.yuewen.com/qdbimg/349573/107580/180"></div>
 <div><h2 class="_searchBookName_lrbl7_250"><mark>凡人修仙传</mark></h2>
 <p class="_searchBookDesc_lrbl7_337">一个普通山村小子，偶然下进入到当地江湖小门派。</p>
 <div><p class="_searchBookAuthor_lrbl7_429">忘语</p></div></div></a></div>
"""

K17_PAGE = """
<div class="textlist"><div class="textleft">
<a href="//www.17k.com/book/3479673.html"><img
 src="https://cdn.static.17k.com/book/189x272/73/96/3479673.jpg-189x272?v=1"
 alt="长生仙游"></a></div>
<div class="textmiddle"><dl>
<dt><a href="//www.17k.com/book/3479673.html" target="_blank">长生仙游</a></dt>
<dd><ul><li class="bq"><span class="ls">作者：
<a href="//user.17k.com/see/www/65617443.html">四更不睡</a></span></li>
<li><strong>简介：</strong><p><a href="//www.17k.com/list/3479673.html">一场意外将陈长生带到了一方仙侠世界。</a></p></li>
</ul></dd></dl></div></div>
"""

JJWXC_PAGE = """
<div><h3 class="title"><a data-recommendInfo='{"relationNovelid":"2956313"}'
 class="track" href="http://www.jjwxc.net/onebook.php?novelid=2956313"
 target="_blank">《撒野》</a><font size='-2'>(2021-01-03)</font></h3>
<div class="intro">校园文。HE。</div>
<div class="info">作者：<a href="http://www.jjwxc.net/oneauthor.php?authorid=1"
 target="_blank"><span style="color: #3B9D3B; ">巫哲</span></a>
 ┃ 进度：完结</div></div>
"""

JJWXC_DETAIL = """
<img class="noveldefaultimage" itemprop="image"
 _src="https://i9-static.jjwxc.net/novelimage.php?novelid=2956313&amp;coverid=23"
 src="https://s3-static.jjwxc.net/tmp/guanli/frontcover/002/956/2956313.jpg"
 width="200" height="280" referrerpolicy="no-referrer">
<div id="novelintro" itemprop="description">校园文。HE。<br>写不出文案的作者跪在这里。<br><br>第二段。</div>
"""

ZONGHENG_JSON = {
    "code": 0,
    "data": {"datas": {"list": [
        {"bookId": 189169,
         "name": '<font color="RED">雪中悍刀行</font>',
         "authorName": "烽火戏诸侯",
         "description": "江湖是一张珠帘。\n大人物小人物，是珠子。",
         "coverUrl": "/cover/8c/75/x.jpeg"},
        {"bookId": 189169,
         "name": "重复条目",
         "authorName": "某人",
         "description": "",
         "coverUrl": ""},
    ]}},
}


def make_book(title, author, site="qidian"):
    return Book(site_key=site, site_label=site, title=title, author=author)


def fake_png(width, height):
    """只带合法文件头和 IHDR 的假 PNG，够 image_info / image_size 识别。"""
    header = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
              + width.to_bytes(4, "big") + height.to_bytes(4, "big"))
    return header + b"\x00" * 32


class ParseTest(unittest.TestCase):
    def test_qidian(self):
        books = parse_qidian(QIDIAN_PAGE)
        self.assertEqual(len(books), 1)
        book = books[0]
        self.assertEqual(book.title, "凡人修仙传")
        self.assertEqual(book.author, "忘语")
        self.assertIn("普通山村", book.description)
        self.assertTrue(book.cover_urls[0].endswith("/349573/107580/600"))

    def test_17k(self):
        books = parse_17k(K17_PAGE)
        self.assertEqual(len(books), 1)
        book = books[0]
        self.assertEqual((book.title, book.author), ("长生仙游", "四更不睡"))
        self.assertIn("陈长生", book.description)
        self.assertIn("/600x800/", book.cover_urls[0])
        self.assertIn("-600x800", book.cover_urls[0])
        self.assertIn("189x272", book.cover_urls[1])

    def test_jjwxc_search(self):
        books = parse_jjwxc(JJWXC_PAGE)
        self.assertEqual(len(books), 1)
        book = books[0]
        self.assertEqual((book.title, book.author), ("撒野", "巫哲"))
        self.assertEqual(book.description, "校园文。HE。")
        self.assertIn("novelid=2956313", book.page_url)

    def test_jjwxc_detail(self):
        book = parse_jjwxc(JJWXC_PAGE)[0]
        parse_jjwxc_detail(book, JJWXC_DETAIL)
        self.assertTrue(book.cover_urls[0].startswith(
            "https://i9-static.jjwxc.net/novelimage.php"))
        self.assertIn("s3-static.jjwxc.net", book.cover_urls[1])
        self.assertIn("写不出文案", book.description)
        self.assertNotIn("<br>", book.description)

    def test_zongheng(self):
        books = parse_zongheng(ZONGHENG_JSON)
        self.assertEqual(len(books), 1)         # 重复的 bookId 被去掉
        book = books[0]
        self.assertEqual(book.title, "雪中悍刀行")
        self.assertEqual(book.author, "烽火戏诸侯")
        self.assertEqual(book.cover_urls,
                         ["https://static.zongheng.com/upload/cover/8c/75/x.jpeg"])
        self.assertIn("珠帘", book.description)


class SourceParseTest(unittest.TestCase):
    def test_plain_title(self):
        self.assertEqual(parse_query("凡人修仙传"),
                         BookQuery("凡人修仙传"))

    def test_bookconv_filename(self):
        self.assertEqual(parse_query("《剑来》作者：烽火戏诸侯.md"),
                         BookQuery("剑来", "烽火戏诸侯"))

    def test_bookconv_string_without_extension(self):
        self.assertEqual(parse_query("《剑来》作者：烽火戏诸侯"),
                         BookQuery("剑来", "烽火戏诸侯"))

    def test_path_and_url(self):
        self.assertEqual(
            parse_query("/tmp/books/《剑来》作者：烽火戏诸侯.epub"),
            BookQuery("剑来", "烽火戏诸侯"))
        self.assertEqual(
            parse_query("https://example.com/《剑来》作者：烽火戏诸侯.md"),
            BookQuery("剑来", "烽火戏诸侯"))

    def test_plain_filename_strips_extension(self):
        self.assertEqual(parse_query("剑来.md"), BookQuery("剑来"))

    def test_plain_author_suffix(self):
        self.assertEqual(parse_query("剑来 作者：烽火戏诸侯.md"),
                         BookQuery("剑来", "烽火戏诸侯"))

    def test_dedupe(self):
        queries = parse_queries([
            "《剑来》作者：烽火戏诸侯.md",
            "《剑来》作者：烽火戏诸侯.epub",
            "剑来",
        ])
        self.assertEqual(queries, [BookQuery("剑来", "烽火戏诸侯")])

    def test_same_title_different_authors_kept(self):
        queries = parse_queries(["《剑来》作者：甲", "《剑来》作者：乙"])
        self.assertEqual(queries, [BookQuery("剑来", "甲"),
                                   BookQuery("剑来", "乙")])

    def test_author_override(self):
        queries = parse_queries(["《剑来》作者：甲", "《剑来》作者：乙"],
                                author="丙")
        self.assertEqual(queries, [BookQuery("剑来", "丙")])

    def test_author_override_applies_to_all_inputs(self):
        queries = parse_queries(
            ["《剑来》作者：甲", "《雪中悍刀行》", "《剑来》作者：乙"],
            author="丙")
        self.assertEqual(queries, [BookQuery("剑来", "丙"),
                                   BookQuery("雪中悍刀行", "丙")])


class TextTest(unittest.TestCase):
    def test_text_of(self):
        html = "<p>第一段<br>换行</p><p>&amp;第二段</p><script>x</script>"
        self.assertEqual(text_of(html), "第一段\n换行\n&第二段")

    def test_clean_title(self):
        self.assertEqual(clean_title("《撒野》"), "撒野")
        self.assertEqual(clean_title(" <mark>剑来</mark> "), "剑来")

    def test_normalize(self):
        self.assertEqual(normalize("《剑来》"), normalize("剑　来"))
        self.assertEqual(normalize("ＡＢＣ"), "abc")

    def test_quote_query_gbk(self):
        self.assertEqual(quote_query("撒野", "gb18030"), "%C8%F6%D2%B0")


class ImageTest(unittest.TestCase):
    def test_png(self):
        self.assertEqual(image_info(PNG), ("png", 1, 1))

    def test_not_image(self):
        self.assertIsNone(image_info(b"<html>not an image</html>"))

    def test_url_extension(self):
        self.assertEqual(url_extension("https://a/b/cover.JPEG"), ".jpeg")
        self.assertEqual(url_extension("https://a/b/img?f=.png"), ".png")
        self.assertIsNone(url_extension("https://a/novelimage.php?id=1"))


class MatchTest(unittest.TestCase):
    def test_is_related(self):
        self.assertTrue(is_related("雪中", "雪中悍刀行"))
        self.assertTrue(is_related("凡人", "凡人修仙传"))
        self.assertFalse(is_related("完全不存在的书", "另一本书"))

    def select(self, books, title, author=None, **kwargs):
        # 测试里不读终端输入，否则在交互式终端跑测试会卡在“请选择序号”
        kwargs.setdefault("interactive", False)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return select_book(title, author, books, **kwargs)

    def test_exact_match(self):
        books = [make_book("剑来", "烽火戏诸侯")]
        self.assertEqual(self.select(books, "剑来").author, "烽火戏诸侯")

    def test_multi_site_same_book_prefers_qidian(self):
        books = [make_book("剑来", "烽火戏诸侯", "zongheng"),
                 make_book("剑来", "烽火戏诸侯", "qidian")]
        self.assertEqual(self.select(books, "剑来").site_key, "qidian")

    def test_same_title_different_author_needs_pick(self):
        books = [make_book("剑来", "甲"), make_book("剑来", "乙")]
        self.assertIsNone(self.select(books, "剑来"))
        chosen = self.select(books, "剑来", pick=2)
        self.assertEqual(chosen.author, "乙")

    def test_author_mismatch_falls_back_to_same_title(self):
        books = [make_book("凡人修仙传", "忘语")]
        chosen = self.select(books, "凡人修仙传", author="张三", pick=1)
        self.assertEqual(chosen.author, "忘语")

    def test_unrelated_suggestions_are_filtered(self):
        books = [make_book("我的透视超给力", "番茄炖肉"),
                 make_book("龙血战神", "风青阳")]
        self.assertIsNone(self.select(books, "不存在的书名"))

    def test_auto_yes(self):
        books = [make_book("雪中悍刀行", "烽火戏诸侯"),
                 make_book("雪中狂刀行", "峰林天下")]
        self.assertEqual(self.select(books, "雪中", auto_yes=True).title,
                         "雪中悍刀行")


class DownloadTest(unittest.TestCase):
    class FakeClient:
        def get(self, url, referer=None, binary=False):
            return Response(url, 200, fake_png(600, 800),
                            {"content-type": "image/png"})

    def test_download_names_and_encoding(self):
        book = Book("qidian", "起点中文网", "剑来", "烽火戏诸侯",
                    description="简介正文", cover_urls=["https://x/cover"])
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(download(book, self.FakeClient(), directory))
            base = os.path.join(directory, "《剑来》作者：烽火戏诸侯")
            self.assertEqual(sorted(os.listdir(directory)),
                             sorted([os.path.basename(base) + ".png",
                                     os.path.basename(base) + ".desc"]))
            with open(base + ".desc", "rb") as f:
                self.assertEqual(f.read(), "简介正文\n".encode("utf-8"))

    def test_safe_base_name(self):
        self.assertEqual(safe_base_name("A/B", "C:D"), "《A／B》作者：C：D")

    def test_write_file_no_force(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "x.txt")
            self.assertTrue(write_file(path, b"1"))
            self.assertFalse(write_file(path, b"2"))
            self.assertTrue(write_file(path, b"2", force=True))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"2")


if __name__ == "__main__":
    unittest.main()
