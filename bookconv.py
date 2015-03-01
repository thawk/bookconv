#!/usr/bin/python2
# vim: set fileencoding=utf-8 foldmethod=marker:
# Author: thawk(thawk009@gmail.com)

PROGNAME = u"bookconv.py"

VERSION = u"20150221"

# {{{ Imports
import codecs
import cookielib
import functools
import htmlentitydefs
import inspect
import json
import locale
import logging
import optparse
import os
import re
import shutil
import sqlite3
import string
import subprocess
import sys
import tempfile
import types
import uuid
import zipfile
import time

from cStringIO import StringIO
from exceptions import TypeError
from bisect import bisect_left

from cgi import escape
from urllib import urlencode, quote, basejoin, splittag, splitquery
from urllib2 import build_opener, urlopen, Request, HTTPCookieProcessor
from xml.dom import minidom
from chm.chm import CHMFile

from chm.chmlib import (
    chm_enumerate, CHM_ENUMERATE_ALL, CHM_ENUMERATOR_CONTINUE, CHM_RESOLVE_SUCCESS
)

try:
    # 大部分情况下都不需要使用chardet，因此没有也行，真正用的时候才报错
    import chardet
except:
    pass

try:    # 先尝试PIL，再尝试pillow
    import Image
except:
    from PIL import Image
# }}}

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(SCRIPT_PATH, "book_db.json")) as fp:
    BOOK_DB = json.load(fp)

STYLE_FILES = [ "font-face.css", "style.css" ]
STYLE_FILE_ENCODING = "utf-8"

# {{{ Contants
COVER_PATHS = [
    os.path.join(os.getenv("HOME"), "ebooks", "covers"),
    os.path.join(os.getenv("HOME"), "my", "book", "covers"),
]

COVER_PATTERNS = [
    u"{title}-{author}",
    u"{title} - {author}",
]

TITLE_ONLY_COVER_PATTERNS = [
    u"{title}",
]

COVER_EXTENSIONS = [ u".png", u".jpg", u".gif", u".jpeg", u".JPG", u".PNG", u".GIF", u".JPEG" ]

DEFAULT_ENCODING = "GB18030"

BOOK_DATABASE = os.path.join(os.getenv("HOME"), "ebooks", "book_database.db")

SHORT_CUTS = {
    "nfzm" : "http://www.infzm.com/enews/infzm",
};

WEB_INFOS = [
    {
        "pattern"   : re.compile("http://book\.ifeng\.com"),
        "parser"    : "IFengBookParser",
    },
    {
        "pattern"   : re.compile("http://www\.infzm\.com"),
        "login_url" : "http://passport.infzm.com/passport/login",
        "post_data" : "loginname={username}&password={password}&submit=登录&refer=http://www.infzm.com",
        "parser"    : "InfzmParser",
    },
    {   # 南都周刊/南方娱乐周刊
        "pattern"   : re.compile("http://www\.(nb|sm)weekly\.com/Print/\d+\.shtml"),
        "parser"    : "NbweeklyParser",
    },
]

PASSWORDS = [
    {
        "pattern"   : re.compile("http://www\.infzm\.com"),
        "username" : "daoewaqc",
        "password" : 'DN`0u=U^K|3>uK',
    },
]

HTML_EXT = u".html"
NCX_ID   = u"toc"
NCX_FILE = u"toc.ncx"
NCX_TYPE = u"application/x-dtbncx+xml"

IDX_ID   = u"index"
IDX_FILE = u"index" + HTML_EXT
IDX_TYPE = u"application/xhtml+xml"

OPF_FILE = u"content.opf"

CSS_FILE = u"style.css"

UID_ELEM_ID = u"BookId"

# 封面图片的文件名。后缀将使用文件原来的后缀
COVER_IMAGE_NAME = u"cover"

# 非封面图片的文件名前缀
IMAGE_PREFIX     = u"image_"
IMAGE_PATH       = u"img/"

DEFAULT_MAX_EPUB_SUB_TOC = 10
MAX_EPUB_SUB_TOCS = {       # max epub sub tocs for each level. If not in this list, use DEFAULT_MAX_EPUB_SUB_TOC
    0 : 20,                 # 根目录允许最多20项
}

# 封面图片，长边与短边之比的最大值
MAX_COVER_ASPECT_RATIO = 2.0

# 输出图片的最大宽度和高度
MAX_IMAGE_WIDTH  = 600
MAX_IMAGE_HEIGHT = 724

# 各额外部分的文件名
COVER_PAGE = u"cover_page"   # 封面
TITLE_PAGE = u"title_page"   # 书名页
PREAMBLE_PAGE = u"preamble_page"   # 前言页
TOC_PAGE   = u"toc_page"     # 目录

# 存放html页面的目录名称
CONTENT_DIR = u"content"

# 不大于该大小就使用嵌入式封面（上半显示图片，下半显示文字），否则将图片拉伸到全页面
MAX_EMBED_COVER_HEIGHT = 300

# 可嵌入目录页显示的最大preamble大小
MAX_INLINE_PREAMBLE_SIZE = 100

# 在目录中显示的简介的最大大小，超出会被截断
MAX_INLINE_INTRO_SIZE = 150

# 简介章节的缺省标题
BOOK_INTRO_TITLE = u"内容简介"
CHAPTER_INTRO_TITLE = u"内容简介"

CHAPTER_COVER_PAGE_ID_FORMAT = u"{0}_cover"
CHAPTER_TITLE_PAGE_ID_FORMAT = u"{0}_title"
CHAPTER_PREAMBLE_PAGE_ID_FORMAT   = u"{0}_preamble"
CHAPTER_TOC_PAGE_ID_FORMAT   = u"{0}_toc"

# 最上层章节的级别
CHAPTER_TOP_LEVEL = 1

# 每层目录的缩进
TOC_INDENT_CHAR = u" "
TOC_INDENT_COUNT = 3

HTTP_RETRY = 2

MEDIA_TYPES = (
    { "type":"html",  "media-type":"application/xhtml+xml",  "pattern":re.compile(r".*\.html?", re.IGNORECASE) },
    { "type":"html",  "media-type":"application/xhtml+xml",  "pattern":re.compile(r".*\.xhtml?", re.IGNORECASE) },
    { "type":"css",   "media-type":"text/css",               "pattern":re.compile(r".*\.css",   re.IGNORECASE) },
    { "type":"image", "media-type":"image/jpeg",             "pattern":re.compile(r".*\.jpe?g", re.IGNORECASE) },
    { "type":"image", "media-type":"image/png",              "pattern":re.compile(r".*\.png",   re.IGNORECASE) },
    { "type":"image", "media-type":"image/gif",              "pattern":re.compile(r".*\.gif",   re.IGNORECASE) },
)

IMAGE_FORMAT_MAP = {
    ".jpe": "JPEG",
    ".jpg": "JPEG",
    ".jfif": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".gif": "GIF",
}

DEFAULT_CATEGORY = u''
CATEGORY_NEWS_PAPER = u'报刊'

# 简介章节的名称。符合名称的章节视为简介
RE_INTRO_TITLES = (
    re.compile(u'简介|内容简介|内容提要|故事梗概', re.IGNORECASE),
)

ASCIIDOC_ATTR_TITLE = u"title"
ASCIIDOC_ATTR_ALT = u"alt"
# }}}

# {{{ Globals
options = dict()

book_dir = os.getcwd()

# 已经处理过的文件
parsed_files = dict()
url2chapter = dict()
# }}}

# {{{ General Utilities
LOG_LEVEL_TRACE = 5

logging.addLevelName(LOG_LEVEL_TRACE, "trace")
def trace(self, message, *args, **kws):
    # Yes, logger takes its '*args' as 'args'.
    if self.isEnabledFor(LOG_LEVEL_TRACE):
        self._log(LOG_LEVEL_TRACE, message, args, **kws) 

logging.Logger.trace = trace
# }}}

# {{{ General Utilities
def lineno():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno

class NotParseableError(Exception):
    def __init__(self, value):
        super(NotParseableError, self).__init__()
        self.value = value
    def __str__(self):
        return repr(self.value)

class TemporaryDirectory(object):
    '''
    A temporary directory to be used in a with statement.
    '''
    def __init__(self, suffix='', prefix='', dir=None, keep=False):
        self.suffix = suffix
        self.prefix = prefix
        self.dir = dir
        self.keep = keep

    def __enter__(self):
        self.tdir = tempfile.mkdtemp(self.suffix, self.prefix, self.dir)
        return self.tdir

    def __exit__(self, *args):
        if not self.keep and os.path.exists(self.tdir):
            shutil.rmtree(self.tdir, ignore_errors=True)

class TemporaryFile(object):
    def __init__(self, suffix="", prefix="", dir=None, mode='w+b'):
        if prefix == None:
            prefix = ''
        if suffix is None:
            suffix = ''
        self.prefix, self.suffix, self.dir, self.mode = prefix, suffix, dir, mode
        self._file = None

    def __enter__(self):
        fd, name = tempfile.mkstemp(self.suffix, self.prefix, dir=self.dir)
        self._file = os.fdopen(fd, self.mode)
        self._name = name
        self._file.close()
        return name

    def __exit__(self, *args):
        try:
            if os.path.exists(self._name):
                os.remove(self._name)
        except:
            pass

def pretty_xml(dom):
    dom.normalize()
    xml = dom.toprettyxml(u"\t", u"\n", u"utf-8")
    # toprettyxml的结果中有多余的空行，因此要把它删除，分>后的空行和<前的空行来删除，前后不是><的空行是原来文件中就有的，可能有用，不删除
    xml = re.sub(r">\n[\s\n]*\n", r">\n", xml)
    xml = re.sub(r"\n[\s\n]*\n(\s*<)", r"\n\1", xml)
    # toprettyxml会加入一些多余的空格，需要去掉
    xml = re.sub(r"([^\s>])\s*\n\s*<", r"\1<", xml)
    xml = re.sub(r">\s*\n\s*([^\s<])", r">\1", xml)
    return xml

# }}}

# {{{ Book structures
#   {{{ -- class ChapterInfo
class ChapterInfo:
    def __init__(self):
        self.title        = u""      # title used in the TOC
        self.title_inner  = u""      # title display in the content. use title if empty
        self.sub_title    = u""
        self.author       = u""
        self.subchapters  = list()   # list of Chapter
        self.cover        = None     # Img instance of the cover of chapter
        self.intro        = None     # 章节概要

        self.series       = u""
        self.category     = u""
        self.source       = u""      # 来源
        self.originated   = u""      # 发自...
        self.publisher    = u""
        self.isbn         = u""
        self.publish_date = u""
        self.publish_ver  = u""

        self.parent       = None     # 父章节
        self.toc_file     = u""      # 本章节的章节目录的路径（如果有的话）

        self.content      = list()   # list of lines，对于chapter是章节正文，对于book可以是前言（相当于正文前无标题的章节）
#   }}}

#   {{{ -- class Chapter
class Chapter(ChapterInfo):
    def __init__(self):
        ChapterInfo.__init__(self)

        self.id           = u""
        self.level        = CHAPTER_TOP_LEVEL - 1   # 设为比最小有效值小一

        self.prev         = None     # 同层的上一章节
        self.next         = None     # 同层的下一章节

        self.entry_file   = u""      # 本章节的第一个文件的路径
        self.content_file = u""      # 本章节的内容的路径（如果有的话）
#   }}}

#   {{{ -- class Book
class Book(ChapterInfo):
    def __init__(self):
        ChapterInfo.__init__(self)

        self.text_page    = u""         # 正文第一页
        self.meta_title   = u""         # 在opf文件中使用的标题
#   }}}

#   {{{ -- class ContentElement
class ContentElement(object):
    def __init__(self):
        pass

    def to_html(self, img_resolver):
        raise NotImplementedError()

    def to_asciidoc(self):
        raise NotImplementedError()

    def to_text(self):
        raise NotImplementedError()

    def content_size(self):
        raise NotImplementedError()

    def get_images(self):
        return list()
#   }}}

#  {{{ BlockContainer and subclasses

#   {{{ -- class BlockContainer
class BlockContainer(ContentElement):
    """ 可以包含若干行的部件 """
    def __init__(self, style_class=None):
        ContentElement.__init__(self)

        if not style_class:
            style_class = self.__class__.__name__

        self.style_class = style_class

        self.lines = list()

    def append_lines(self, lines):
        if lines:
            if isinstance(lines, list):
                self.lines.extend(lines)
            else:
                self.lines.append(lines)

    def to_html(self, img_resolver):
        html = u""

        if self.lines:
            if self.style_class:
                html += u'<div class="{0}">'.format(self.style_class)

            html += to_html(self.lines, img_resolver)

            if self.style_class:
                html += u'</div>'

        return html

    def to_asciidoc(self):
        return to_asciidoc(self.lines)

    def to_text(self):
        return to_text(self.lines)

    def content_size(self):
        return content_size(self.lines)

    def get_images(self):
        for img in get_images(self.lines):
            yield img
#   }}}

#   {{{ -- class StyledBlock
class StyledBlock(BlockContainer):
    """ 带样式的块 """
    def __init__(self, style_class, lines=None):
        BlockContainer.__init__(self, style_class)
        self.append_lines(lines)
#   }}}

#   {{{ -- class Literal
class Literal(BlockContainer):
    """ 需要缩进的内容，类似于引用 """
    def __init__(self, lines=None):
        BlockContainer.__init__(self, u"literal")
        self.append_lines(lines)

    def to_asciidoc(self):
        text = u""
        for line in self.lines:
            if isinstance(line, basestring):
                text += u"  " + line + u"\n\n"
            else:
                raise TypeError("Need string type, not {0} type".format(type(line)))

        return text

    def to_text(self):
        text = u""
        for line in self.lines:
            if isinstance(line, basestring):
                text += u"  " + line + u"\n"
            else:
                raise TypeError("Need string type, not {0} type".format(type(line)))

        return text
#   }}}

#   {{{ -- class Quote
class Quote(BlockContainer):
    """ 引用 """
    def __init__(self, lines=None, attribution="", citetitle=""):
        BlockContainer.__init__(self)
        self.attribution = attribution
        self.citetitle   = citetitle
        self.append_lines(lines)

    def to_html(self, img_resolver):
        html  = u'<blockquote>'
        html += to_html(self.lines, img_resolver)

        if self.citetitle:
            html += u'<div class="citetitle">{0}</div>'.format(escape(self.citetitle))

        if self.attribution:
            html += u'<div class="attribution">—— {0}</div>'.format(escape(self.attribution))

        html += u'</blockquote>'

        return html

    def to_asciidoc(self):
        text = u'[quote'

        if self.attribution:
            text += ','
            text += self.attribution

        if self.citetitle:
            text += ','
            text += self.citetitle

        text += u']\n'
        text += BlockContainer.to_asciidoc(self)
        return text

    def to_text(self):
        text = BlockContainer.to_text(self)

        ref = ""
        
        if self.attribution:
            ref = self.attribution

        if self.citetitle:
            if ref:
                ref += ','

            ref += self.citetitle

        if ref:
            text += '－－'
            text += ref
            text += '\n'

        return text
#   }}}

#   {{{ -- class Ruler
class Ruler(BlockContainer):
    """ <hr> """
    def __init__(self):
        BlockContainer.__init__(self)

    def to_html(self, img_resolver):
        return "<hr />"

    def to_asciidoc(self):
        return "'''''''''''''''''''''''''''''''''''\n\n"

    def to_text(self):
        return "--------------------\n"
#   }}}

#  }}}

#  {{{ InlineContainer and subclasses

#   {{{ -- class InlineContainer
class InlineContainer(ContentElement):
    """ 行内元素容器，所包含的元素会连接在一起 """
    def __init__(self, style_class=None):
        ContentElement.__init__(self)

        self.style_class = style_class
        self.sub_elements = list()

    def append_elements(self, sub_elements):
        def do_append(element):
            if isinstance(element, basestring):
                self.sub_elements.append(element)
            elif isinstance(element, InlineContainer):
                self.sub_elements.append(element)
            else:
                raise TypeError("Need string or InlineContainer type, not {0} type".format(type(element)))

        if sub_elements:
            if isinstance(sub_elements, types.GeneratorType) or isinstance(sub_elements, list):
                for e in sub_elements:
                    do_append(e)
            else:
                do_append(sub_elements)

    def to_html(self, img_resolver):
        html = u""

        if self.style_class:
            html += u'<span class="{0}">'.format(self.style_class)

        for e in self.sub_elements:
            if isinstance(e, basestring):
                html += escape(e)
            elif isinstance(e, InlineContainer):
                html += e.to_html(img_resolver)
            else:
                raise TypeError("Need string or InlineContainer type, no {0} type".format(type(e)))

        if self.style_class:
            html += u'</span>'

        return html

    def to_asciidoc(self):
        text = u""
        try:
            for e in self.sub_elements:
                if isinstance(e, basestring):
                    text += escape(e)
                elif isinstance(e, InlineContainer):
                    text += e.to_asciidoc()
                else:
                    raise TypeError("Need string or InlineContainer type, no {0} type".format(type(e)))
        finally:
            text = u"[{style_class}]##"
            if text:
                text = u"[{style_class}]##{text}##".format(
                    style_class=self.style_class,
                    text=text)

        return text

    def to_text(self):
        text = u""
        for e in self.sub_elements:
            if isinstance(e, basestring):
                text += escape(e)
            elif isinstance(e, InlineContainer):
                text += e.to_text()
            else:
                raise TypeError("Need string or InlineContainer type, no {0} type".format(type(e)))

        return text

    def content_size(self):
        return content_size(self.sub_elements)

    def get_images(self):
        for img in get_images(self.sub_elements):
            yield img
#   }}}

class FootNote(InlineContainer):
    def __init__(self, text):
        self.footnote_text = text
        InlineContainer.__init__(self, u"")

    def to_html(self, img_resolver):
        return u'<span class="inline-footnote">【注：{text}】</span>'.format(
            text=self.footnote_text)

    def to_asciidoc(self):
        return u" footnote:[{0}]".format(self.footnote_text)

    def to_text(self, img_resolver):
        return u'【注：{text}】'.format(text=to_text(self.tfootnote_text))

#   {{{ -- class StyledText
class StyledText(InlineContainer):
    """ 带样式的文本 """
    def __init__(self, style_class, sub_elements=None):
        InlineContainer.__init__(self, style_class)
        self.append_elements(sub_elements)
#   }}}

#   {{{ -- class QuotedText
class QuotedText(InlineContainer):
    """ 带样式的文本 """
    def __init__(self, style_class, quote_char, sub_elements=None):
        InlineContainer.__init__(self, style_class)
        self.quote_char = quote_char
        self.append_elements(sub_elements)

    def to_asciidoc(self):
        return self.quote_char + InlineContainer.to_asciidoc(self) + self.quote_char
#   }}}

#   {{{ -- class Line
class Line(InlineContainer):
    def __init__(self, elements):
        InlineContainer.__init__(self, u"")
        self.append_elements(elements)

    def to_html(self, img_resolver):
        return u"<p class='p'>" + InlineContainer.to_html(self, img_resolver) + u"</p>\n";

    def to_asciidoc(self):
        return InlineContainer.to_asciidoc(self) + u"\n\n"
#   }}}

#   {{{ -- class SectionTitle
class SectionTitle(InlineContainer):
    def __init__(self, title):
        InlineContainer.__init__(self, u"section_title")
        self.append_elements(title)

    def to_html(self, img_resolver):
        return u''.join((u'<p class="p section_title">', InlineContainer.to_html(self, img_resolver), u'</p>'))

    def to_asciidoc(self):
        return u"." + InlineContainer.to_asciidoc(self) + u"\n"
#   }}}

#   {{{ -- class Strong
class Strong(QuotedText):
    """ 加粗 """
    def __init__(self, sub_elements=None):
        QuotedText.__init__(self, u"strong", u"**")
        self.append_elements(sub_elements)
#   }}}

#   {{{ -- class Emphasized
class Emphasized(QuotedText):
    """ 强调 """
    def __init__(self, sub_elements=None):
        QuotedText.__init__(self, u"emphasized", u"__")
        self.append_elements(sub_elements)
#   }}}

#   {{{ -- class Monospaced
class Monospaced(QuotedText):
    """ 等宽 """
    def __init__(self, sub_elements=None):
        QuotedText.__init__(self, u"monospaced", u"++")
        self.append_elements(sub_elements)
#   }}}

#   {{{ -- class Superscript
class Superscript(InlineContainer):
    """ 上标 """
    def __init__(self, sub_elements=None):
        InlineContainer.__init__(self, u"")
        self.append_elements(sub_elements)

    def to_html(self, img_resolver):
        return u'<sup>' + InlineContainer.to_html(self, img_resolver) + u'</sup>\n';

    def to_asciidoc(self):
        return u"^" + InlineContainer.to_asciidoc(self) + u"^"
#   }}}

#   {{{ -- class Subscript
class Subscript(InlineContainer):
    """ 下标 """
    def __init__(self, sub_elements=None):
        InlineContainer.__init__(self, u"")
        self.append_elements(sub_elements)

    def to_html(self, img_resolver):
        return u'<sub>' + InlineContainer.to_html(self, img_resolver) + u'</sub>\n';

    def to_asciidoc(self):
        return u"~" + InlineContainer.to_asciidoc(self) + u"~"
#   }}}
#  }}}

#   {{{ -- class Table
class Table(ContentElement):
    """ 表格 """
    def __init__(self):
        ContentElement.__init__(self)
        self.rows = list()

    def append_row(self, cells):
        self.rows.append(cells)

    def to_html(self, img_resolver):
        html = u"<table class='normal'>\n"
        for row in self.rows:
            html += u"  <tr>\n"
            for cell in row:
                html += u"    <td>"
                html += to_html(cell, img_resolver) if cell else u"&nbsp;"
                html += u"</td>\n"

            html += u"  </tr>\n"

        html += u"</table>\n"
        return html

    def to_asciidoc(self):
        raise NotImplementedError()
        text = "\n"

        for row in self.rows:
            text += " | ".join(row)
            text += "\n"

        text += "\n"
        return text

    def get_images(self):
        for row in self.rows:
            for cell in row:
                for img in get_images(cell):
                    yield img
#   }}}
# }}}

# {{{ Img like classes
#   {{{ -- class ImgImpl
class ImgImpl(object):
    def __init__(self, unique_key, format="jpeg"):
        self.content_    = None
        self.id_         = u""
        self.width_      = -1
        self.height_     = -1
        self.is_loaded_  = False
        self.unique_key_ = unique_key
        self.format_     = format

    def load_content(self):
        raise NotImplementedError()
        return False

    def load_image(self):
        if not self.is_loaded_:
            self.is_loaded_ = True
            content = self.load_content()
            if content:
                f = StringIO(content)
                width, height = Image.open(f).size
                f.close()

                if width > 0 and height > 0:
                    self.content_ = content
                    self.width_   = width
                    self.height_  = height

    def is_valid(self):
        try:
            self.load_image()
        except:
            return False

        return self.width_ > 0 and self.height_ > 0

    def unique_key(self):
        return self.unique_key_

    def resize(self, maxWidth, maxHeight):
        self.load_image()

        if self.width_ > maxWidth or self.height_ > maxHeight:
            img = Image.open(StringIO(self.content_))

            if self.width_ * maxHeight > self.height_ * maxWidth:
                # 宽度更大，按宽度进行缩小
                resized = img.resize((maxWidth, self.height_ * maxWidth / self.width_), Image.ANTIALIAS)
            else:
                # 高度更大，按高度进行缩小
                resized = img.resize((self.width_ * maxHeight / self.height_, maxHeight), Image.ANTIALIAS)

            if resized:
                o = len(self.content_)
                f = StringIO()
                resized.save(f, self.format_)
                self.content_ = f.getvalue()
                self.width_, self.height_ = resized.size
                f.close()
#   }}}

#   {{{ -- class Img
class Img(object):
    def __init__(self, filename=u'', desc=u''):
        self.filename_  = filename
        self.extension_ = os.path.splitext(filename)[1].lower()
        self.desc_      = desc

    @classmethod
    def ext_to_format(cls, ext):
        if IMAGE_FORMAT_MAP.has_key(ext):
            return IMAGE_FORMAT_MAP[ext]

        return ext[1:].upper()

    def width(self):
        raise NotImplementedError()

    def height(self):
        raise NotImplementedError()

    def content(self):
        raise NotImplementedError()

    def extension(self):
        return self.extension_

    def filename(self):
        return self.filename_

    def desc(self):
        return self.desc_

    def set_id(self, id):
        raise NotImplementedError()

    def id(self):
        raise NotImplementedError()

    def unique_key(self):
        raise NotImplementedError()

    def is_valid(self):
        raise NotImplementedError()

    def resize(self, maxWidth, maxHeight):
        raise NotImplementedError()

#   }}}

#   {{{ -- class CachedImg
class CachedImg(Img):
    cache = dict()      # a dict of fullpath->image_data

    def __init__(self, impl, filename, desc=u""):
        super(CachedImg, self).__init__(filename, desc)

        unique_key = impl.unique_key()
        if self.cache.has_key(unique_key):
            self.impl_ = self.cache[unique_key]
        else:
            self.impl_ = impl
            self.cache[unique_key] = self.impl_

    def width(self):
        self.impl_.load_image()
        return self.impl_.width_

    def height(self):
        self.impl_.load_image()
        return self.impl_.height_

    def content(self):
        self.impl_.load_image()
        return self.impl_.content_

    def set_id(self, id):
        assert(not self.impl_.id_)
        self.impl_.id_ = id

    def id(self):
        return self.impl_.id_

    def unique_key(self):
        return self.impl_.unique_key()

    def is_valid(self):
        return self.impl_.is_valid()

    def resize(self, maxWidth, maxHeight):
        return self.impl_.resize(maxWidth, maxHeight);

#   }}}

#   {{{ -- class InputterImg
class InputterImg(CachedImg):
    class Impl(ImgImpl):
        def __init__(self, path, inputter=None):
            self.inputter_   = inputter if inputter else FileSysInputter("")
            self.path_       = path
            ImgImpl.__init__(self, self.inputter_.fullpath(path), Img.ext_to_format(os.path.splitext(path)[1].lower()))
            
        def load_content(self):
            return self.inputter_.read_binary(self.path_)

    def __init__(self, path, inputter=None, desc=u""):
        super(InputterImg, self).__init__(self.Impl(path, inputter), path, desc)
#   }}}

#   {{{ -- class MemImg
class MemImg(CachedImg):
    class Impl(ImgImpl):
        def __init__(self, content, format):
            ImgImpl.__init__(self, md5.new(content).hexdigest(), format)
            self.content_ = content

        def load_content(self):
            return self.content_

    def __init__(self, content, filename, desc=u""):
        super(MemImg, self).__init__(self.Impl(content, Img.ext_to_format(os.path.splitext(filename)[1].lower())), filename, desc)
#   }}}

#   {{{ -- class SuitableImg
class SuitableImg(Img):
    """ 从多张图片中选择最合适的一张.

    可以从多张图片中选择面积最大的一张。
    """
    def __init__(self, img, *imgs, **properties):
        super(SuitableImg, self).__init__(desc=properties['desc'] if properties.has_key('desc') else u'')
        self.imgs = [img, ]
        self.imgs.extend(imgs)
        self.selected = None

    def select_suitable_img(self):
        if not self.selected:
            largest_size = -1
            for img in self.imgs:
                if img.width() * img.height() > largest_size:
                    self.selected = img

    def width(self):
        self.select_suitable_img()
        return self.selected.width()

    def height(self):
        self.select_suitable_img()
        return self.selected.height()

    def content(self):
        self.select_suitable_img()
        return self.selected.content()

    def extension(self):
        self.select_suitable_img()
        return self.selected.extension()

    def filename(self):
        self.select_suitable_img()
        return self.selected.filename()

    def set_id(self, id):
        self.select_suitable_img()
        return self.selected.set_id(id)

    def id(self):
        self.select_suitable_img()
        return self.selected.id()

    def unique_key(self):
        self.select_suitable_img()
        return self.selected.unique_key()

    def is_valid(self):
        self.select_suitable_img()
        return self.selected.is_valid()

    def resize(self, maxWidth, maxHeight):
        self.select_suitable_img()
        return self.selected.resize(maxWidth, maxHeight)
#   }}}
# }}}

# {{{ Book info utilities

#   {{{ -- func book_file_name
def book_file_name(title, author, suffix):
    title = title.strip()
    if not title:
        title = u"unnamed"


    author = author.strip()
    if author:
        filename = u"{title} - {author}".format(title=unicode(title), author=unicode(author))
    else:
        filename = u"{title}".format(title=unicode(title))

    filename += unicode(suffix.strip())

    return filename
#   }}}

#   {{{ -- func parse_filename
def parse_filename(filename, title, author):
    if not title or not author:
        fileinfo = guess_title_author(filename)

        if title:
            fileinfo[title] = title

        if author:
            fileinfo[author] = author
    else:
        fileinfo = {
            "title": title,
            "author": author,
            "extra_info": "",
            "category": "",
        }

    return fileinfo
#   }}}

#   {{{ -- func guess_title_author
def guess_title_author(filename):
    re_ignored_extra_infos = (
        re.compile(u'chm', re.IGNORECASE),
        )
    re_extra_infos = (
        re.compile(u'(?<![作|编|著]者[:：])\((?P<info>[^)]*)\)', re.IGNORECASE),
        re.compile(u'(?<![作|编|著]者[:：])\[(?P<info>[^]]*)\]', re.IGNORECASE),
        re.compile(u'(?<![作|编|著]者[:：])［(?P<info>[^］]*)］', re.IGNORECASE),
        re.compile(u'(?<![作|编|著]者[:：])『(?P<info>[^』]*)』', re.IGNORECASE),
        re.compile(u'(?<![作|编|著]者[:：])【(?P<info>[^】]*)】', re.IGNORECASE),
        re.compile(u'(?<![作|编|著]者[:：])（(?P<info>[^）]*)）', re.IGNORECASE),
        re.compile(u'(?<=》)\s*(?P<info>v\d+(?:\.\d+)?)', re.IGNORECASE),
        )
    re_title_author_patterns = (
        re.compile(u'.*《(?P<title>[^》]+)》(?:[^:：]*[:：])?(?P<author>[^:：]+)', re.IGNORECASE),
        re.compile(u'.*《(?P<title>[^》]+)》(?P<author>.*)', re.IGNORECASE),           # 匹配只有《书名》的形式
        re.compile(u'.*《(?P<title>[^》]+)》[作|编|著]者\s*[:：]\s*(?P<author>.+)', re.IGNORECASE),      # 有'作者'字样
        re.compile(u'(?P<title>.+)[作|编|著]者\s*[:：]\s*(?P<author>.+)', re.IGNORECASE),      # 有'作者'字样
        re.compile(u'(?P<title>.+)[-－_＿:：](?P<author>.+)', re.IGNORECASE),          # -或_或:分隔
        re.compile(u'^(?P<title>[^ 　]+)[ 　]+(?P<author>.+)', re.IGNORECASE),         # 空格分隔
        )
    re_title_only_patterns = (
        re.compile(u'《(?P<title>[^》]+)》', re.IGNORECASE),
        )
    re_ignore_infos = (
        re.compile(u'\((全本|文字全本|校对全本|原创|美|日|英)\)', re.IGNORECASE),
    )

    name = os.path.splitext(os.path.basename(filename.strip(u'/')))[0]

    extra_info = "";
    erase_infos = []
    for re_extra_info in re_extra_infos:
        for m in re_extra_info.finditer(name):
            for re_ignored_extra_info in re_ignored_extra_infos:
                if re_ignored_extra_info.match(m.group("info")):
                    erase_infos.append(re_extra_info)
                    break
            else:
                extra_info = extra_info + "(" + m.group("info") + ")"
                erase_infos.append(re_extra_info)

    for re_extra_info in erase_infos:
        name = re_extra_info.sub(u"", name)

    for re_ignore_info in re_ignore_infos:
        extra_info = re_ignore_info.sub(u"", extra_info)

    title  = "";
    author = "";

    for pattern in re_title_author_patterns:
        m = pattern.match(name)
        if m:
            title  = m.group('title')
            author = m.group('author')
            title  = title.strip(u" 　\t- _－＿")
            author = author.strip(u" 　\t- _－＿")

            break
            #if title and author:
            #    break

    if not title or not author:
        title  = ""
        author = ""

        for pattern in re_title_only_patterns:
            m = pattern.match(name)
            if m:
                title  = m.group('title')
                title.strip(u" 　\t- _－＿")

                break

        if re.match(u'(?P<author>.+)(?:作品集|作品全集)', title):
            author  = m.group('author')

        if title:
            logging.debug(u"Guess title is '{title}', can't guess author from '{filename}'".format(
                title=title, filename=filename))
        else:
            logging.debug(u"Can't guess title/author from {filename}".format(filename=filename))
            title = name

    else:
        logging.debug(u"Guess title is '{title}', guess author is '{author}' from '{filename}'".format(
            title=title, author=author, filename=filename))

    return {"title": title, "author": author, "extra_info": extra_info, "category": ""}
#   }}}

#   {{{ -- func lookup_cover
def lookup_cover(title, author, exactly_match=False):
    def do_lookup_cover_in_dir(path, title, author):
        patterns = COVER_PATTERNS if author else TITLE_ONLY_COVER_PATTERNS
        for pattern in patterns:
            filename = pattern.format(title=title, author=author)
            for ext in COVER_EXTENSIONS:
                p = os.path.join(path, filename + ext)
                if os.path.exists(p):
                    return InputterImg(p)

    def do_lookup_cover(title, author):
        for cover_path in COVER_PATHS:
            cover = do_lookup_cover_in_dir(cover_path, title, author)
            if cover:
                return cover;

        return None

    if book_dir:
        cover = do_lookup_cover_in_dir(book_dir, title, author)
        if cover:
            return cover

        cover = do_lookup_cover_in_dir(book_dir, title, u"")
        if cover:
            return cover

    # 既考虑标题，又考虑作者
    if author:
        cover = do_lookup_cover(title, author)
        if cover:
            return cover

    if exactly_match:
        return None # Author not matched, lookup failed

    # 只考虑标题
    cover = do_lookup_cover(title, u"")
    if cover:
        return cover

    return None
#   }}}

#   {{{ -- func complete_book_info
def complete_book_info(book_info):
    re_title_cleanups = (
        re.compile(u'(?P<title>.+)(?:合集|全集|系列)', re.IGNORECASE),
    )

    re_category_map = (
        ( re.compile(u'文集|合集|合辑|全集|系列|作品集|小说集|部全', re.IGNORECASE), u'合集'),
        ( re.compile(u'恐怖', re.IGNORECASE), u'恐怖'),
        ( re.compile(u'科幻', re.IGNORECASE), u'科幻'),
        ( re.compile(u'玄幻|修真', re.IGNORECASE), u'玄幻'),
    )

#     {{{ ---- func lookup_zong_heng
    def lookup_zong_heng(title, author, encoding='utf-8'):
        class ZongHengImg(CachedImg):
            class Impl(ImgImpl):
                def __init__(self, book_url):
                    ImgImpl.__init__(self, book_url, "jpeg")
                    self.book_url_ = book_url
                    
                def load_content(self):
                    req = Request(self.book_url_)
                    req.add_header('Referer', 'http://www.zongheng.com')

                    logging.debug(u"Fetching book info page: {0}".format(self.book_url_))

                    f = urlopen(req)
                    s = f.read().decode(encoding)

                    re_cover = re.compile(
                        u'<div class="bortable wleft">\s*<a\s[^>]*>\s*<img[^>]*src="(?P<cover>[^"]+)"', 
                        re.IGNORECASE | re.MULTILINE)

                    m = re_cover.search(s)
                    if not m:
                        return None

                    cover_url = m.group('cover')
                    if not re.search('cover', cover_url):
                        return None

                    req = Request(cover_url)
                    req.add_header('Referer', self.book_url_)

                    logging.debug(u"Fetching book cover: {0}".format(cover_url))

                    f = urlopen(req)
                    return f.read()

            def __init__(self, book_url, desc=u""):
                CachedImg.__init__(self, self.Impl(book_url), "cover.jpg", desc)

        result = list()

        url = "http://search.zongheng.com/search/bookName/" + quote(title.encode(encoding)) + "/1.html"

        logging.debug(u"Fetching '{url}'".format(url=url))

        req = Request(url)
        req.add_header('Referer', 'http://www.zongheng.com')

        try:
            f = urlopen(req)
            s = f.read().decode(encoding)
        except:
            logging.debug(u"Fetch failed.")
            return result

        logging.debug(u"Fetch done.")

        for match in re.finditer(
                u'<div class="list">\s*' +
                u'<h1>\s*' + 
                u'<a[^>]*href="(?P<book_url>[^"]+)"[^>]*>(?P<title>.*?)</a>\s*' +
                u'</h1>\s*' +
                u'<p>\s*' +
                u'作者：<em><a[^>]*>(?P<author>.*?)</a></em>\s*' +
                u'分类：<em><a[^>]*>(?P<category>.*?)</a></em>\s*',
                s, re.IGNORECASE):
            result.append({
                'title'  : re.sub('<[^>]*>', '', match.group('title')),
                'author' : re.sub('<[^>]*>', '', match.group('author')),
                'l1cat'  : re.sub('<[^>]*>', '', match.group('category')),
                'l2cat'  : "",
                'cover'  : ZongHengImg(match.group('book_url'))
                })

        logging.debug(u"{0} results from zongheng.".format(len(result)))
        return result
#     }}}

#     {{{ ---- func lookup_qi_dian
    def lookup_qi_dian(title, author, encoding='utf-8'):
        result = list()

        url = "http://sosu.qidian.com/ajax/search.ashx"
        data = urlencode({
               "method"     : "getbooksearchlist", 
               "searchtype" : u"书名".encode(encoding), 
               "searchkey"  : title.encode(encoding)
               })

        logging.debug(u"Fetching '{url}' using '{data}'".format(url=url, data=data))

        req = Request(url + "?" + data)
        req.add_header('Referer', 'http://sosu.qidian.com')

        try:
            f = urlopen(req)
            s = f.read().decode(encoding)
        except:
            logging.debug(u"Fetch failed")
            return result

        logging.debug(u"Fetch done.")

        s = re.sub(u"</?b>|\\\\u003c/?b\\\\u003e", u"", s)
        try:
            books = json.loads(s)
        except Exception as e:
            logging.debug(u"Failed to decode QiDian: {0}".format(e))
            return result

        cover_inputter = UrlInputter("http://image.cmfu.com/books/")
        for book in books[0]:
            result.append({
                'title'  : book['BookName'],
                'author' : book['AuthorName'],
                'l1cat'  : book['CategoryName'],
                'l2cat'  : book['SubCategoryName'],
                'cover'  : InputterImg(u"{id}/{id}.jpg".format(id=book['BookId']), cover_inputter)
                })

        logging.debug(u"{0} results from qidian.".format(len(result)))
        return result
#     }}}

#     {{{ ---- func lookup_book_info
    def lookup_book_info(title, author):
        books = list()
        books.extend(lookup_qi_dian(title, author))
        books.extend(lookup_zong_heng(title, author))

        logging.debug(u"Total {0} results.".format(len(books)))

        match_book = None
        for book in books:
            if book["title"] == title:
                if book["author"] == author:
                    match_book = book
                    break

                # 记录只有书名相符的书
                if not match_book:
                    match_book = book
                    
        return match_book
#     }}}

#     {{{ ---- func local_lookup
    def local_lookup(title, author):
        bookinfo = None

        for b in BOOK_DB:
            # 标题必须一样，如果作者一样就是全匹配，否则如果前面没有匹配上才记录
            if title==b["title"] and (author==b["author"] or not bookinfo):
                bookinfo = dict()
                for k in b.keys():
                    bookinfo[k] = b[k]

                if author==b["author"]:
                    break

        if not bookinfo:
            return None

        if not bookinfo.has_key("cover"):
            bookinfo["cover"] = None

        return bookinfo
#     }}}

#     {{{ ---- func local_lookup_sqlite
    def local_lookup_sqlite(title, author):
        conn = sqlite3.connect(BOOK_DATABASE)
        cur = conn.cursor()
        cur.execute("select * from bookinfos where title=? and author=?")
        r = cur.fetchone()
        
        if not r:
            cur.execute("select * from bookinfos where title=?")
            r = cur.fetchone()

        if r:
            bookinfo = dict()
            for k in r.keys():
                bookinfo[k] = r[k]

            return bookinfo

        return None
#     }}}

    def fuzzy_lookup(title, author, func):
        r = func(title, author)
        if r:
            return r

        # 对于合集之类，把合集字样去掉再试一下
        for re_title_cleanup in re_title_cleanups:
            m = re_title_cleanup.match(title)
            if m:
                r = func(m.group('title'), author)
                if r:
                    return r

        return None

    title = book_info["title"]
    author = book_info["author"] if book_info.has_key("author") else u""

    cover = fuzzy_lookup(title, author, lookup_cover)
    if cover:
        book_info["cover"] = cover

    newinfo = fuzzy_lookup(title, author, local_lookup)
    if newinfo:
    # 把原来没有的项目拷贝过去
        for k in [ "author", "l1cat", "l2cat", "cover" ]:
            if (not book_info.has_key(k) or not book_info[k]) and (newinfo and newinfo.has_key(k) and newinfo[k]):
                book_info[k] = newinfo[k]

    if not options.offline:
        # 可以在线查信息，看看是否需要在线查找
        for k in [ "author", "l1cat", "cover" ]:
            if not book_info.has_key(k) or not book_info[k]:
                # 还有未知项目
                logging.info(u"Searching book information from internet for '{0}' ...".format(title))

                newinfo = fuzzy_lookup(title, author, lookup_book_info)

                # 把原来没有的项目拷贝过去
                for k in [ "author", "l1cat", "l2cat", "cover" ]:
                    if (not book_info.has_key(k) or not book_info[k]) and (newinfo and newinfo.has_key(k)):
                        book_info[k] = newinfo[k]

                break

    if not book_info['l1cat']:
        for (r,c) in re_category_map:
            if r.search(book_info['title']) or r.search(book_info['sub_title']):
                book_info['l1cat'] = c
                break
        
#   }}}
# }}}

# {{{ Code cleaner/normalizer

#   {{{ -- func unescape
##
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.
def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)
#   }}}

#   {{{ -- func reset_level
def reset_level(chapter, level):
    if hasattr(chapter, "level"):
        chapter.level = level

    for i in xrange(0, len(chapter.subchapters)):
        reset_level(chapter.subchapters[i], level + 1)
#   }}}

class HtmlContentNormalizer(object):
    #       {{{ -- 正式表达式常量
    re_content_line_sep = re.compile(r"(<\s*br\s*\/?>|(?:</?p(?:\s[^>]*|\s*)>)|\r|\n)+", re.IGNORECASE)
    re_content_cleanup_html = re.compile(r"<[^>]*>|\n|\r", re.IGNORECASE)
    re_content_img = re.compile(
        u"<img[^>]*?\ssrc=(?P<quote1>['\"])?(?P<url>.*?)(?(quote1)(?P=quote1)|(?=\s|>))" +
        u"(?:[^>]*\salt=(?P<quote2>['\"])?(?P<desc>.*?)(?(quote2)(?P=quote2)|(?=\s|>)))?" +
        u"[^>]*>",
        re.IGNORECASE | re.DOTALL)
        
    re_quote = re.compile(
        r"<(?P<tag>q|blockquote)\b[^>]*>(?P<content>.+?)<\s*/\s*(?P=tag)\s*>",
        re.IGNORECASE | re.DOTALL)
    re_bold = re.compile(
        r"<(?P<tag>b|strong)\b[^>]*>(?P<content>.+?)<\s*/\s*(?P=tag)\s*>",
        re.IGNORECASE | re.DOTALL)
    #       }}}

    def __init__(self, inputter, re_imgs=re_content_img):
        self.inputter  = inputter

        if not hasattr(re_imgs, '__iter__'):
            self.re_imgs = [re_imgs]
        else:
            self.re_imgs  = re_imgs

    def normalize(self, line, inputter=None):
        if not line:
            return list()

        return list(
                functools.partial(self._normalize_styled_content, self.re_quote, Quote, inputter, 
                    functools.partial(self._normalize_styled_content, self.re_bold, Strong, inputter, 
                        functools.partial(self._normalize_block_content, inputter)))
                    (line))

    def _normalize_styled_content(self, re, cls, inputter, next_proc, line):
        start_pos = 0
        for m in re.finditer(line):
            if m.start() > start_pos:
                for l in next_proc(line[start_pos:m.start()]):
                    yield l

            quote_lines = next_proc(m.group('content'))
            if quote_lines:
                yield cls(quote_lines)

            start_pos = m.end()

        # 加入最后的内容
        if start_pos < len(line):
            for l in next_proc(line[start_pos:]):
                yield l

    def _normalize_block_content(self, inputter, block_content):
        for line in self.re_content_line_sep.split(block_content):
            line = line.strip()
            if line:
                for l in self._normalize_line(inputter, line):
                    yield l

    def _normalize_line(self, inputter, line):
        if not inputter:
            inputter = self.inputter

        # 找出所有可能的图片位置
        img_pos = list()
        
        for re_img in self.re_imgs:
            for m in re_img.finditer(line):
                img_pos.append({
                    "start" : m.start(),
                    "end" : m.end(),
                    "url" : m.group("url"),
                    "desc" : title_normalize_from_html(m.group("desc")) if m.groupdict().has_key("desc") else u"",
                })

        # 对img_pos按开始位置进行排序
        img_pos.sort(key=lambda pos: pos["start"])

        start_pos = 0
        for pos in img_pos:
            if pos["start"] < start_pos:     # 有可能两个re_imgs的结果有重叠，取前一个。后一个结果将忽略
                continue

            if pos["start"] > start_pos:    # 马上就是图片，不需要处理两张图片之间的内容
                # 加入图片之前的文本
                for l in self._to_text(line[start_pos:pos["start"]]):
                    yield l

            # 加入图片
            yield InputterImg(pos["url"], inputter, title_normalize(pos["desc"]))

            start_pos = pos["end"]

        # 加入行末的内容
        if start_pos < len(line):
            for l in self._to_text(line[start_pos:]):
                yield l

    def text_only(self, line):
        lines = list()

        if not line:
            return lines

        for l in self.re_content_line_sep.split(line):
            lines.extend(self._to_text(l))

        return lines

    def _to_text(self, line):
        return content_text_normalize(unescape(self.re_content_cleanup_html.sub(u"", line)))

#   {{{ -- func content_text_normalize
#       {{{ -- 正式表达式常量
re_content_skip_lines = re.compile(u"^[　 \t]*$")
re_indent_cleanups = [
    #[ re.compile(u"^[ ]{1,6}([^　 \ta-zA-Z])"), u"　　\\1" ],   # 行首的1到6个半角空格规范为两个全角空格
    #[ re.compile(u"^[ ]{1,6}([^　 \t])"), u"　　\\1" ],   # 行首的1到6个半角空格规范为两个全角空格
    #[ re.compile(u"^[　]{0,3}([^　 \t])"), u"　　\\1" ],        # 行首的0到3个全角空格规范为两个全角空格
    [ re.compile(u"^[　 \t]+"), u"" ], # 去掉前面的缩进，使用CSS控制缩进
]
#       }}}

def content_text_normalize(lines):
    content = list()

    if isinstance(lines, basestring):
        lines = [ lines ]

    for line in lines:
        if isinstance(line, basestring):
            for l in line.splitlines():
                for r in re_indent_cleanups:
                    l = r[0].sub(r[1], l)

                if re_content_skip_lines.match(l):
                    continue

                content.append(l)
        else:
            content.append(line)

    return content

def literal_text_normalize(lines):
    content = list()

    if isinstance(lines, basestring):
        lines = [ lines ]

    for line in lines:
        if isinstance(line, basestring):
            for l in line.splitlines():
                if re_content_skip_lines.match(l):
                    continue

                content.append(l)
        else:
            content.append(line)

    return content
#   }}}

#   {{{ -- func trim
def trim(line):
    return re.sub(u"^[ \t　]+|[ \t　]+$", u"", line)
#   }}}

#   {{{ -- func urldecode
def urldecode(url):
    rex = re.compile('%([0-9a-hA-H][0-9a-hA-H])',re.M)
    return rex.sub(lambda m: chr(int(m.group(1),16)), url.encode("utf-8")).decode("utf-8")
#   }}}

#   {{{ -- func is_alphanum
def is_alphanum(char):
    return char >= 'a' and char <= 'z' or char >= 'A' and char <= 'Z' or char >= '0' and char <= '9'
#   }}}

#   {{{ -- func title_normalize
def title_normalize(title):
    if not title:
        return u""

    return re.sub(u"^(·|○)+|(·|○)+$|^[ 　]+|[ 　]$", u"", title, re.IGNORECASE)
#   }}}

#   {{{ -- func title_normalize_from_html
def title_normalize_from_html(title):
    if not title:
        return u""

    if isinstance(title, basestring):
        return re.sub(u"(?i)^(·|○)+|(·|○)+$|^[ 　]+|[ 　]$", u"", unescape(re.sub(u"<[^>]*>", u"", title)))
    
    return [ title_normalize_from_html(t) for t in title ]
#   }}}
# }}}

# {{{ Inputters
class Inputter(object): # {{{
    def __init__(self, default_encoding=""):
        ## 入口文件
        #  如果指定了，就应该解释这个文件，而不是index.html等
        self.entry = u""
        self.default_encoding = default_encoding
        self.last_encoding = ""    # 最近用过的编码，先尝试这个编码，不行的话再试其它
        self.nested_level = 0

    def read_binary(self, filename):
        raise NotImplementedError()

    def read_all(self, filename, encoding=None):
        binary = self.read_binary(filename)

        for enc in (encoding, self.last_encoding, self.default_encoding, "utf-8", "GB18030"):
            if enc:
                try:
                    u = unicode(binary, enc)
                    self.last_encoding = enc
                    return u
                except UnicodeDecodeError:
                    pass

        # 解释不成功，用chardet模块尝试查找编码
        logging.info("Checking with chardet")
        encoding = chardet.detect(binary)["encoding"]

        if not encoding:
            encoding = self.last_encoding if self.last_encoding else DEFAULT_ENCODING

            logging.info(u"  Unable to detect encoding for '{0}', using {1}".format(self.fullpath(filename), encoding))
        else:
            logging.info(u"  encoding is {0} for '{1}'".format(encoding, self.fullpath(filename)))

        u = unicode(binary, encoding, 'ignore')     # 可能有部分字符有问题，允许部分编码错误
        last_encoding = encoding
        return u

    def read_lines(self, filename, encoding=None):
        return self.read_all(filename, encoding).splitlines(False)

    def fullpath(self, filename=None):
        raise NotImplementedError()

    def is_subpath(self, path, root=u""):
        raise NotImplementedError()
#   }}}

class FileSysInputter(Inputter): # {{{
    def __init__(self, basedir=u"", encoding=""):
        super(FileSysInputter, self).__init__(encoding)

        if os.path.isfile(basedir):
            self.basedir   = os.path.normpath(os.path.normpath(os.path.dirname(basedir)))
            self.entry     = os.path.basename(basedir)
        else:
            self.basedir   = os.path.normpath(basedir)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read_binary(self, filename):
        fullpath = os.path.normpath(os.path.join(self.basedir, filename))

        # url中可能带#号，因此在文件找不到时，可以试一下去掉文件名中的#号
        if not os.path.isfile(fullpath):
            fullpath = re.sub(u"#.*", u"", fullpath)

        with open(os.path.normpath(os.path.join(self.basedir, filename)), u"r") as fp:
            return fp.read()

    def exists(self, filename):
        full_filename = self.fullpath(filename)
        return os.path.exists(full_filename);

    def isfile(self, filename):
        full_filename = self.fullpath(filename)
        return os.path.exists(full_filename) and os.path.isfile(full_filename)

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return os.path.normpath(os.path.join(self.basedir, filename))

    def is_subpath(self, path, root=u""):
        return self.fullpath(path).startswith(self.fullpath(root))
#   }}}

g_idx = 0
class ChmInputter(Inputter): # {{{
    def __init__(self, filename, encoding=""):
        def callback(cf,ui,lst):
            lst.append(ui.path)
            return CHM_ENUMERATOR_CONTINUE

        super(ChmInputter, self).__init__(encoding)

        self.filename = filename
        self.chmfile = CHMFile()
        self.chmfile.LoadCHM(filename.encode(sys.getfilesystemencoding()))
        self.entry = self.chmfile.home if self.chmfile.home != "/" else ""

        filelist = list()
        ok=chm_enumerate(self.chmfile.file, CHM_ENUMERATE_ALL, callback, filelist)
        if not ok:
            raise Exception("chmlib.chm_enumerate failed")

        for enc in (encoding, "utf-8", "GB18030"):
            if enc:
                try:
                    self.filelist = [ unicode(f, enc) for f in filelist ]
                    break
                except UnicodeDecodeError:
                    pass
        else:
            self.filelist = filelist

        self.filelist.sort()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.chmfile:
            self.chmfile.CloseCHM()

    def read_binary(self, filename):
        filename = os.path.normpath(filename)
        result, ui = self.chmfile.ResolveObject(os.path.join(u"/", filename).encode("utf-8"))
        if (result != CHM_RESOLVE_SUCCESS):
            raise Exception(u"Failed to resolve {0}: {1}".format(filename, result))

        size, content = self.chmfile.RetrieveObject(ui)
        if (size != ui.length):
            raise Exception(u"Failed to retrieve {0}: filesize is {1}, only got {2}".format(filename, ui.length, size))

        return content

    def exists(self, filename):
        filename = os.path.join(u"/", os.path.normpath(filename))

        # 文件是否存在
        idx = bisect_left(self.filelist, filename)

        if idx != len(self.filelist) and self.filelist[idx] == filename:
            return True

        # 看看是不是目录
        if not filename.endswith(u"/"):
            filename += os.path.sep
            idx = bisect_left(self.filelist, filename)
            if idx != len(self.filelist) and self.filelist[idx].startswith(filename):
                return True

        return False

    def isfile(self, filename):
        filename = os.path.normpath(filename)
        result, ui = self.chmfile.ResolveObject(os.path.join(u"/", filename).encode("utf-8"))
        return result == CHM_RESOLVE_SUCCESS

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return os.path.normpath(os.path.join(self.filename, filename))

    def is_subpath(self, path, root=u""):
        return self.fullpath(path).startswith(self.fullpath(root))
#   }}}

class UrlInputter(Inputter): # {{{
    def __init__(self, baseurl=u"", encoding=""):
        super(UrlInputter, self).__init__(encoding)

        m = re.match(u"(.*?://.*/)([^/]*)$", baseurl)
        if m:
            self.baseurl = m.group(1)
            self.entry   = m.group(2)
        else:
            self.baseurl = baseurl

        self.cache = dict()

        # 处理cookies
        self.cookie_jar = cookielib.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

        # 看看要不要登录
        for web_info in WEB_INFOS:
            if web_info["pattern"].match(baseurl):
                # 找到了相应的项目
                if web_info.has_key("login_url"):
                    # 需要登录
                    authInfo = None

                    # 找登录信息
                    for password in PASSWORDS:
                        if password["pattern"].match(baseurl):
                            authInfo = password
                            break

                    data = web_info["post_data"]
                    if data:
                        data = data.format(**authInfo)
                    else:
                        data = None

                    req = Request(web_info["login_url"], data)
                    if web_info.has_key("referer"):
                        req.add_header('Referer', web_info["referer"])

                    logging.debug(u"Login {url}".format(url=web_info["login_url"]))

                    try:
                        f = self.opener.open(req)
                        c = f.read()
                    except Exception as e:
                        raise IOError(u"Failed to retrieve {0}: {1}".format(web_info["login_url"], e))

                    #print unicode(c, 'utf-8')

                break

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read_binary(self, filename):
        url = basejoin(self.baseurl, filename)

        if self.cache.has_key(url):
            return self.cache[url]

        logging.debug(u"          Fetching url '{0}'".format(url))

        req = Request(url)
        req.add_header('Referer', url)

        for i in xrange(0, HTTP_RETRY):
            try:
                f = self.opener.open(req)
                c = f.read()
                self.cache[url] = c
                return c
            except:
                pass
        else:
            raise IOError(u"Failed to retrieve {0}".format(url))

    def exists(self, filename):
        return True;

    def isfile(self, filename):
        return filename[-1:] != "/"

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return basejoin(self.baseurl, filename)

#   }}}

class SubInputter(Inputter): # {{{
    def __init__(self, inputter, root):
        super(SubInputter, self).__init__(inputter.default_encoding)

        self.inputter = inputter
        self.nested_level = inputter.nested_level + 1

        # 指定了一个文件，该文件作为入口文件
        if inputter.isfile(root):
            self.root  = os.path.dirname(root)
            self.entry = os.path.basename(root)
        else:
            self.root  = root
            self.entry = u""

    def __enter__(self):
        self.inputter.__enter__()
        return self

    def __exit__(self, *args):
        self.inputter.__exit(*args)

    def read_binary(self, filename):
        try:
            return self.inputter.read_binary(os.path.join(self.root, filename))
        except:
            log.error(u"root: '{0}' filename: '{1}' fullpath: '{2}'".format(
                    self.root, filename, self.fullpath(filename)))
            raise

    def exists(self, filename):
        return self.inputter.exists(os.path.join(self.root, filename))

    def isfile(self, filename):
        return self.inputter.isfile(os.path.join(self.root, filename))

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return self.inputter.fullpath(os.path.join(self.root, filename))

    def is_subpath(self, path, root=u""):
        return self.inputter.is_subpath(os.path.join(self.root, path), self.root)
#   }}}
# }}}

# {{{ Parsers
class Parser(object): # {{{
    re_cover = re.compile(u"<img\s*src=(?P<quote1>['\"])?(?P<src>.*?)(?(quote1)(?P=quote1)|(?=\s|>))", re.IGNORECASE)

    def parse(self, inputter, top_level, book_title=u"", book_author=u""):
        raise NotImplementedError(u"Parser::parse() is not implemented!")

    def extract_image_path(self, htmls):
        """ 从html中提取出img的路径

        Args:
            htmls - html片段或者路径，可以为数组或者字符串

        Returns:
            htmls中各项对应的路径。如果htmls是数组则返回相同长度的数组，否则将返回单个字符串
        """
        is_list = True
        if isinstance(htmls, basestring):
            htmls = [htmls,]
            is_list = False

        image_paths = list()

        for html in htmls:
            m = self.re_cover.match(html)
            if m:
                image_paths.append(m.group("src"))
            else:   # 也可以直接提供图片的路径
                image_paths.append(html)

        return image_paths if is_list else image_paths[0]

    # 如果有多张封面，使用最大的一张
    def parse_cover(self, paths, inputter):
        if isinstance(paths, basestring):
            paths = [paths,]

        covers = list()

        for cover_filename in paths:
            if inputter.isfile(cover_filename):
                cover = InputterImg(cover_filename, inputter)
                if cover.width() > 0 and cover.height() > 0 and \
                        min(cover.width(), cover.height()) * MAX_COVER_ASPECT_RATIO > max(cover.width(), cover.height()):
                    covers.append(InputterImg(cover_filename, inputter))

        if not covers:
            return None
        elif len(covers) > 1:
            return SuitableImg(*covers, desc=u'')
        else:
            return covers[0]

    @classmethod
    def parse_book(cls, inputter, top_level, title=u"", author=u"", cover=None):
        logging.debug(u"{indent}Searching suitable parse for {path}".format(
                indent=u"      "*inputter.nested_level, path=inputter.fullpath()))

        parsed_files[inputter.fullpath()] = True

        if isinstance(inputter, UrlInputter):
            # 看看有没有与url对应的解释器
            for web_info in WEB_INFOS:
                if web_info["pattern"].match(inputter.fullpath()):
                    parser = globals()[web_info["parser"]]()
                    logging.debug(u"{indent}  Checking '{path}' with {parser}.".format(
                        path=inputter.fullpath(), parser=parser.__class__.__name__, indent=u"      "*inputter.nested_level))

                    try:
                        book = parser.parse(inputter, top_level, title, author)
                        if book:
                            return book
                    except NotParseableError as e:
                        # try next parser
                        logging.error(u"{indent}    {path} should be parsed with {parser}, but failed: {error}!".format(
                            path=inputter.fullpath(), indent=u"      "*inputter.nested_level, parser=parser.__class__.__name__, error=e))

                        raise NotParseableError(u"{file} is not parseable by any parser".format(file=inputter.fullpath()))
                    
        for parser in (AsciidocParser(), HtmlBuilderCollectionParser(), EasyChmCollectionParser(), EasyChmCollectionParser2(), IFengBookParser(), EasyChmParser(), HtmlBuilderParser(), RedirectParser()):
            logging.debug(u"{indent}  Checking '{path}' with {parser}.".format(
                path=inputter.fullpath(), parser=parser.__class__.__name__, indent=u"      "*inputter.nested_level))

            try:
                book = parser.parse(inputter, top_level, title, author)
                if book:
                    # 指定了封面
                    if cover and not book.cover:
                        book.cover = cover

                    # 找一下书本目录下有没有cover.jpg
                    if not book.cover:
                        if book_dir:
                            for ext in COVER_EXTENSIONS:
                                p = os.path.join(book_dir, "cover" + ext)
                                if os.path.exists(p):
                                    book.cover = InputterImg(p)

                    # 封面库中有没有这本书的封面
                    if not book.cover:
                        book.cover = lookup_cover(book.title, book.author)

                    # 取第一个子章节的封面
                    if not book.cover and book.subchapters and book.subchapters[0].cover:
                        book.cover = book.subchapters[0].cover

                    return book
            except NotParseableError as e:
                # try next parser
                pass

        logging.error(u"{indent}    {path} is not parseable by any parser".format(
            path=inputter.fullpath(), indent=u"      "*inputter.nested_level))

        raise NotParseableError(u"{file} is not parseable by any parser".format(file=inputter.fullpath()))

#   }}}

class HtmlBuilderParser(Parser): # {{{
    re_idx_comment = re.compile(u"<!--.*?-->")
    re_idx_toc     = re.compile(u".*<font class=f3>[^<]+", re.IGNORECASE)
    re_idx_intro   = re.compile(u".*<td\s+[^>]*\\bclass=m5\\b>(.+?)</td>", re.IGNORECASE)

    re_idx_levels  = (
        ( re.compile(u".*<td[^>]*class=m6[^>]*>(?P<title>[^<]+)</td>", re.IGNORECASE), 
          re.compile(u".*<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*>\s*<p[^>]*>\s*(?P<title>.+?)\s*</td>\s*</tr>\s*</table>", re.IGNORECASE),
          #<p align="center"><font size="3"><font color="#915788">↘</font><span class=f1><font face="楷体_GB2312" color="#915788">悬疑卷</font></span><font color="#915788">↙</font></font></td>
          #<font color="#915788" size="3">↘</font><font size="3" face="楷体_GB2312" color="#915788">灵异小故事集</font><font color="#915788" size="3">↙</font></span></td>
          re.compile(u".*<font[^>]*>↘(?:</?(?:font|span)[^>]*>)+(?P<title>[^<\s][^<]+)(?:</?(?:font|span)[^>]*>)+↙<", re.IGNORECASE),
        ),
        ( re.compile(u".*<td[^>]*class=m2[^>]*>(?P<title>[^<]+)</td>", re.IGNORECASE), ),
    )
    re_idx_details  = (
        re.compile(u".*?<td[^>]*>\s*(?:<font[^>]*>(?:&nbsp;|　|\s)*)<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?P<title>\S[^<]*?)<img[^>]+src=\"(?P<cover>[^\"]+)\"[^>]*>\s*</A>.*?</td>", re.IGNORECASE),
        re.compile(u".*?<td[^>]*>(?:&nbsp;|　|\s)*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?P<title>\S[^<]+)</A>.*?</td>", re.IGNORECASE),
        # <td><font size="2"> <A HREF="刘慈欣003.htm" > <font color="#800000">【1】远航！远航！</font></A></font></td>
        # <td width="217"><font size="2"> <A HREF="刘慈欣004.htm" > <font color="#800000">【2】<span style="letter-spacing: -1pt">《东京圣战》和《冷酷的方程式》</span></font></A></font></td>
        # <td><font color="#0000FF">&nbsp;</font><A HREF="刘慈欣000.htm" ><font color="#0000FF">★刘慈欣资料</font></A></td>
        re.compile(u".*?<td[^>]*>\s*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?P<title>.+?)</A>(?:&nbsp;|　|…|\s)*(?:\d*\s*)?</td>", re.IGNORECASE),
        re.compile(u".*?<td[^>]*>\s*(?:<font[^>]*>(?:&nbsp;|　|\s)*)<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?P<title>.+?)</A>(?:&nbsp;|　|…|\s)*(?:\d*\s*)?(?:</font[^>]*>(?:&nbsp;|　|\s)*)</td>", re.IGNORECASE),
        re.compile(u".*?<td[^>]*>\s*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?:<font[^>]*>(?:&nbsp;|　|\s)*)?(?P<title>.+?)(?:</font[^>]*>(?:&nbsp;|　|\s)*)?</A>(?:&nbsp;|　|…|\s)*(?:\d*\s*)?</td>", re.IGNORECASE),
        #re.compile(u"<td[^>]*>\s*(?:</?font[^>]*>(?:&nbsp;|　|\s)*)*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?:</?font[^>]*>\s*)*(?P<title>.+?)(?:</?font[^>]*>\s*)*</A>(?:&nbsp;|　|…|\s)*(?:\d*\s*)?(?:</?font[^>]*>\s*)*</td>", re.IGNORECASE | re.DOTALL),
        # <font color="#000000">·</font><A HREF="mydoc001.htm" >第02章 春雪</A><BR>
        re.compile(u".*?</font><A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>\s*(?:<font[^>]*>(?:&nbsp;|　|\s)*)?(?P<title>.+?)(?:</font[^>]*>(?:&nbsp;|　|\s)*)?</A>", re.IGNORECASE),
        # <a href=index1.html class=f5 title=卷一☆点击进入>灵魂上载</a><br>
        re.compile(u".*<A[^>]*HREF=(?P<quote1>['\"])?(?P<url>.+?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*?title=(?P<quote2>['\"])?(?:.+?点击进入)(?(quote2)(?P=quote2)|(?=\s|>))[^>]*>\s*(?P<title>.+?)</A>\s*<BR>", re.IGNORECASE),
    )

    re_title = re.compile(r"\s*<title>\s*([^<]+)\s*", re.IGNORECASE)
    re_content_begin = re.compile(r"<!--(?:HTMLBUILERPART|BookContent Start).*?-->")
    re_content_end = re.compile(r"<!--(?:/HTMLBUILERPART|BookContent End).*?-->")
    re_ignore_title = re.compile(u"上页|下页|上一页|下一页|目录|回目录|回封面")
    re_subbook_url  = re.compile(u".*/index\.html", re.IGNORECASE)

    #<html><head><title></title></head><BODY leftMargin=0 topMargin=0 marginheight=0 marginwidth=0 style="overflow:hidden"><iframe frameborder=0 style="width:100%;height:100%" src="chm/000015/List.htm"><a href="chm/000015/List.htm">点此进入</a></iframe></body></html>
    re_redirects = (
        re.compile(r"<iframe\b[^>]*\bsrc=\"(?P<url>[^\"]+)\"[^>]*>\s*<a href=\"\1\">", re.IGNORECASE | re.MULTILINE),
        re.compile(r"<center[^>]*>\s*<a[^>]+href=\"(?P<url>[^\"]+)\"[^>]*>\s*<img[^>]+src=\"(?P<cover>[^\"]+)\"[^>]*>\s*</a>\s*</center>", re.IGNORECASE | re.DOTALL),
    )

    # <td align=center><img src=../image4/nkts.jpg class=p1 alt=南柯太守></td>
    #re_img_list = re.compile(u".*<td[^>]*><img src=(?P<src>[^'\" \t]+) class=[^>]* alt=(?P<desc>[^> ]+)></td>")

    class ContentNormalizer(HtmlContentNormalizer):
        re_section_title = re.compile(u"^\s*<font class=f10>(?P<title>[^<]+)</font>\s*$")

        def _normalize_line(self, inputter, line):
            m = self.re_section_title.match(line)
            if m:
                lines = list()
                lines.append(SectionTitle(title_normalize_from_html(m.group("title"))))
                return lines

            return HtmlContentNormalizer._normalize_line(self, inputter, line)

    def _get_index_filenames(self, inputter):
        index_filenames = list()
        
        if inputter.entry:
            return [{"url":inputter.entry, "cover":None}]
        else:
            for i in (u"cover.html", u"cover.htm", u"index.html", u"index.htm", u"tempbook.htm", ):
                if inputter.isfile(i):
                    index_filenames.append({"url":i, "cover":None})

        if inputter.isfile(u"index1.html"):
            i = 1
            while True:
                filename = u"index{0}.html".format(i)
                if not inputter.isfile(filename):
                    break;
                
                index_filenames.append({"url":filename, "cover":None})
                i += 1

        return index_filenames

    def parse(self, inputter, top_level, book_title, book_author):
        normalizer = self.ContentNormalizer(inputter=inputter)

        def read_chapter(inputter, filename, indent):
            logging.debug(u"{indent}    Parsing file {filename}...".format(filename=filename, indent=u" "*indent));

            chapter = Chapter()

            is_in_content = False

            try:
                for line in inputter.read_lines(filename):
                    while line:
                        if not chapter.title:
                            m = self.re_title.match(line)
                            if m:
                                chapter.title = title_normalize_from_html(m.group(1))
                                line = line[m.end():]
                                continue
                        
                        # 在正文内容中
                        if is_in_content:
                            m = self.re_content_end.search(line)
                            if not m:
                                chapter.content.extend(normalizer.normalize(line))
                                break

                            # 出现正文结束标志，但前半行可能有内容
                            chapter.content.extend(normalizer.normalize(line[0:m.start()]))
                            is_in_content = False
                            line = line[m.end():]

                        # 检查正文内容的开始
                        m = self.re_content_begin.search(line)
                        if m:
                            is_in_content = True
                            # 后半行可能有内容
                            line = line[m.end():]
                            continue

                        # 处理下一行
                        break
            except:
                logging.debug(u"{indent}    {file} is not parseable by {parser}. '{chapter}' is not readable".format(
                    file=os.path.join(inputter.fullpath(), filename), parser=self.__class__.__name__,
                    chapter=filename, indent=u"      "*inputter.nested_level))

            if len(chapter.content) == 0:
                logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                    file=os.path.join(inputter.fullpath(), filename), parser=self.__class__.__name__,
                    indent=u"      "*inputter.nested_level))

                raise NotParseableError(u"{file} is not parseable by {parser}".format(
                    file=os.path.join(inputter.fullpath(), filename), parser=self.__class__.__name__))

            #logging.debug(u"        Title: {0}".format(chapter.title))
            return chapter

        index_filenames = self._get_index_filenames(inputter)
        if not index_filenames:
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        i = 0
        while i < len(index_filenames):
            file_content = inputter.read_all(index_filenames[i]["url"])
            for re_redirect in self.re_redirects:
                logging.debug(u"    Checking '{0}' against redirect '{1}'...".format(index_filenames[i]["url"], re_redirect.pattern))
                m = re_redirect.search(file_content)
                if m:   # 这个文件是重定向文件，以重定向后的文件为准
                    url = m.group("url")
                    try:
                        cover = m.group("cover")
                        if cover:
                            cover = InputterImg(cover, inputter)
                        else:
                            cover = None
                    except:
                        cover = None

                    logging.info(u"{indent}    {src} is redirected to {dest}".format(
                        indent=u"      "*inputter.nested_level, src=index_filenames[i]["url"], dest=url))

                    for f in index_filenames:
                        if f["url"] == url:
                            if not f["cover"] and cover:
                                f["cover"] = cover
                            break
                    else:
                        index_filenames.append({"url":url, "cover":cover})

                    del index_filenames[i]
                    break
            else:
                i += 1

        intro = None
        root_chapter = Chapter()
        root_chapter.level = top_level - 1
        cover = None

        for index_filename in index_filenames:
            logging.info(u"{indent}    Parsing index file: {filename}...".format(filename=index_filename["url"], indent=u"      "*inputter.nested_level))

            if index_filename["cover"] and not cover:
                cover = index_filename["cover"]

            chapter_stack = [root_chapter]

            status = 0

            file_content = inputter.read_all(index_filename["url"])

            chapter_inputter = inputter
            dirname = os.path.dirname(index_filename["url"])
            if dirname:
                chapter_inputter = SubInputter(inputter, dirname)
                # 不需要缩进
                chapter_inputter.nested_level -= 1

            next_pos = 0   # 开始处理的位置
            while next_pos < len(file_content):
                # 每次循环都尝试每一个正则表达式，有匹配的就处理，没有的话就跳到下一行
                # next_pos指明了下一个处理点（或下一行的开始）
                start_pos = next_pos

                # 由于从2.7开始，re.match()才支持startPos参数，因此只能对字符串进行裁断
                file_content = file_content[start_pos:]

                # 下次缺省从下个换行开始处理。因此要找到下个换行的位置作为next_pos的缺省值
                m = re.search("[\r\n]+", file_content)
                if m:
                    next_pos = m.end()
                else:
                    next_pos = len(file_content)

                if status == 0:         # before 目录
                    m = self.re_idx_toc.match(file_content)
                    if m:
                        next_pos = m.end()

                        status = 1
                        logging.debug(u"{indent}      Header skipped".format(indent=u"      "*inputter.nested_level))
                        continue

                if status == 1 and not intro:     # 未读入章节内容，允许有概要
                    m = self.re_idx_intro.match(file_content)
                    if m:
                        next_pos = m.end()

                        logging.debug(u"{indent}      Found intro".format(indent=u"      "*inputter.nested_level))
                        intro = Chapter()
                        intro.title = BOOK_INTRO_TITLE
                        intro.content = normalizer.text_only(m.group(1))
                        continue

                process_next_line = False
                for idx,r in enumerate(self.re_idx_details):
                    m = r.match(file_content)
                    if m:
                        chapter_filename = m.group("url")
                        chapter_title    = title_normalize_from_html(m.group("title"))

                        logging.debug(u"    match #{idx} '{re}'".format(idx=idx, re=r.pattern))
                        if chapter_filename == "#":
                            continue

                        if len(chapter_title) == 0:
                            logging.warning(u"{indent}      No title found, ignoring url '{url}' in file '{filename}'".format(
                                url=chapter_filename, filename=index_filename["url"], indent=u"      "*inputter.nested_level))

                            continue

                        if self.re_ignore_title.match(chapter_title):
                            continue;

                        status = 2

                        try:
                            chapter = read_chapter(chapter_inputter, chapter_filename, inputter.nested_level * 6 + (chapter_stack[-1].level + 1) * 2)
                            if not chapter:
                                logging.warning(u"{indent}      Content not found for {title}: {filename}".format(
                                    title=chapter_title, filename=chapter_filename, indent=u"      "*inputter.nested_level))
                                raise NotParseableError(u"Content not found for {title}: {filename}".format(
                                    title=chapter_title, filename=chapter_filename, indent=u"      "*inputter.nested_level))
                        except NotParseableError as e:
                            # 有些书使用re_idx_details来作为子书的链接，因此也要试一下
                            try:
                                logging.debug("    Trying subbook...")
                                subbookinfo = Parser.parse_book(SubInputter(chapter_inputter, chapter_filename), u"", book_author)
                                assert(subbookinfo)

                                chapter = Chapter()
                                url2chapter[chapter_inputter.fullpath(chapter_filename)] = chapter

                                chapter.cover  = subbookinfo.cover
                                if not chapter.cover and m.groupdict().has_key("cover"):
                                    chapter.cover = InputterImg(m.group("cover"), chapter_inputter)

                                chapter.subchapters = subbookinfo.subchapters

                                for subchapter in chapter.subchapters:
                                    subchapter.parent = chapter

                                reset_level(chapter, chapter_stack[-1].level + 1)

                                logging.info(u"    {indent}{title}: {has_cover}".format(
                                    indent="  "*(chapter_stack[-1].level + 1), title=chapter_title,
                                    has_cover = chapter.cover and u"Has cover" or "No cover"))

                            except NotParseableError as e:
                                # 尝试下一个表达式
                                continue

                        chapter.title = chapter_title   # 以目录中的标题为准
                        chapter.level = chapter_stack[-1].level + 1
                        chapter.parent = chapter_stack[-1]
                        chapter.parent.subchapters.append(chapter)
                        logging.debug(u"{indent}      Chapter: {title}".format(indent="  "*(3*inputter.nested_level+chapter.level), title=chapter.title))

                        next_pos = m.end()

                        process_next_line = True
                        break

                if process_next_line:
                    continue

                process_next_line = False
                for lvl in range(1, len(self.re_idx_levels) + 1):
                    for r in self.re_idx_levels[lvl-1]:
                        m = r.match(file_content)
                        if m:
                            next_pos = m.end()

                            level = lvl + top_level
                            while level <= chapter_stack[-1].level:
                                chapter_stack.pop()
                        
                            chapter = Chapter()
                            chapter.title = title_normalize_from_html(m.group("title"))
                            chapter.level = level
                            logging.debug(u"{indent}    Level {level} toc: {title}".format(
                                indent=u"  "*(3*inputter.nested_level+chapter.level), level=chapter.level, title=chapter.title))

                            chapter.parent = chapter_stack[-1]
                            chapter.parent.subchapters.append(chapter)
                            chapter_stack.append(chapter)

                            process_next_line = True
                            break

                    if process_next_line:
                        break

                if process_next_line:
                    continue

        if len(root_chapter.subchapters) == 0:
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        book = Book()
        book.title  = book_title
        book.author = book_author
        book.cover  = cover
        book.subchapters = root_chapter.subchapters
        for subchapter in book.subchapters:
            subchapter.parent = None

        if intro:
            book.subchapters[0:0] = [intro]
            book.intro = u"\n".join(intro.content)

        return book
#   }}}

class EasyChmParser(Parser): # {{{
    #re_pages = re.compile(u"\\bpages\s*\[\d+\]\s*=\s*\['(?P<filename>[^']+)'\s*,\s*'(?P<chapter_title>[^']*)'\s*,\s*'([^']*)'\s*(?:,\s*'(?P<l1title>[^']*)')?(?:,\s*'(?P<chapter_intro>[^']*)')?.*?\]\s*;", re.IGNORECASE)
    #re_pages = re.compile(u"\\bpages\s*\[\d+\]\s*=\s*\['(?P<filename>[^']+)'\s*,\s*'(?P<chapter_title>[^']*)'\s*,\s*'([^']*)'\s*(?<upper_titles>(?:,\s*'(?P<l1title>[^']*)')*)(?:,\s*'(?P<chapter_intro>[^']*)')?.*?\]\s*;", re.IGNORECASE)
    #re_pages = re.compile(u"\\pages\s*\[\d+\]\s*=\s*\[\s*'(.+?)'\s*\];")
    #re_pages_field_sep = re.compile(u"'\s*,\s*'")

    book_index_files = (    # page.js文件名及.txt文件的存放路径
        (os.path.join("js", "page.js"), "txt"),
        (os.path.join("js", "pages.js"), "data"),
        (os.path.join("index", "page.js"), "index"),
        ("Home1.htm", "txt"),   # 在《地球往事三部曲》中，把page.js中的内容直接放到Home1.htm中了
        ("page.js", "txt"),  # 《侯卫东官场笔记1-8》（校对全本）作者：小桥老树.chm中，page.js直接放在根目录
    )

    re_pages = re.compile(u"\\b\w*pages\s*\[\d+\]\s*=\s*\['(?P<page>.+?)'\]\s*;", re.IGNORECASE)
    re_pages_field_sep = re.compile(u"'\s*,\s*'")

    re_content_first = re.compile(u"document\.write\s*\((\s*.*?)['\"]\s*\)\s*;", re.IGNORECASE | re.MULTILINE)
    re_inner_title_signature = re.compile(u"<p.*center")
    re_content_cleanups = [
        [re.compile(u"(?i)document\.write\s*\(\s*['\"]"), u"\n"],
        [re.compile(u"(?i)(?m)['\"]\s*\)\s*;?\s*$"), u""],
    ]
    re_intro_title = re.compile(u"^[ \t　]*【?(?P<title>[^】：:]+)[】：:][ \t　]*$")
    re_intro_removes = [
        re.compile(u"^[ \t　]*\**\.*[ \t　]*$"),
    ]
    re_title_sep = re.compile(u"<\s*br\s*/?\s*>", re.IGNORECASE)

    # {{{ ---- pages_rules
    pages_rules = [
        # 《三国之力挽狂澜》作者：金桫.chm.js: pages[2]=['02_02','节二：必死','1520'];
        { 'cond' : lambda idx,fields: len(fields) == 3,
          'map'  : { 'file': 0, 'title1': 1 },
        },

        # 《三国之力挽狂澜》作者：金桫.chm.js: pages[1]=['02_01','节一：宗亲','1477','梦魇之章'];
        { 'cond' : lambda idx,fields: len(fields) == 4 and fields[3][0:4].lower() != u"<img",
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },
        # 《三国之力挽狂澜》作者：金桫.chm.js: pages[0]=['01_1','<BR><font size=2>内容简介：<BR>从历史出发，','2','<img src=../txt/2561.jpg>'];
        { 'cond' : lambda idx,fields: len(fields) == 4 and fields[3][0:4].lower() == u"<img" and idx == 0,
          'map'  : { 'book_intro': 1, 'book_cover': [3] },
        },
        # 《任怨作品合集》（精排合本）作者：任怨.chm 4: pages[1]=['02_1','<BR><font size=3>　　退出军旅,'2','<img src=../1.jpg>'];
        { 'cond' : lambda idx,fields: len(fields) == 4 and fields[3][0:4].lower() == u"<img" and idx != 0,
          'map'  : { 'next_intro': 1, 'next_cover': [3] },
        },

        # 《霍桑探案集》作者：[中]程小青.chm.js: pages[0]=['01_01','书籍相关','803','第一部:舞后的归宿','<img src=../txt/舞后的归宿.jpg class=cover>'];
        { 'cond' : lambda idx,fields: len(fields) == 5 and fields[4][0:4].lower() == u"<img",
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [4] },
        },
        # 《全能炼金师》（封面文字全本）作者：缘分0.chm.js: pages[0]=['1_01','第1章 炼狱岛','4188','第一部 炼狱岛','<font class=f2><BR>本集导读：<BR>'];
        { 'cond' : lambda idx,fields: len(fields) == 5 and re.search(r'<br\s*>', fields[4], re.IGNORECASE),
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_intro': 4 },
        },
        # 《调教初唐》作者：晴了.chm.js: pages[0]=['1-1','第001章 房府之二男','3334','第一卷','1'];
        { 'cond' : lambda idx,fields: len(fields) == 5,
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },

        # 《禁书三部曲》作者：若花燃燃.chm.js: pages[0]=['01_01','楔言','578','万劫','万劫','<img border=0 src=../pic/万劫.gif>'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5][0:4].lower() == u"<img" and fields[4] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [5] },
        },
        # 酒徒架空历史合集-酒徒.chm.js: pages[0]=['01_01','第一章 祸不单行','5021','布衣卷','明','<img border=0 src=../pic/ming.gif>'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5][0:4].lower() == u"<img" and fields[4] != fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 4, 'title3_cover': [5] },
        },
        # 莫言作品全集：arrpages[2]=['1-3','纯文学','酒国','莫言','省人民检察院的特级侦察员丁钩儿奉命到酒国市去调查一个特殊的案子：酒国市的官员吃掉了无数婴儿。但到酒国市的人没有能经得起诱惑的，丁钩儿虽不断提醒自己不喝酒，最后却醉酒淹死在茅厕里。','finish'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] == u"finish",
          'map'  : { 'file': 0, 'title1': 2, 'author': 3, 'title1_intro': 4 },
        },
        # 《徐公子胜治作品合集》.chm.js: pages[0]=['01_01','001回 阴阳一席坐，佛道两骛人','6086','第一卷 阴神篇','神游','神游'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] == fields[4] and fields[4] != fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 4 },
        },
        # 汤姆.克兰西作品集.chm: pages[0]=['01_01','第一章 伦敦市区:一个阳光灿烂的日子','10569','爱国者游戏','爱国者游戏','爱国者游戏'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] == fields[4] and fields[4] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },
        # 《卡徒》（精校文字全本）作者：方想.chm.js: pages[0]=['1_001','第一节 以卡为生','4970','第一集','1','第一集'];
        # 权柄-三戒大师.chm.js: pages[0]=['1_01','第一章 秦少爷初临宝地 防狼术小试牛刀','2876','第一卷 原上草','卷一','第一卷 原上草'];
        # 汤姆.克兰西作品集.chm.js: pages[0]=['01_01','第一章 伦敦市区:一个阳光灿烂的日子','10569','爱国者游戏','爱国者游戏','爱国者游戏'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] != fields[4] and fields[5] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },
        # 《丹·布朗作品集》作者：[美]丹·布朗.chm.js: pages[0]=['1_01','书籍相关','970','达芬奇密码','达芬奇密码','①'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] != fields[4] and fields[4] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },
        # pages[0]=['01_01','第一章 血尸','3155','第一卷 七星鲁王','1','第一季·七星鲁王宫'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] != fields[4] and fields[4] != fields[3] and fields[5] != fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 5 },
        },

        # 莫言作品全集：arrpages[2]=['1-3','纯文学','酒国','莫言','省人民检察院的特级侦察员丁钩儿奉命到酒国市去调查一个特殊的案子：酒国市的官员吃掉了无数婴儿。但到酒国市的人没有能经得起诱惑的，丁钩儿虽不断提醒自己不喝酒，最后却醉酒淹死在茅厕里。','finish'];
        { 'cond' : lambda idx,fields: len(fields) == 7 and fields[5] == u"finish",
          'map'  : { 'file': 0, 'title1': 2, 'author': 3, 'title1_intro': 4, 'title2': 6 },
        },

        # 《圣纹师》（实体封面版）作者：拂晓星.chm.js: pages[0]=['1-1','～第一章零之殿下～','7314','·第一集 愿望女神·','<img src=../txt/01.jpg id=...>','·第一集 愿望女神·','掌握人类命运的圣纹师，出现了前所未有的危机！<br>急剧'];
        # 未来军医-胜己.chm.js: pages[0]=['01_01','第001章 诈尸','4297','第一卷 重生现代','<img src=../txt/1.jpg class=cover width=186 height=275>','※洛&#9825xin※精心制作','<img src=../txt/1.jpg class=cover width=600 height=889>'];
        { 'cond' : lambda idx,fields: len(fields) == 7 and fields[4][0:4].lower() == u"<img" and fields[6][0:4].lower() == u"<img",
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [4, 6] },
        },
        # 《血红全本作品合集》1.0: pages[0]=['01_01','第一章 我，是流氓','2344','正文','我就是流氓','<font class=f7>　　<font color=red><b>内容简介：</b></font><BR><BR>　　一个小流氓如何因为奇遇变成一个超级大流氓的故事。</font>','血红'];
        { 'cond' : lambda idx,fields: len(fields) == 7 and len(fields[4]) > 0 and fields[5][0:5].lower() == u"<font" and len(fields[6]) > 0,
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 4, 'author': 6 },
        },
        # 《月关全本作品合集》1.0: pages[0]=['01_1','第001章 注入灵魂成功','2604','第一卷 回到过去','','颠覆笑傲江湖','<font class=f3>　　<font color=red><b>内容简介：</b></font><BR><BR>　　每部小说中，都有主角和...<BR>　　江湖，由我来笑傲，我就是：泉州参将吴天德！</font>','月关'];
        { 'cond' : lambda idx,fields: len(fields) == 8 and len(fields[4]) == 0 and len(fields[5]) > 0 and fields[6][0:5].lower() == u"<font" and len(fields[7]) > 0,
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 5, 'author': 7 },
        },

        # 《卡徒》（精校封面收藏版）作者：方想.chm: pages[0]=['1_01','第一节 以卡为生','4972','目录','卡徒·第一季','','<img src=../txt/1.jpg width=200 height=282 class=cover>',''];
        { 'cond' : lambda idx,fields: len(fields) == 8 and fields[3] == u"目录" and len(fields[4]) > 0 and len(fields[5]) == 0 and len(fields[7]) == 0,
         'map'  : { 'file': 0, 'title1': 1, 'title2': 4, 'title2_cover': [6] },
        },

        #合并到下面，由程序对于两级相同的标题进行合并
        ## 道门世家-普通.chm.js: pages[0]=['1-1','本集简介','0','第一集','第一集','A～★航星★','<img src=../txt/01.jpg class=cover>','<br>　　我是一个平','<img src=../txt/1.jpg class=cover>','0','第一集'];
        ## 《刘猛作品集》作者：刘猛.chm: pages[0]=['1_1','第一章 提炼','40144','最后一颗子弹留给我','','A～★航星★','<img src=../txt/1.jpg class=cover>','　　这是一部关于青春和爱……','<img src=../txt/1.jpg class=cover>','40144','最后一颗子弹留给我'];
        #{ 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and len(fields[7]) > 20 and fields[10] == fields[3],
        #  'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [6, 8], 'title2_intro': 7 },
        #},

        # 《二月河帝王系列》作者：二月河.epub: pages[581]=['14_1','第一回','10319','爝火五羊城','','A～★航星★','<img src=../txt/4.jpg class=cover>','','<img src=../txt/4.jpg class=cover>','10319','爝火五羊城'];
        { 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and fields[7] == "" and fields[10] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [6, 8] },
        },
        # 《二月河帝王系列》作者：二月河.epub: pages[0]=['01_01','楔子','4522','第一卷 夺宫初政','','A～★航星★','<img src=../txt/1.jpg class=cover>','　　康熙帝名玄烨，...','<img src=../txt/1.jpg class=cover>','4522','康熙大帝'];
        # 
        { 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and len(fields[7]) > 20 and len(fields[10]) > 0 and fields[10] != fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 10, 'title3_cover': [6, 8], 'title3_intro': 7 },
        },
        # 《荆柯守作品合集》: pages[0]=['01_1','风起紫罗峡目录大纲','885','作品相关','','','<img src=../txt/1.jpg class=cover>','','<img src=../txt/1.jpg class=cover>','','风起紫罗峡'];
        #{ 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and len(fields[10]) > 0 and fields[10] != fields[3],
        { 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and len(fields[10]) > 0,
         'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 10, 'title3_cover': [6, 8], 'title3_intro': 7 },
        },
        # 《酒徒历史作品集》: pages[58]=['05_01','第一章 黄昏（一）','6406','第一卷 斜阳','指南录','天','涯','　　一群男人为了捍卫一个文明不被武力征服的权力，一个民族不集体沦为四等奴隶的尊严而进行的抗争。<br>　　在崖山落日前，探索历史的另一种可能，和文明的另一种出路。以文天祥空坑兵败后的抗元故事为主线，介绍那个时代的传奇……','E','书','指南录'];
        { 'cond' : lambda idx,fields: len(fields) == 11 and len(fields[4]) > 0 and fields[4] == fields[10] and len(fields[7]) > 20,
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 10, 'title3_intro': 7 },
        },
        # 恶魔狂想曲之明日骄阳.chm.js: pages[0]=['1-1','本集简介','0','第一集','第一集','A～★航星★','<img src=../txt/1.jpg class=cover>','<br>　　疾风佣兵','<img src=../txt/1.jpg class=cover>','0','第一集','<img src=../txt/01.jpg class=cover>'];
        { 'cond' : lambda idx,fields: len(fields) == 12 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and fields[11][0:4].lower() == u"<img" and re.search(r"<br\s*>", fields[7], re.IGNORECASE) and fields[10] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [6, 8, 11], 'title2_intro': 7 },
        },

        # 上面全部不能匹配时的最后退路
        { 'cond' : lambda idx,fields: len(fields) >= 4,
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },
    ]
    # }}}

    def parse(self, inputter, top_level, book_title, book_author): # {{{
        normalizer = HtmlContentNormalizer(inputter=inputter)

        def read_chapter(inputter, filename, title): # {{{
            chapter = Chapter()
            url2chapter[inputter.fullpath(filename)] = chapter
            content = u"".join(inputter.read_lines(filename))

            m = self.re_content_first.search(content)
            if m and self.re_inner_title_signature.search(m.group(1)):
                has_inner_title = True
            else:
                has_inner_title = False

            for cleanup in self.re_content_cleanups:
                content = cleanup[0].sub(cleanup[1], content)

            content = normalizer.normalize(content, inputter)

            if content:
                if has_inner_title and isinstance(content[0], basestring):
                    chapter.title_inner = trim(content[0])
                    chapter.content     = content[1:]
                else:
                    chapter.content     = content

            chapter.title = title

            return chapter
        # }}}

        def parse_intro(html, default_title=BOOK_INTRO_TITLE): # {{{
            lines = normalizer.text_only(html)
            if not lines:
                return u'', u''

            m = self.re_intro_title.match(lines[0])
            if m:
                title = m.group("title")
                lines = lines[1:]
            else:
                title = default_title

            content = list()
            for line in lines:
                keep_line = True
                for rm in self.re_intro_removes:
                    if rm.match(line):
                        keep_line = False
                        break

                if keep_line:
                    content.append(line)

            return title, content
        # }}}

#        # 如果有入口文件，则入口文件只能是start.htm
#        if inputter.entry and inputter.entry != u"start.htm":
#            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
#                file=inputter.fullpath(), parser=self.__class__.__name__,
#                indent=u"      "*inputter.nested_level))
#
#            raise NotParseableError(u"{file} is not parseable by {parser}".format(
#                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 把pages.js的内容解释到pages列表中
        pages = list()
        for (book_index_file, txt_path) in self.book_index_files:
            logging.debug(u"{indent}    Trying {book_index_file}, {txt_path}...".format(
                book_index_file=book_index_file,
                txt_path=txt_path,
                indent=u"      "*inputter.nested_level))

            if not inputter.exists(txt_path):
                logging.debug(u"{indent}      {txt_path} not exists".format(
                    txt_path=txt_path,
                    indent=u"      "*inputter.nested_level))
                continue

            if not inputter.exists(book_index_file):
                logging.debug(u"{indent}      {book_index_file} not exists".format(
                    book_index_file=book_index_file,
                    indent=u"      "*inputter.nested_level))
                continue

            logging.debug(u"{indent}    Checking {file}".format(
                file=book_index_file,
                indent=u"      "*inputter.nested_level))

            for m in self.re_pages.finditer(inputter.read_all(book_index_file)):
                pages.append(self.re_pages_field_sep.split(m.group(1)))

            if not pages:
                continue

            # 逐项处理pages
            max_title_level = 0     # 最大标题层次数，只有1级为1，两级为2...
            next_intro = None       # 有些格式中，把章节简介和封面放在前面一行
            next_cover = None

            book = Book()
            book.title  = book_title
            book.author = book_author

            intro = None
            root_chapter = Chapter()
            root_chapter.level = sys.maxint
            chapter_stack = [root_chapter]

            cover_inputter = SubInputter(inputter, os.path.dirname(book_index_file))

            for idx in xrange(len(pages)):
                for rule in self.pages_rules:
                    if not rule['cond'](idx, pages[idx]):
                        continue

                    # 滿足条件
                    if rule['map'].has_key('book_cover'):
                        # 提供了书本的封面
                        cover = self.parse_cover(
                            self.extract_image_path([pages[idx][i] for i in rule['map']['book_cover']])
                            # 有可能是相对于根js进行定位，因此尝试只要最后的部分
                            + [os.path.join(txt_path, os.path.basename(self.extract_image_path(pages[idx][i]))) for i in rule['map']['book_cover']]
                            + [os.path.join(u"..", txt_path, os.path.basename(self.extract_image_path(pages[idx][i]))) for i in rule['map']['book_cover']],
                            cover_inputter)

                        if cover:
                            book.cover = cover
                            logging.debug(u"{indent}  Found book cover '{filename}'".format(
                                indent=u"      "*inputter.nested_level, filename=cover.filename()))
            
                    if rule['map'].has_key('book_intro'):
                        # 提供了书本的简介
                        intro = Chapter()
                        intro.title, intro.content = parse_intro(pages[idx][rule['map']['book_intro']], BOOK_INTRO_TITLE)
                        if not intro.title and not intro.content:
                            intro = None

                    if rule['map'].has_key('next_cover'):
                        # 提供了下一章节的封面
                        next_cover = self.parse_cover(
                            self.extract_image_path([pages[idx][i] for i in rule['map']['next_cover']]),
                            cover_inputter)
            
                    if rule['map'].has_key('next_intro'):
                        # 提供了下一章节的简介
                        next_intro = parse_intro(pages[idx][rule['map']['next_intro']], CHAPTER_INTRO_TITLE)

                    for lvl in xrange(3, 0, -1):
                        title_name = u"title{0}".format(lvl)
                        if not rule['map'].has_key(title_name):
                            continue

                        # 记录最大的标题层次
                        if lvl > max_title_level:
                            max_title_level = lvl

                        if lvl > 1:
                            chapter = Chapter()
                            titles = self.re_title_sep.split(pages[idx][rule['map'][title_name]], 1)
                            chapter.title = title_normalize_from_html(titles[0])
                            if len(titles) > 1: # 有简短的前言
                                chapter.content = HtmlContentNormalizer(inputter).normalize(titles[1])
                        else:
                            subInputter = SubInputter(inputter, txt_path)
                            if subInputter.isfile(pages[idx][rule['map']['file']] + u".txt"):
                                chapter = read_chapter(
                                    subInputter,
                                    pages[idx][rule['map']['file']] + u".txt",
                                    title_normalize_from_html(pages[idx][rule['map'][title_name]]))
                            else:
                                title  = title_normalize_from_html(pages[idx][rule['map'][title_name]])
                                author = pages[idx][rule['map']['author']] if rule['map'].has_key('author') else u''

                                subInputter = SubInputter(subInputter, pages[idx][rule['map']['file']])
                                logging.debug(u"{indent}      Parsing sub book '{path}'".format(
                                    path = subInputter.fullpath(""),
                                    indent=u"      "*inputter.nested_level))

                                logging.debug("    Trying subbook...")
                                subbookinfo = Parser.parse_book(
                                    subInputter,
                                    title_normalize_from_html(pages[idx][rule['map'][title_name]]),
                                    (pages[idx][rule['map']['author']] if rule['map'].has_key('author') else u''),
                                    u'')

                                chapter = Chapter()
                                url2chapter[subInputter.fullpath()] = chapter
                                chapter.title  = title if title else subbookinfo.title
                                chapter.author = author if author else subbookinfo.author
                                chapter.subchapters = subbookinfo.subchapters
                                chapter.cover = subbookinfo.cover

                                for subchapter in chapter.subchapters:
                                    subchapter.parent = chapter

                        chapter.level = lvl

                        if next_intro:
                            chapter.intro = next_intro[1]
                            next_intro = None

                        if next_cover:
                            chapter.cover = next_cover
                            next_cover = u""

                        if rule['map'].has_key(title_name + u"_intro"):
                            chapter.intro = parse_intro(pages[idx][rule['map'][title_name + u"_intro"]], CHAPTER_INTRO_TITLE)[1]
                            
                        if rule['map'].has_key(title_name + u"_cover"):
                            chapter.cover = self.parse_cover(
                                self.extract_image_path([pages[idx][i] for i in rule['map'][title_name + u"_cover"]]),
                                cover_inputter)

                        if lvl > 1:
                            logging.info(u"    {indent}{title}: {has_cover}".format(
                                indent="  "*(max_title_level-lvl), 
                                title=chapter.title,
                                has_cover = chapter.cover and u"Has cover" or "No cover"))

                        # 已经生成好chapter，放到适当的位置
                        while lvl >= chapter_stack[-1].level:
                            chapter_stack.pop()

                        chapter.parent = chapter_stack[-1]
                        chapter.parent.subchapters.append(chapter)
                        chapter_stack.append(chapter)

                        logging.debug(u"{indent}      {title}{content}{cover}{intro}".format(
                            indent=u"  "*(3*inputter.nested_level+max_title_level-chapter.level+1), title=chapter.title,
                            content=u"" if chapter.content else u" w/o content",
                            cover=u" w/ cover" if chapter.cover else u"",
                            intro=u" w/ intro" if chapter.intro else u""))

                    # 处理完一条pages记录，不再尝试后续的rule
                    break

            # 已经完成解释，不再尝试下一条book_index_files
            break
        else: # book_index_files中所有项目均不符合
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        reset_level(root_chapter, top_level)

        book.subchapters = root_chapter.subchapters
        for subchapter in book.subchapters:
            subchapter.parent = None

        # 对于最高层的标题，看看txt/目录有没有对应的封面图片
        for chapter in root_chapter.subchapters:
            if chapter.cover:
                break   # 如果使用目录中与章节编号对应的图片作为封面的话，所有顶层章节都不应有指定的封面
        else:   # 所有顶层章节目前都没有封面，看看目录下有没有对应编号的图片
            top_title_count = 0     # 顶层标题计数，用于对应txt/目录下的jpg文件
            for chapter in root_chapter.subchapters:
                top_title_count += 1

                chapter.cover = self.parse_cover([
                    u"../txt/{0}.jpg".format(top_title_count), 
                    u"../txt/0{0}.jpg".format(top_title_count)], cover_inputter)

                if not chapter.cover:   # 应该所有顶层章节都有封面图片，否则说明这些不是章节对应的封面图片
                    for c in root_chapter.subchapters:
                        c.cover = None

                    break

        if intro:
            book.subchapters[0:0] = [intro]
            book.intro = u"\n".join(intro.content)

        # 取第一个章节的封面作为整本书的封面
        if not book.cover and book.subchapters and book.subchapters[0].cover:
            book.cover = book.subchapters[0].cover

        return book
    # }}}
#   }}}

class IFengBookParser(Parser): # {{{
    re_info = re.compile(
        u"<div [^>]*\"infoTab\d*\"[^>]*>\s*" +
        u"<table[^>]*>\s*" +
        u"(?:<tbody>\s*)?<tr[^>]*>\s*" +
        u".*?<img src=\"(?P<cover>[^\"]+)\".*?</td>\s*" +
        u"<td[^>]*>\s*" +
        u"<span[^>]*><a\s[^>]*>(?P<title>.+?)</a></span>\s*" +
        u"(?:<span class=\"us_gray\">(?P<sub_title>[^<]+)</span>)?" +
        u".*?" +
        u"<td[^>]*id=\"authors\"[^>]*>\s*<a[^>]*>(?P<author>[^<]*)</a>" +
        u".*?" +
        u"(?P<attrs>(?:<tr[^>]*>\s*<td[^>]*>[^<]+：\s*</td>\s*<td[^>]*>.*?</td>\s*</tr>\s*)+)" +
        u".*?" + 
        u"</t(?:body|able)>" +
        u"", re.IGNORECASE | re.DOTALL)
        
    re_attr = re.compile(
        u"<td[^>]*>\s*(?P<name>[^<]+)\s*：\s*</td>\s*<td[^>]*>\s*(?P<value>.*?)</td>", re.IGNORECASE | re.DOTALL)

    re_multival = re.compile(
        u"<a[^>]*>(?P<val>.*?)</a>", re.IGNORECASE | re.DOTALL)

    re_preliminaries = (
        re.compile(
            u"<div class=\"(?P<type>[^\"]\+Intro)\">\s*" +
            u"<h2><span>(?P<title>[^<]*)</span></h2>\s*" +
            u"(?P<content>.+?)<(?:h4|/div)>" +
            u"", re.IGNORECASE | re.DOTALL),
    )

    re_book_content = re.compile(
        u"<div class=\"bookContent\">", re.IGNORECASE)
   
    re_part = re.compile(
        u"<div class=\"part\">\s*<h3[^>]*>(?P<title>.+?)</h3>\s*" +
        u"<div class=\"current\">\s*(?P<intro>.+?)<ul>(?P<lists>.+?)</ul>" +
        u"", re.IGNORECASE | re.DOTALL)

    re_part_title_cleanups = (
        { 're'  : re.compile(u"<(?P<tag>\w+)(?:\s[^>]*)?>.*?</(?P=tag)\s*>", re.DOTALL),
          'sub' : u""
        },
    )

    re_part_list = re.compile(
        u"<li><a href=\"(?P<url>[^\"]+)\" title=\"(?P<title>[^\"]+)\">",
        re.IGNORECASE)

    re_chapter_content = re.compile(
        u"<div[^>]*\\bid=\"artical_real\"[^>]*>(?P<content>.+?)</div>",
        re.IGNORECASE | re.DOTALL)

    def parse(self, inputter, top_level, book_title, book_author):
        if not inputter.entry:
            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        file_content = inputter.read_all(inputter.entry)

        normalizer = HtmlContentNormalizer(inputter=inputter)

        # 找出书的基本信息
        book = Book()
        m = self.re_info.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. infoTab not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        book.title = title_normalize_from_html(m.group("title"))
        if m.group("sub_title"):
            book.sub_title = title_normalize_from_html(m.group("sub_title"))

        book.author = title_normalize_from_html(m.group("author"))

        attrs = dict()
        for match_attr in self.re_attr.finditer(m.group("attrs")):
            value = list()
            for match_val in self.re_multival.finditer(match_attr.group("value")):
                value.append(match_val.group("val"))

            if not value:
                value = match_attr.group("value")
            elif len(value) == 1:
                value = value[0]

            attrs[match_attr.group("name")] = value

        if m.group("cover"):
            book.cover = self.parse_cover(m.group("cover"), inputter)

        book.publisher = title_normalize_from_html(attrs.get(u"出 版"))
        book.isbn = title_normalize_from_html(attrs.get(u"ISBN"))
        book.publish_date = title_normalize_from_html(attrs.get(u"出版日期"))
        book.publish_ver = title_normalize_from_html(attrs.get(u"版 次"))
        book.category = title_normalize_from_html(attrs.get(u"所属分类"))

        logging.debug(u"    Book info:")
        logging.debug(u"      BookName: {title}".format(title=book.title))
        logging.debug(u"      Author:   {author}".format(author=book.author))
        logging.debug(u"      Category: {category}".format(category=book.category))

        logging.debug(u"    Parsing book content")

        # 收集前置章节（作者简介、图书简介等）
        preliminaries = list()

        for r in self.re_preliminaries:
            m = r.search(file_content)
            if m:
                chapter = Chapter()
                chapter.title   = title_normalize_from_html(m.group("title"))
                chapter.content.extend(normalizer.text_only(m.group("content")))

                if m.group("type") == "bookIntro":
                    book.intro = u"\n".join(chapter.content)

                if chapter.title and chapter.content:
                    logging.debug(u"      Preliminaries: {title}".format(title=chapter.title))
                    preliminaries.append(chapter)
        
        m = self.re_book_content.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. bookContent not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        for match_part in self.re_part.finditer(file_content[m.end():]):
            title = match_part.group("title")
            for r in self.re_part_title_cleanups:
                title = r["re"].sub(r["sub"], title)

            chapter = Chapter()
            chapter.title = title
            chapter.intro = normalizer.text_only(match_part.group("intro"))

            logging.debug(u"      Chapter: {title}".format(title=chapter.title))

            for match_li in self.re_part_list.finditer(match_part.group("lists")):
                subchapter = Chapter()
                subchapter.title = title_normalize_from_html(match_li.group("title"))

                logging.debug(u"        Chapter: {title} ({url})".format(title=subchapter.title, url=match_li.group("url")))

                # 读入正文
                chapter_content = inputter.read_all(match_li.group("url"))
                m = self.re_chapter_content.search(chapter_content)
                if not m:
                    raise NotParseableError(u"{file} is not parseable by {parser}. '{chapter}' is not parseable!".format(
                        file=inputter.fullpath(), parser=self.__class__.__name__, chapter=match_li.group("url")))

                subchapter.content.extend(normalizer.text_only(m.group("content")))

                chapter.subchapters.append(subchapter)

            book.subchapters.append(chapter)

        # 看看有没有可以识别的章节
        if len(book.subchapters) <= 0:
            raise NotParseableError(u"{file} is not parseable by {parser}. No chapter detected!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 插入前面的章节
        book.subchapters[0:0] = preliminaries

        return book
#   }}}

class InfzmParser(Parser): # {{{
    """ 南方周末解释器
    """
    re_info = re.compile(
        u'<div id="contents">\s*' +
        u'<div id="enews_header">\s*' +
        u'<h1>\s*' +
        u'<span>.*?</span>(?P<title>\S+)\s*</h1>\s*' +
            u'</div>\s*' +
            u'<div[^>]*>\s*' +
        u'<div class="side-1">\s*' +
        u'<div class="cover">\s*' +
        u'<img[^>]* src="(?P<cover>[^"]+)"[^>]*>\s*' +
        u'<p>(?P<date>.+?)</p>\s*' +
        u'<p>(?P<version>.+?)</p>\s*' +
        u'', re.IGNORECASE | re.DOTALL)

    #   <dt><span>本期头条:</span><a href="http://www.infzm.com/content/51232" title="翼城人口特区 一个县尘封25年的二胎试验">翼城人口特区 一个县尘封25年的二胎试验</a>
    #           </dt>
    #   <dd class="summary">在放开“二胎”25年之后的山西翼城，人口增长率反而低于全国水平，以性别比例为代表的各项人口指标均优于全国水平</dd>
    # </dl>
    re_topnews = re.compile(
        u'<dl class="topnews">\s*' +
        u'<dt><span>[^<]*</span><a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)">' +
        u'.*?<dd class="summary">(?P<summary>[^<]+)</dd>' +
        u'', re.IGNORECASE | re.DOTALL)

    re_lists = [
        [
            #   <h2>经济</h2>
            #   <dl>
            #           <dt></dt>
            #           <dd>
            #                   <ul class="relnews">
            #                           <li><a href="http://www.infzm.com/content/51073" title="消灭村庄？——中国新城市化之忧">消灭村庄？——中国新城市化之忧</a></li>
            #                           <li><a href="http://www.infzm.com/content/51074" title="一位宜黄官员的来信">一位宜黄官员的来信</a></li>
            #
            #                   </ul>
            #
            #           </dd>
            #           </dl>
            re.compile(
            #    u'<div class="left">\s*' +
                u'<h2>(?P<title>.+?)</h2>\s*' +
                u'<dl>\s*' +
                u'<dt></dt>\s*' +
                u'<dd>\s*' +
                u'<ul class="relnews">\s*' +
                u'(?P<news>.*?)' +
                u'</dd>\s*' +
                u'</dl>' +
                u'', re.IGNORECASE | re.DOTALL),
            # <li><a href="http://www.infzm.com/content/51074" title="一位宜黄官员的来信">一位宜黄官员的来信</a></li>
            re.compile(
                u'<li><a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)">',
                re.IGNORECASE)
        ],
        [
            #   <dl style="float: left; width: 300px;">
            #                   <dt id="rw_1">观点</dt>
            #                                                           <dd>
            #                     <a href="http://www.infzm.com/content/50903" title="来信（20100927）">
            #                     <span class="jt"></span>来信（20100927）                                                        </a>
            #                     </dd>
            #                     <a href="http://www.infzm.com/content/50885" title="【世相】助人为恐">
            #                     <span class="jt"></span>【世相】助人为恐                                                        </a>
            #                     </dd>
            # </dl>
            re.compile(
            #    u'<div id="index"[^>]*>\s*' + 
                u'<dl style=[^>]*>\s*' +
                u'<dt[^>]*>(?P<title>.+?)</dt>\s*' +
                u'(?P<news>' + 
                u'<dd>\s*' +
                u'<a\s' +
                u'.*?)' +
                u'</dl>' +
                u'', re.IGNORECASE | re.DOTALL),
            #                                                           <dd>
            #                     <a href="http://www.infzm.com/content/50903" title="来信（20100927）">
            #                     <span class="jt"></span>来信（20100927）                                                        </a>
            #                     </dd>
            re.compile(
                u'<dd>\s*' +
                u'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)">',
                re.IGNORECASE)
        ],
    ]

    # <div id="detailContent">
    #   <h1>【诺贝尔奖2010】钢笔字是如何变成赔率的——诺贝尔奖的博彩游戏</h1>
    #   <p class="relInfo">
    #           <span class="author">
    #                   <em>作者:</em>
    #                   <strong>南方周末特约撰稿 魏一帆（Tim Hathaway）　翻译：李宏宇</strong>
    # 
    #           </span>
    #                                                                   <span class="originated">发自北京 伦敦 连线报道</span>
    #                                                                   <span class="pubTime">2010-10-13 17:29:24</span>
    #           <span class="source"><em>来源:</em>南方周末</span>
    #   </p>
    #   <div class="contents">
    #   ...
    #   页。&nbsp;</p></div><!--end #text-->
    re_news_content = re.compile(
        u'<div id="detailContent">\s*' +
        u'<h1>(?P<title>.+?)</h1>\s*' +
        u'<p class="relInfo">\s*' +
        u'<span class="author">\s*' +
        u'<em>作者:</em>\s*' +
        u'<strong>(?P<author>.+?)</strong>\s*' +
        u'</span>\s*'
        u'(?:<span class="originated">(?P<originated>.*?)</span>\s*)?' +
        u'(?:<span class="pubTime">(?P<publish_date>.*?)</span>\s*)?' +
        u'(?:<span class="source">(?P<source>.*?)</span>\s*)?' +
        u'.*?</p>\s*' +
        u'<div class="contents">\s*' +
        u'(?P<content>.*?)' +
        u'</div><!--end #text-->' +
        u'', re.IGNORECASE | re.DOTALL)

    # <p style="text-align: center;"><img alt="" src="http://images.infzm.com/medias/2010/1013/39426.jpeg" height="400" width="549"></p>
    # <p style="text-align: center; color: rgb(102, 102, 102); line-height: 1.4em; padding: 0pt 4em;">从25年前开始，翼城人就可以有条件生育二胎。 <span style="color: rgb(136, 136, 136);">（东方IC/图）</span></p>
    re_news_content_img = re.compile(
        u'<img[^>]*src="(?P<url>[^"]+)"[^>]*>\s*' +
        u'</p>\s*' +
        u'<p style="[^"]*text-align: center;[^>]*>(?P<desc>.*?)</p>' +
        u'', re.IGNORECASE | re.DOTALL)

    re_section_title = re.compile(
        u'<p><b>(?P<title>.+?)</b></p>',
        re.IGNORECASE | re.DOTALL)

    def parse_chapter(self, path, inputter):
        # 读入正文
        chapter_content = inputter.read_all(path)

        m = self.re_news_content.search(chapter_content)
        if not m:
#            print chapter_content
            raise NotParseableError(u"{file} is not parseable by {parser}. '{url}' is not parseable!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__, url=url))

        normalizer = HtmlContentNormalizer(inputter=inputter)

        #print m.group("content")
        #print normalizer.normalize(m.group("content"))
        chapter = Chapter()
        url2chapter[inputter.fullpath(path)] = chapter
        chapter.title = title_normalize_from_html(m.group("title"))
        chapter.author = title_normalize_from_html(m.group("author"))
        chapter.originated = title_normalize_from_html(m.group("originated"))
        chapter.publish_date = title_normalize_from_html(m.group("publish_date"))
        chapter.source = title_normalize_from_html(m.group("source"))

        chapter.content = list()
        start_pos = 0
        content = m.group("content")

        normalizer = HtmlContentNormalizer(inputter=inputter, re_imgs=self.re_news_content_img)

        for m in self.re_section_title.finditer(content):
            if m.start() > start_pos:
                chapter.content.extend(normalizer.normalize(content[start_pos:m.start()]))

            chapter.content.append(SectionTitle(title_normalize_from_html(m.group("title"))))

            start_pos = m.end()

        if start_pos < len(content):
            chapter.content.extend(normalizer.normalize(content[start_pos:]))

        return chapter

    def parse(self, inputter, top_level, book_title, book_author):
        if not inputter.entry:
            raise notparseableerror(u"{file} is not parseable by {parser}".format( file=inputter.fullpath(), parser=self.__class__.__name__))

        normalizer = HtmlContentNormalizer(inputter=inputter)

        file_content = inputter.read_all(inputter.entry)
        #print file_content

        # 找出基本信息
        book = Book()
        m = self.re_info.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. cover not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        book.title = u"{title}-{version}".format(
            title=title_normalize_from_html(m.group("title")),
            version=title_normalize_from_html(m.group("date")))
            #version=title_normalize_from_html(m.group("version")))

        logging.debug(u"    {title}".format(title=book.title))

        book.sub_title = title_normalize_from_html(m.group("date"))
        book.cover = self.parse_cover(m.group("cover"), inputter)
        book.author = u"南方报业传媒集团"
        book.category = CATEGORY_NEWS_PAPER

        m = self.re_topnews.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. topnews not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        logging.debug(u"      TopNews: {title} ({url})".format(title=title_normalize_from_html(m.group("title")), url=m.group("url")))

        chapter = Chapter()
        url2chapter[inputter.fullpath()] = chapter
        chapter.title = u"本期头条"
        topnews = self.parse_chapter(m.group("url"), inputter)
        topnews.intro = normalizer.normalize(m.group("summary"))
        chapter.subchapters.append(topnews)
        book.subchapters.append(chapter)

        news_lists = list()
        for re_list in self.re_lists:
            for match_list in re_list[0].finditer(file_content):
                news_lists.append({
                    'start' : match_list.start(),
                    'end'   : match_list.end(),
                    'title' : title_normalize_from_html(match_list.group("title")),
                    'news'  : match_list.group("news"),
                    're'    : re_list[1],
                })

            if news_lists:  # 只要首组能匹配的表达式
                break

        news_lists.sort(key=lambda l: l["start"])

        #start_pos = 0
        for news_list in news_lists:
            #if news_list["start"] < start_pos:
            #    continue

            #start_pos = news_list["end"]

            chapter = Chapter()
            chapter.title = news_list["title"]

            logging.debug(u"      Chapter: {title}".format(title=chapter.title))

            #print news_list["news"]
            for match_news in news_list["re"].finditer(news_list["news"]):
                logging.debug(u"        Chapter: {title} ({url})".format(
                    title=title_normalize_from_html(match_news.group("title")), url=match_news.group("url")))

                subchapter = self.parse_chapter(match_news.group("url"), inputter)

                chapter.subchapters.append(subchapter)

            if chapter.subchapters:
                book.subchapters.append(chapter)
            else:
                logging.debug(u"      No sub chapters found, skipping {title}".format(title=chapter.title))
        
        # 不需要重排TOC
        options.rearrange_toc = False

        return book
#   }}}

class NbweeklyParser(Parser): # {{{
    """ 南都周刊
    """
    # 层层深入，下一层将在上一层的content范围内查找
    re_info = [
        # 圈定一个范围
        re.compile(
          u'<div class="printarticle"[^>]*>(?P<content>.*?)<div[^>]*class="newslist"' +
          u'', re.IGNORECASE | re.DOTALL),

        # 在上面的content中查找如下内容
        re.compile(
          u'<ul>\s*' +
          u'<a\s+[^>]*><img\s+[^>]*src="(?P<cover>[^"]+)"[^>]*>' + 
          u'.*' +
          u'<li>\s*<h4>(?P<title>[^>]+\d\d\d\d年度第\d+期)</h4>' +
          u'.*' +
          u'<li>\s*<h5>出版日期：(?P<publish_date>[^<]+)</h5>' +
          u'.*' +
          u'<li>\s*<h5>主管主办：(?P<author>[^<]+)</h5>' +
          u'', re.IGNORECASE | re.DOTALL),
    ]

    # 顶层数组每项对应一个方案，每个方案又是一个数组，分别层层深入，下一层从上一层的content中进行查找
    re_levels = [
        #<h2 style="text-align:left; color:#ba0600;">----财智----</h2>
        #<ul>
        #  
        #      <li>
        #        <h2><a href="/Print/Article/11489_0.shtml" target="_blank">喜羊羊被购疑云：老鼠爱上羊</a></h2>
        #        <h6>当下中国最知名、最赚钱的“羊”和“狼”，为何要投入早已落寞的“唐老鸭”、“米老鼠”的怀抱？是凤凰期望攀上更高的枝头，还是这边的梧桐不够参天？</h6>

        #      </li>
        #    
        #</ul>
        [
           # 顶层
            re.compile(
                u'<div[^>]*class="newslist"[^>]*>' +
                u'(?P<content>.*?)' +
                u'<div[^>]*class="dright"' +
                u'', re.IGNORECASE | re.DOTALL),
            # 栏目
            re.compile(
                u'<h2[^>]*>-*(?P<title>.+?)-*</h2>\s*' +
                u'<ul>(?P<content>.*?)</ul>' +
                u'', re.IGNORECASE | re.DOTALL),
            # 具体文章
            re.compile(
                u'<h2><a href="(?P<url>[^"]+)"[^>]*>(?P<title>.+?)</a>' +
                u'', re.IGNORECASE | re.DOTALL),
        ],

        # <div class="newslist">
        #   <ul>
        #         <li>
        #           <h3><a href="/Print/Article/11473-0.shtml" target="_blank">“张学友演唱会定金门”调查</a></h3>
        #           <h6>至此事件三方演绎齐全，如罗生门各有说法，而实质很可能是陈淑芬与前下属沈诗仪的矛盾以财务纠纷形式公开化，唯一可怜的是歌神张学友被无辜利用。  </h6>
        #         </li>
        [
           # 顶层
            re.compile(
                u'<div[^>]*class="newslist"[^>]*>' +
                u'(?P<content>.*?)' +
                u'<div[^>]*class="dright"' +
                u'', re.IGNORECASE | re.DOTALL),
            # 具体文章
            re.compile(
                u'<li>\s*<h3><a href="(?P<url>[^"]+)"[^>]*>(?P<title>.+?)</a>' +
                u'', re.IGNORECASE | re.DOTALL),
        ],


    ]

    # <div class="body">
    #   <div class="dleft">
    #     <div class="dpath" style="font-size:14px;"> <a href="/" style="text-decoration:underline;">主页</a> &gt; <a style="text-decoration:underline;" href="/Print/823.shtml">南都周刊2010年度第43期</a> &gt; 正文 </div>
    # 
    #     <div class="dtitle">
    #       <h1>网络公关业“刮骨疗毒”</h1>
    #       <div class="text">2010-11-12 10:12:20　来源: 南都周刊　浏览量: 3190　<a href="/Reviews/11466,1.shtml"><span>跟帖 0 条</span></a></div>
    #       <div class="intro">司法介入网络黑色公关事件，如同引爆这一行业的一枚重磅炸弹。“这不是网络营销的行业杯具，而是这个社会的现实写照。”一名资深网络营销从业者颇有悲情色彩地在博客里写下这样的话。</div>
    #       <div class="content">
    #         <table width="100%" border="0" cellpadding="0" cellspacing="0" align="center">
    #           <tr>
    # 
    #             <td><div>　　实习生_ 蒋丽娟 记者_ 张小摩</div>
    # <div style="text-align: center;"><img height="328" width="500" alt="" src="/UserFiles/fckfiles/2010/11/09/08ed51a6d45045008534dfeae18675cc.jpg" /></div>
    # <div style="text-align: center;">　　网络已经植入人们的生活，公关的网络日益庞大，对于大众来说需要一双火眼金睛去雾里看花。</div>
    # <div>&nbsp;</div>
    # <div>　　这个被视为朝阳产业的行业，一直就未曾理直气壮地走入阳光。面对接手的&ldquo;脏活&rdquo;，一些公司在眼前利益与行业自律之间，仍要在内心进行一番激烈搏杀。天堂或者地狱，往往就在一念之间。</div>
    # <div>&nbsp;</div>
    # <div><b>　　网络公关成为&ldquo;标配&rdquo;</b></div>
    re_chapter_content = re.compile(
        u'<div[^>]+class="body"[^>]*>' +
        u'.*?' +
        u'<div[^>]+class="dtitle"[^>]*>\s*' +
        u'<h1>(?P<title>.+?)</h1>' +
        u'.*?' +
        u'<div[^>]+class="intro"[^>]*>(?P<intro>.+?)</div>' +
        u'.*?' +
        u'<div[^>]+class="content"[^>]*>\s*' +
        u'<table[^>]*>' +
        u'(?P<content>.+?)' +
        u'</table>' +
        u'', re.IGNORECASE | re.DOTALL)

    # <div style="text-align: center;"><img alt="" src="/UserFiles/fckfiles/2010/11/09/a85d1c8ebc0347eaadcf81829cf7edc3.jpg" height="757" width="500"></div>
    # <div style="text-align: center;">　　网络成为公关公司新的“武器”。摄影_孙海</div>
    re_chapter_content_img = re.compile(
        u'<div[^>]*>\s*(?:<a[^>]*>)?\s*<img[^>]*src="(?P<url>[^"]+)"[^>]*>(?:</a>)?</div>\s*' +
        u'(?:<div[^>]*>(?P<desc>[^<]+)</div>)?' +
        u'', re.IGNORECASE | re.DOTALL)

    # <div><b><span style="font-size: medium;">　<span style="color: rgb(0, 0, 255);">　网络灰社会</span></span></b></div>
    re_section_title = re.compile(
        u'<div[^>]*><b>(?P<title>.+?)</b></div>',
        re.IGNORECASE | re.DOTALL)

    def parse_chapter(self, path, inputter):
        # 读入正文
        chapter_content = inputter.read_all(path)

        m = self.re_chapter_content.search(chapter_content)
        if not m:
#            print chapter_content
            raise NotParseableError(u"{file} is not parseable by {parser}. '{path}' is not parseable!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__, path=path))

        if self.re_chapter_content_img:
            normalizer = HtmlContentNormalizer(inputter=inputter, re_imgs=self.re_chapter_content_img)
        else:
            normalizer = HtmlContentNormalizer(inputter=inputter)

        #print m.group("content")
        #print normalizer.normalize(m.group("content"))

        d = m.groupdict()
        chapter = Chapter()
        for k in dir(chapter):
            if not inspect.ismethod(getattr(chapter, k)) and d.has_key(k):
                setattr(chapter, k, title_normalize_from_html(d[k]))

        if chapter.cover and isinstance(chapter.cover, basestring):
            chapter.cover = self.parse_cover(chapter.cover, inputter)

        chapter.content = list()
        start_pos = 0
        content = m.group("content")

        if self.re_section_title:
            for m in self.re_section_title.finditer(content):
                if m.start() > start_pos:
                    chapter.content.extend(normalizer.normalize(content[start_pos:m.start()]))

                chapter.content.append(SectionTitle(title_normalize_from_html(m.group("title"))))

                start_pos = m.end()

        if start_pos < len(content):
            chapter.content.extend(normalizer.normalize(content[start_pos:]))

        return chapter

    def parse_level(self, parent, content, levels, idx, inputter):
        for m in levels[idx].finditer(content):
            d = m.groupdict()
            chapter = None

            if d.has_key('url'):
                chapter = self.parse_chapter(d['url'], inputter)

            # 外面的title优先级高
            if d.has_key('title'):
                # 没有chapter，表示没有url，这是一个分类用的章节，不对应具体文章
                if not chapter:
                    chapter = Chapter()

                chapter.title = title_normalize_from_html(d['title'])

            if chapter:
                # cover、intro、author等都是列表的优先级更高
                if d.has_key('cover'):
                    chapter.cover = self.parse_cover(d['cover'], inputter)

                if d.has_key('intro'):
                    chapter.intro = normalizer.normalize(d['intro'])

                if d.has_key('author'):
                    chapter.author = title_normalize_from_html(d['author'])

                chapter.parent = parent
                logging.debug(u"        {indent}Chapter: {title}".format(indent=u"  "*idx, title=chapter.title))

            # 如果有content，则表示有子章节，放到待处理列表中，进入下一轮处理
            if d.has_key('content') and idx + 1 < len(levels):
                self.parse_level(
                    chapter if chapter else parent, 
                    d['content'],
                    levels,
                    idx + 1,
                    inputter)

            # 有内容才添加
            if chapter and (chapter.subchapters or chapter.content):
                parent.subchapters.append(chapter)

    def parse(self, inputter, top_level, book_title, book_author):
        if not inputter.entry:
            raise notparseableerror(u"{file} is not parseable by {parser}".format( file=inputter.fullpath(), parser=self.__class__.__name__))

        file_content = inputter.read_all(inputter.entry)
        #print file_content

        # 找出基本信息
        book = Book()
        content = file_content
        for i in xrange(len(self.re_info)):
            m = self.re_info[i].search(content)
            if not m:
                raise NotParseableError(u"{file} is not parseable by {parser}. cover not found!".format(
                    file=inputter.fullpath(), parser=self.__class__.__name__))
           
            d = m.groupdict()
            for k in dir(book):
                if not inspect.ismethod(getattr(book, k)) and d.has_key(k):
                    setattr(book, k, title_normalize_from_html(d[k]))

                if d.has_key(u"content"):
                    content = d[u"content"] 

        logging.debug(u"    {title}".format(title=book.title))

        if isinstance(book.cover, basestring):
            book.cover = self.parse_cover(book.cover, inputter) 

        if not book.category:
            book.category = CATEGORY_NEWS_PAPER 

        for re_level in self.re_levels:
            root_chapter = Chapter()
            self.parse_level(root_chapter, file_content, re_level, 0, inputter)
            
            # 只要第一组能解释的表达式
            if len(root_chapter.subchapters) > 0:
                book.subchapters = root_chapter.subchapters
                break

        if len(book.subchapters) <= 0:
            raise NotParseableError(u"{file} is not parseable by {parser}. chapter not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 不需要重排TOC
        options.rearrange_toc = False

        return book
#   }}}

class AsciidocParser(Parser): # {{{
    # {{{ ---- Regexs
    re_image1 = re.compile(r"^!(?:\[(?P<alt>[^]]*)\])?\((?P<src>[^ )]+)(?:\s+\"(?P<title>[^\"]*)\")?\s*\)")
    re_image2 = re.compile(r"^image:(?P<src>[^ \t　[]+)(?P<attrs>\[[^]]*\])")

    re_footnote = re.compile(r"\s*\bfootnote:\[(?P<text>[^]]*)\]")

    re_block_titles = [
        re.compile(r"^\.(?P<title>[^. \t　].*)"),
    ]

    re_dequote = re.compile(r"^(?P<quote>[\"'])(?P<text>.*?)(?P=quote)$")

    re_literal = re.compile(r"^[ \t　]{1,6}(?P<content>.*)")

    re_quote = re.compile(r"^\[(?P<style>quote|verse)(?:,\s*(?P<attribution>[^,]+?)\s*(?:,\s*(?P<citetitle>[^]]+?)\s*)?)?]")

    re_paragraph_end = re.compile(r"^[ \t　]*$|^\|==+")

    re_quoted_text = re.compile(r"(?P<attrs>\[[^]]*\])?(?P<quote_char>\*\*|\+\+|__|##)(?P<text>.*?)(?P=quote_char)")
    
    re_head_attribute = re.compile(r"^:(?P<name>[^:]+):\s*(?P<value>.*?)\s*$")

    re_attributes = re.compile(r"^\[(?P<attrs>[^\]]+)\]\s*$")

    re_table_begin = re.compile(r"^\|===+\s*$")
    re_table_end = re_table_begin

    re_empty_line = re.compile(r"^[ \t　]*$")

    re_section_title = re.compile("^(?P<leading_char>=+)\s+(?P<title>.*?)(?:\s+(?P=leading_char))?\s*$")

    re_delimited_block = re.compile("^(?P<delimit_char>[/\+-.\*_=])(?P=delimit_char){3,}\s*$")

    re_ruler = re.compile("^'{3,}\s*$")
    # }}}

    # {{{ ---- 在文件header中的属性名与ChapterInfo中字段的对应关系
    attributes = {
        "title":       "title",
        "subtitle":    "sub_title",
        "author":      "author",
        "series":      "series",
        "category":    "category",
        "publisher":   "publisher",
        "isbn":        "isbn",
        "publishdate": "publish_date",
        "publistver":  "publist_ver",
        "description": "intro",
    }
    # }}}

    # {{{ ---- class LineHolder
    class LineHolder(object):
        re_comment_line = re.compile(r"^//")
        def __init__(self, container):
            self.iter = container.__iter__()
            self.stacks = list()

        def __iter__(self):
            return self

        def next(self):
            while True:
                if self.stacks:
                    l = self.stacks.pop()
                else:
                    l = self.iter.next()

                if self.re_comment_line.match(l):
                    continue

                return l

        def push_back(self, v):
            self.stacks.append(v)
    # }}}

    # {{{ ---- func parse
    def parse(self, inputter, top_level, book_title, book_author):
        # {{{ ------ func concat_lines
        def concat_lines(lines):
            """ 把多行按asciidoc规则合并。连续的非空行将连接为一行。返回合并后的行 """
            result = list()
            last_line = u""

            for line in lines:
                if self.re_empty_line.match(line):
                    if last_line:
                        result.append(last_line)
                        last_line = u""
                        
                    continue

                # 非空行
                trimed = trim(line)
                if last_line and is_alphanum(last_line[-1]) and is_alphanum(line[0]):
                    last_line += u" "

                last_line += line

            if last_line:
                result.append(last_line)

            return result
        # }}}
                
        # {{{ ------ func parse_attributes
        def parse_attributes(line, last_attrs):
            """ 解释属性行

            返回True表示line是属性行，包含的属性将合并到last_attrs中。
            False表示不是属性行。"""

            if not line:
                return False

            m = self.re_attributes.match(line)
            if m:
                attrs = dict()

                position = 0
                for attr in m.group("attrs").split(","):
                    if "=" in attr:
                        # 命名参数
                        (name, val) = attr.split("=", 1)
                        m = self.re_dequote.match(val)
                        if m:
                            attrs[name] = m.group("text")
                        else:
                            attrs[name] = val
                    else:
                        # 定位参数，从0开始
                        m = self.re_dequote.match(attr)
                        if m:
                            attr = m.group("text")

                        attrs[position] = attr
                        position += 1

                if attrs:
                    for k in attrs:
                        last_attrs[k] = attrs[k]

                    return True

            return False
        # }}}

        # {{{ ------ func get_paragraph
        def get_paragraph(line_holder, retain_line_break=False):
            lines = list()
            for line in line_holder:
                if not self.re_paragraph_end.match(line):
                    lines.extend([trim(l) for l in line.splitlines()])
                else:
                    line_holder.push_back(line)
                    break

            if not retain_line_break:
                # 不保留换行符，把所有连续行连接为一行
                lines = concat_lines(lines)

            return lines
        # }}}

        # {{{ ------ func replacements
        def replacements(text):
            result = unescape(text)
            # TODO: 对(C)等字符序列进行替换
            trans_pairs= (
                (u"(C)",  u"©"),
                (u"(TM)", u"™"),
                (u"(R)",  u"®"),
                (u"--",   u"—"),
                (u"...",  u"…"),
                (u"->",   u"→"),
                (u"<-",   u"←"),
                (u"=>",   u"⇒"),
                (u"<=",   u"⇐"),
            )

            for f, t in trans_pairs:
                result = result.replace(f, t)

            return result
        # }}}

        # {{{ ------ func parse_footnote
        def parse_footnote(text):
            elements = list()
            start = 0
            for me in self.re_footnote.finditer(text):
                if me:
                    if me.start() != start: # 匹配前的部分
                        elements.append(replacements(text[start:me.start()]))

                    elements.append(FootNote(me.group("text")))
                    start = me.end()

            if start != len(text):
                elements.append(replacements(text[start:]))

            return elements
        # }}}

        # {{{ ------ func parse_quoted_text
        def parse_quoted_text(text):
            elements = list()
            start = 0
            for me in self.re_quoted_text.finditer(text):
                if me.start() != start: # 匹配前的部分
                    elements.extend(parse_footnote(text[start:me.start()]))

                attrs = dict()
                parse_attributes(me.group("attrs"), attrs)

                quote_char = me.group("quote_char")
                if quote_char == "__":
                    elements.append(Emphasized(parse_quoted_text(me.group("text"))))
                elif quote_char == "**":
                    elements.append(Strong(parse_quoted_text(me.group("text"))))
                elif quote_char == "++":
                    elements.append(Monospaced(parse_quoted_text(me.group("text"))))
                elif quote_char == "^":
                    elements.append(Superscript(parse_quoted_text(me.group("text"))))
                elif quote_char == "~":
                    elements.append(Subscript(parse_quoted_text(me.group("text"))))
                else:
                    keyword = attrs[0] if attrs.has_key(0) else u""

                    if keyword:
                        elements.append(StyledText(
                            keyword,
                            parse_quoted_text(me.group("text"))))
                    else:
                        elements.extend(parse_quoted_text(me.group("text")))

                start = me.end()

            if start != len(text):
                elements.extend(parse_footnote(text[start:]))

            return elements
        # }}}
                            
        # {{{ ------ func parse_chapter_attributes
        def parse_chapter_attributes(line_holder, chapter, last_attrs):
            for line in line_holder:
                m = self.re_head_attribute.match(line)
                if m:   # 是属性行
                    attr_name = m.group("name")
                    attr_value = m.group("value")

                    # 对属性值进行处理
                    if not attr_name.endswith("!"): # 如果以!结束，表示跳过此项
                        # attr_name lower case, alphanumeric, dash and
                        # underscore characters only — all other characters deleted
                        attr_name = re.sub(r"[^0-9a-zA-Z_-]", "", attr_name.lower())
                        last_attrs[attr_name] = attr_value
                else:
                    line_holder.push_back(line)
                    break

            for attr_name in last_attrs:
                attr_value = last_attrs[attr_name]

                if attr_name in self.attributes and not getattr(chapter, self.attributes[attr_name]):
                    setattr(chapter, self.attributes[attr_name], attr_value)
                elif attr_name == "cover" and inputter.exists(attr_value):
                    chapter.cover = InputterImg(attr_value, inputter)
        # }}}

        # {{{ ------ func handle_table
        def handle_table(line, line_holder, content, last_attrs):
            def append_row(table, row_text, sep="|"):
                row = list()
                for cell in row_text.split(sep):
                    try:
                        row.append(list())
                        lh = self.LineHolder(cell.splitlines())
                        while True:
                            parse_block(lh, row[-1])
                    except StopIteration:
                        pass

                table.append_row(row)

            # 识别是否开始一个表格
            m = self.re_table_begin.match(line)
            if not m:
                return False

            table = Table()
            try:
                row = u""
                for line in line_holder:
                    if self.re_table_end.match(line):
                        break

                    if line and line[0] == "|":
                        if row:
                            append_row(table, row)
                            row = u""

                        row = line[1:]
                    else:
                        row = row + "\n" + line
            finally:
                if row:
                    append_row(table, row)

                content.append(table)

            return True
        # }}}

        # {{{ ------ func handle_image
        def handle_image(line, content):
            # 处理图片
            m = self.re_image1.match(line)
            if m:
                # 图片
                content.append(InputterImg(urldecode(m.group("src")), inputter, m.group("title")))
                return True

            m = self.re_image2.match(line)
            if m:
                # 图片
                attrs = dict()
                parse_attributes(m.group("attrs"), attrs)

                alt = u""
                if attrs.has_key(0):
                    alt = attrs[0]
                elif attrs.has_key(ASCIIDOC_ATTR_ALT):
                    alt = attrs[ASCIIDOC_ATTR_ALT]

                title = u""
                if attrs.has_key(ASCIIDOC_ATTR_TITLE):
                    title = attrs[ASCIIDOC_ATTR_TITLE]

                content.append(InputterImg(urldecode(m.group("src")), inputter, title))
                return True

            return False
        # }}}

        # {{{ ------ func handle_block_title
        def handle_block_title(line, content):
            for re_block_title in self.re_block_titles:
                m = re_block_title.match(line)
                if m:
                    # 节标题
                    content.append(SectionTitle(title_normalize_from_html(m.group("title"))))
                    return True

            return False
        # }}}

        # {{{ ------ func handle_literal
        def handle_literal(line, line_holder, content):
            # 识别是否开始一个literal block（由缩进引起）
            m = self.re_literal.match(line)
            if not m:
                return False

            # 有缩进的行，是Literal
            line_holder.push_back(line)

            content.append(
                Literal(
                    get_paragraph(line_holder, retain_line_break=True)))

            return True
        # }}}

        # {{{ ------ func handle_delimited_block
        def handle_delimited_block(line, line_holder, content, last_attrs):
            m = self.re_delimited_block.match(line)
            if not m:
                return False

            delimit_char = m.group("delimit_char")

            lines = list()
            r = re.compile(u"^[{delimit_char}]{{4,}}\s*$".format(delimit_char=delimit_char))

            try:
                for l in line_holder:
                    if r.match(l):
                        break
                    else:
                        lines.append(l)
            except StopIteration:
                logging.error(u"Can't find end delimit block: '" + line + u"'")
                raise

            lh = self.LineHolder(lines)
            if delimit_char == "_":
                # quote block
                attribution = u""
                citetitle = u""

                if last_attrs.has_key(0) and last_attrs[0] == "quote":
                    # 开始一个引用块
                    attribution = last_attrs[1] if last_attrs.has_key(1) else u""
                    citetitle = last_attrs[2] if last_attrs.has_key(2) else u""

                content.append(
                    Quote(
                        parse_blocks(self.LineHolder(lines)),
                        attribution,
                        citetitle))
            elif delimit_char == ".":
                # literal block
                content.append(Literal(lines))
            else:
                content.append(BlockContainer(parse_blocks(self.LineHolder(lines))))

            return True
        # }}}

        # {{{ ------ func parse_paragraph
        def parse_paragraph(line_holder, content, last_attrs):
            if last_attrs.has_key(0):
                role = last_attrs[0]
                if role == "quote":
                    # 开始一个引用块
                    attribution = last_attrs[1] if last_attrs.has_key(1) else u""
                    citetitle = last_attrs[2] if last_attrs.has_key(2) else u""

                    content.append(
                        Quote(
                            [ Line(parse_quoted_text(l)) for l in get_paragraph(line_holder) ],
                        attribution,
                        citetitle))
                else:
                    # 指定了class
                    content.append(
                        StyledBlock(
                            role,
                            [ Line(parse_quoted_text(l)) for l in get_paragraph(line_holder)]))
            else:
                for l in get_paragraph(line_holder):
                    content.append(Line(parse_quoted_text(l)))
        # }}}

        # {{{ ------ func parse_block
        def parse_block(line_holder, content, last_attrs, line=None):
            """ 解释除了标题、表格以外的内容.
            
            每次处理一个block。

            会抛出StopIteration异常 """
            if line is None:
                line = line_holder.next()

            if self.re_empty_line.match(line):
                return

            if handle_table(line, line_holder, content, last_attrs):
                return

            if handle_literal(line, line_holder, content):
                return

            if handle_image(line, content):
                return

            if handle_block_title(line, content):
                return

            if handle_delimited_block(line, line_holder, content, last_attrs):
                return

            if self.re_ruler.match(line):
                # 插入<hr>
                content.append(Ruler())
                return

            line_holder.push_back(line)

            # 正文内容
            parse_paragraph(line_holder, content, last_attrs)
        # }}}

        # {{{ ------ func parse_blocks
        def parse_blocks(line_holder, last_attrs=dict()):
            lines = list()

            try:
                while True:
                    line = line_holder.next()

                    # 处理属性行
                    if parse_attributes(line, last_attrs):
                        continue

                    parse_block(line_holder, lines, last_attrs, line=line)

                    last_attrs.clear()
            except StopIteration:
                pass

            return lines
        # }}}

        # {{{ ------ func parse_section_body
        def parse_section_body(line_holder, chapter, last_attrs):
            logging.debug(u"AsciidocParser.parse_secion_body")

            try:
                while True:
                    line = line_holder.next()

                    # 处理属性行
                    if parse_attributes(line, last_attrs):
                        continue

                    # 处理title
                    m = self.re_section_title.match(line)
                    if m:   
                        level = len(m.group("leading_char"))

                        if level <= chapter.level:
                            line_holder.push_back(line)
                            return

                        # 子章节
                        curr_chapter = Chapter()
                        curr_chapter.title = title_normalize(m.group("title"))
                        curr_chapter.level = level
                        logging.debug(u"{indent}    Level {level} toc: {title}".format(
                            indent=u"  "*(curr_chapter.level+3*inputter.nested_level), level=curr_chapter.level, title=curr_chapter.title))

                        # 标题行
                        curr_chapter.parent = chapter
                        chapter.subchapters.append(curr_chapter)

                        parse_chapter_attributes(line_holder, curr_chapter, last_attrs)
                        
                        last_attrs.clear()
                        parse_section_body(line_holder, curr_chapter, last_attrs)
                    else:
                        line_holder.push_back(line)
                        parse_block(line_holder, chapter.content, last_attrs)
                        last_attrs.clear()

            except StopIteration:
                pass
        # }}}

        logging.debug(u"AsciidocParser.parse")

        if not inputter.entry or (inputter.entry[-4:].lower() != ".txt" and inputter.entry[-9:].lower() != ".asciidoc"):
            raise NotParseableError(u"{file} is not parseable by {parser}. Not asciidoc file!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        root_chapter = Chapter()
        chapter_stack = [root_chapter]
        curr_chapter = chapter_stack[-1]

        line_holder = self.LineHolder(inputter.read_lines(inputter.entry))
        last_attrs = dict()

        parse_section_body(line_holder, root_chapter, last_attrs) 
        book = Book()

        # 如果root_chapter只有一个子章节，则直接使用该章节
        if len(root_chapter.subchapters) == 1:
            root_chapter = root_chapter.subchapters[0]

        # 把root_chapter中的所有属性拷贝到book中
        chapter_attrs = vars(root_chapter)
        for n in chapter_attrs:
            if hasattr(book, n):
                setattr(book, n, chapter_attrs[n])

        if not book.title:
            book.title = book_title

        if not book.author:
            book.author = book_author

        return book
    # }}}
#   }}}

#   {{{ -- CollectionParsers
class CollectionParser(Parser): # {{{
    default_entrys = ()     # 缺省入口文件，可以被调用者通过inputer中指定来覆盖
    force_entrys = ()       # 本Parser只能使用此入口文件，会覆盖inputter.entry

    re_comment = re.compile(u"<!--.*?-->")
    re_remove_querys = re.compile(u"[#\?].*$")
    re_auto_levels  = ()    # 多个表达式，初始不区分级别，按遇到的先后定顺序
    re_links   = ()
    re_extra     = None
    re_extra_end = None
    cover_base = () # 如果当前目录下，找不到封面，则用这里的值作为前缀试试
    root_base = ()  # 如果当前目录下，找不到书本，则用这里的值作为前缀试试

    # 在找不到links的情况下，可以跟随这里的链接去尝试一下
    re_alt_entry_links = ()

    def parse(self, inputter, top_level, book_title, book_author):
        book = Book()
        book.title  = book_title
        book.author = book_author
        extra_chapters = list()
        subbook_count = 0
        first_subbook_cover = None

        normalizer = HtmlContentNormalizer(inputter=inputter)

        if self.force_entrys:
            # 强制指定入口文件
            index_files = self.force_entrys
        elif inputter.entry:
            # 如果已经指定了入口文件则直接使用之
            index_files = (inputter.entry, )
        else:
            index_files = self.default_entrys

        for index_file in index_files:
            local_extras = list()
            root_chapter = Chapter()
            root_chapter.level = top_level
            chapter_stack = [root_chapter]

            if not inputter.isfile(index_file):
                continue

            logging.debug(u"{indent}    Parsing {file}".format(
                file=inputter.fullpath(index_file), indent=u"      "*inputter.nested_level))

            file_content = inputter.read_all(index_file)
            file_content = self.re_comment.sub(u"", file_content)

            links = list()
            alt_entry_links = set()

            level_map = dict()  # 把re_auto_levels中的级别根据出现先后确定的级别

            # 扫描整个文件，找出所有链接，保存到links中
            next_pos = 0   # 开始处理的位置
            while next_pos < len(file_content):
                # next_pos指明了下一个处理点（或下一行的开始）
                start_pos = next_pos

                file_content = file_content[start_pos:]

                # 下次缺省从下个换行开始处理。因此要找到下个换行的位置作为next_pos的缺省值
                m = re.search("[\r\n]+", file_content)
                if m:
                    next_pos = m.end()
                else:
                    next_pos = len(file_content)

                for re_alt_entry_link in self.re_alt_entry_links:
                    m = re_alt_entry_link.match(file_content)
                    if m:
                        logging.debug(u"      Match alt_entry '{1}': '{0}'...".format(re_alt_entry_link.pattern, m.group("root")))
                        alt_entry_links.add(m.group("root"))

                #print line
                for re_link in self.re_links:
                    #print re_link.pattern
                    m = re_link.match(file_content)

                    if not m:
                        continue

                    next_pos = m.end()

                    root  = self.re_remove_querys.sub(u"", m.group("root"))
                    title = title_normalize_from_html(m.group("title"))

                    group_dict = m.groupdict()
                    author = group_dict["author"] if group_dict.has_key("author") else book_author
                    intro = HtmlContentNormalizer(inputter).normalize(group_dict["intro"]) if group_dict.has_key("intro") else u""

                    cover = None
                    if group_dict.has_key("cover"):
                        if inputter.isfile(group_dict["cover"]):
                            cover = self.parse_cover(group_dict["cover"], inputter) 
                        else:   # 尝试以cover_base中的值作为前缀来查找封面
                            if isinstance(self.cover_base, basestring):
                                self.cover_base = (self.cover_base,) 

                            for base in self.cover_base:
                                cover_file = os.path.normpath(os.path.join(base, group_dict["cover"]))
                                if inputter.isfile(cover_file):
                                    cover = self.parse_cover(cover_file, inputter)
                                    break

                    if not inputter.exists(root):
                        # 看看能不能在root_base目录下找到一个存在的root子目录
                        if isinstance(self.root_base, basestring):
                            self.root_base = (self.root_base,)

                        for base in self.root_base:
                            newroot = os.path.normpath(os.path.join(base, root))
                            if inputter.exists(newroot):
                                root = newroot
                                break

                    level = chapter_stack[-1].level + 1
                    subinputter = SubInputter(inputter, root)
                    subpath = subinputter.fullpath()

                    # 子书应该在本inputter的子目录下，如果出了本目录就不算
                    if not inputter.is_subpath(root):
                        logging.debug(u"{indent}Skip sub book in {index_file}: {path}: {title}{author_info}, not in subpath of {curr_path}".format(
                            indent=u"  "*(level+3*inputter.nested_level), 
                            level=level,
                            index_file=inputter.fullpath(index_file),
                            curr_path=inputter.fullpath(u""),
                            path=root, title=title,
                            author_info=u"/" + author if author else u""))
                        continue

                    logging.info(u"{indent}Found level {level} sub book in {index_file}: {path}: {title}{author_info}{cover_info}".format(
                        indent=u"  "*(level+3*inputter.nested_level), 
                        level=level,
                        index_file=inputter.fullpath(index_file),
                        path=subinputter.fullpath(), title=title,
                        author_info=u"/" + author if author else u"",
                        cover_info=u" with cover" if cover else u""))

                    for link in links:
                        if link['path'] == subpath:
                            # # 本文件已经处理过了，不再重复处理。前一次也不加单独的父章节了
                            # chapter = link['chapter']
                            # if chapter and chapter.parent:
                            #     # 把前一次的父章节去掉，移到祖父章节下
                            #     for subchapter in chapter.subchapters:
                            #         subchapter.parent = chapter.parent
                            #
                            #     idx = chapter.parent.subchapters.index(chapter)
                            #     chapter.parent.subchapters[idx:idx+1] = chapter.subchapters
                            #
                            #     # 标记一下，下次就不会再处理了
                            #     link['chapter'] = None
                            #     
                            # logging.info(u"{indent}      Skip duplicated sub book: {path}: {title}".format(
                            #     indent=u"  "*(level+3*inputter.nested_level), path=subinputter.fullpath(), title=title))

                            break
                    else:
                        # 已经处理过，不再重复处理
                        if parsed_files.has_key(subpath):
                            if not url2chapter.has_key(subpath):
                                continue

                            chapter = url2chapter[subpath]
                            if url2chapter[subpath].level <= level:
                                logging.info(u"{indent}      Sub book has already processed: {path}: {title}".format(
                                    indent=u"  "*(level+3*inputter.nested_level), path=subinputter.fullpath(), title=title))
                            else:
                                # 目前的级别比之前低，移到本位置
                                logging.info(u"{indent}      Moving sub book {path}: {title} from level {orig_level} of {orig_parent_title} to level {level} of {parent_title}".format(
                                    indent=u"  "*(level+3*inputter.nested_level),
                                    path=subpath, title=title,
                                    orig_level=chapter.level,
                                    orig_parent_title=chapter.parent.title,
                                    level=level,
                                    parent_title=chapter_stack[-1].title))

                                chapter.title = title
                                chapter.parent.subchapters.remove(chapter)
                                chapter.parent=chapter_stack[-1]
                                chapter.parent.subchapters.append(chapter)
                                chapter.level = level
                                subbook_count += 1

                            continue

                        # 该链接未出现过
                        logging.debug("{indent}      Trying subbook...".format(indent=u"  "*(level + 3*inputter.nested_level)))
                        subbookinfo = Parser.parse_book(subinputter, level, title, author, cover)
                        assert(subbookinfo)

                        chapter = Chapter()
                        url2chapter[subinputter.fullpath()] = chapter
                        chapter.title  = title if title else subbookinfo.title
                        chapter.author = author if author else subbookinfo.author
                        chapter.cover  = cover if cover else subbookinfo.cover
                        chapter.intro  = intro if intro else subbookinfo.intro
                        chapter.subchapters = subbookinfo.subchapters

                        for subchapter in chapter.subchapters:
                            subchapter.parent = chapter

                        chapter.parent = chapter_stack[-1]
                        chapter.parent.subchapters.append(chapter)

                        reset_level(chapter, level)

                        # 记录subbook的信息，特别是记录第一本书的封面
                        subbook_count += 1
                        if cover and not first_subbook_cover:
                            first_subbook_cover = cover

                        links.append({
                            'path'     : subinputter.fullpath(),
                            'chapter'  : chapter,
                        })

                    # 匹配成功，不再检查后续的re_links
                    break

                for i in range(0, len(self.re_auto_levels)):
                    m = self.re_auto_levels[i].match(file_content)
                    if m:
                        if level_map.has_key(i):
                            level = level_map[i]
                        else:
                            level = top_level + 1 + len(level_map)
                            level_map[i] = level

                        while level <= chapter_stack[-1].level:
                            chapter_stack.pop()
                    
                        chapter = Chapter()
                        chapter.title = title_normalize_from_html(m.group(1))
                        chapter.level = level
                        logging.debug(u"{indent}  Level {level} toc: {title}".format(
                            indent=u"  "*(chapter.level+3*inputter.nested_level), level=chapter.level, title=chapter.title))

                        chapter.parent = chapter_stack[-1]
                        chapter.parent.subchapters.append(chapter)
                        chapter_stack.append(chapter)
                        break

                # 处理嵌入页面中的作品简介、作者简介等内容
                if self.re_extra:
                    m = self.re_extra.match(file_content)
                    if m:
                        chapter = Chapter()
                        chapter.title = title_normalize_from_html(m.group("title"))

                        logging.debug(u"{indent}    Found extra chapter: {title}".format(
                            title=chapter.title, indent=u"      "*inputter.nested_level))

                        next_pos = m.end()
                        chapter.content.extend(normalizer.text_only(m.group("content")))

                        if len(chapter.content) > 0:
                            local_extras.append(chapter)

            if len(links) == 0:
                for alt_entry_link in alt_entry_links:
                    try:
                        logging.debug(u"  Tring alt entry: '{0}'".format(alt_entry_link))

                        subinputter = SubInputter(inputter, alt_entry_link)
                        subpath = subinputter.fullpath()

                        # 已经处理过，不再重复处理
                        if parsed_files.has_key(subpath):
                            continue;

                        logging.debug("    Trying subbook...")
                        subbookinfo = Parser.parse_book(subinputter, u"", book_author)

                        root_chapter.cover  = subbookinfo.cover
                        root_chapter.subchapters = subbookinfo.subchapters

                        for subchapter in root_chapter.subchapters:
                            subchapter.parent = root_chapter

                        break
                    except NotParseableError as e:
                        logging.debug(u"    '{0}' is not parseable".format(alt_entry_link))
                        continue
                else:
                    logging.debug(u"{indent}      No links found. Skipping {file}".format(
                        file=index_file, indent=u"      "*inputter.nested_level))

                    continue

            # 把本索引文件中找到的内容加入到book中
            book.subchapters.extend(root_chapter.subchapters)
            extra_chapters.extend(local_extras)

            for subchapter in book.subchapters:
                subchapter.parent = None

        if len(book.subchapters) == 0:
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 插入前面的额外章节
        book.subchapters[0:0] = extra_chapters

        # 如果只有一本子书，则把该子书的封面作为封面
        if not book.cover and first_subbook_cover and subbook_count==1:
            book.cover = first_subbook_cover

        return book
#     }}}

class HtmlBuilderCollectionParser(CollectionParser): # {{{
    default_entrys = ( u"cover.html", u"cover.htm", u"index.htm" )

    re_auto_levels  = (
        re.compile(u".*<td[^>]*class=m6[^>]*>([^<]+)</td>.*", re.IGNORECASE),
        re.compile(u".*<td[^>]*class=m2[^>]*>([^<]+)</td>.*", re.IGNORECASE),
        )

    re_links = (
        re.compile(u".*<td[^>]*>[ \t　]*<A[^>]*HREF=['\"](?P<root>[^\"'<>]+)/index\.html?['\"]\s+title=进入阅读[^>]*>(?P<title>[^<]+)</A>.*", re.IGNORECASE),
        # <td align="center" style="border: 1 dotted #996600"><a href="zw8/index.htm"><img src="zw8.jpg" width="150" height="220" border="0" alt="异变"></a></td>
        re.compile(u".*<td[^>]*>\s*<a[^>]+href=\"(?P<root>[^\"<>]+)/index\.html?\"[^>]*>\s*<img[^>]+src=\"(?P<cover>[^\"]+)\"[^>]*alt=\"(?P<title>[^\"]+)\"[^>]*>\s*</a>(?:&nbsp;|　|…|\s)*(?:\d*\s*)?</td>.*", re.IGNORECASE),
        re.compile(
            u".*" +
            u"<a[^>]*\shref=(?P<quote1>['\"])?(?P<root>[^<>]*?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*>" +
            u"<img src=(?P<quote2>['\"])?(?P<cover>.*?)(?(quote2)(?P=quote2)|(?=\s|>))[^>]*\s" +
            u"alt=(?P<quote3>['\"])?(?P<title>.*?)☆进入阅读[^>]*>" +
            u"</a>"),
        # <a href=wsdzc/index.html class=f5 title=法医秦明系列II☆点击进入>无声的证词</a><br>
        re.compile(
            u".*" +
            u"<a[^>]*\shref=(?P<quote1>['\"])?(?P<root>[^<>]+/index\.html?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*>" +
            u"(?P<title>[^<>]+)" +
            u"</a>"),
    )

    re_extra = re.compile(u".*<font class=m2>(?P<title>[^<]+?)(?:[:：])?</font><br>\s*(?P<content>(?:.\|\s)*?)<(?!br>)", re.IGNORECASE)

    # 在找不到links的情况下，可以跟随这里的链接去尝试一下
    re_alt_entry_links = (
        # 若花燃燃作品集:<td><a href=cover.html class=fl><img src=image/back.gif border=0 alt=上页><img src=image/return.gif border=0 alt=封面></a><a href=1/index.html class=fl><img src=image/next.gif border=0 alt=下页></a></td>
        re.compile(u".*<a[^>]*\shref=(?P<quote1>['\"])?(?P<root>[^<>]*index\.html?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*><img[^>]*alt=['\"]?下?页"),
        re.compile(u".*<a[^>]+href=(?P<quote1>[\"'])?(?P<root>[^<>]*?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*title=(?P<quote2>['\"])?点击进入(?(quote2)(?P=quote2)|(?=\s|>))[^>]*>\s*封面图片欣赏\s*</a>", re.IGNORECASE | re.DOTALL),
    )
#     }}}

class EasyChmCollectionParser(CollectionParser): # {{{
    default_entrys = ( u"cover.html", u"cover.htm", u"start.html", u"start.htm", u"index.html", u"index.htm" )

    re_links = (
        re.compile(u"^\s*<a rel=\"(?P<rel>[^\"]*)\" title=\"开始阅读\" href=\"(?P<root>[^<>\"]+)/(start|index)\.html?\">(?P<title>[^<]+)</a>\s*", re.IGNORECASE),
                # <a rel="pic/12.jpg" title="告诉你一个不为所知的：神秘周易八卦" href="12/start.htm">作者：天行健0006</a>
        re.compile(u"^\s*<a rel=\"(?:(?P<cover>[^\"]+?\.(?:jpg|png|gif|JPG|PNG|GIF))|[^\"]*)\" title=\"(?P<title>[^\"]+)\" href=\"(?P<root>[0-9]+)/(start|index)\.html?\">(?:作者：(?P<author>[^<]*)|[^<]*)</a>\s*", re.IGNORECASE),
        # <span class="STYLE27">1. <a href="魔法学徒/start.htm" target="main_r">《魔法学徒》（封面全本）作者：蓝晶</a><br>
        # 2. <a href="魔盗/start.htm" target="main_r">《魔盗》（珍藏全本）作者：血珊瑚</a></span><span class="STYLE27"><br>
        re.compile(u".*\\b\d+\.\s*<a\s[^>]*\\bhref=\"(?P<root>[^/<>]+)/(start|index)\.html?\"[^>]*>\s*《(?P<title>[^》]+)》(?:[^<]*作者[：:](?P<author>[^<]*)|[^<]*)</a>\s*", re.IGNORECASE),
            # <font face="宋体" size="2"><a href="3/start.htm">《独闯天涯》
            # <img src="3.jpg" class="image" width="100" height="125" style="border: 3px solid #FFFFFF"></a></font></td>
        re.compile(u".*<a\s[^>]*\\bhref=\"(?P<root>[^/<>]+)/(start|index)\.html?\"[^>]*>\s*《(?P<title>[^》]+)》(?:[^<]*作者[：:](?P<author>[^<]*)|<img\s\+[^>]*\\bsrc=\"(?P<cover>[^\"]*)\"[^>]*>\s*|[^<]*)</a>\s*", re.IGNORECASE | re.MULTILINE),
        re.compile(u".*\\b\d+\.\s*<a\s[^>]*\\bhref=\"(?P<root>[^/<>]+)/(start|index)\.html?\"[^>]*>\s*(?P<title>[^<]+)</a>\s*", re.IGNORECASE),
        # 《方想作品合集V1.1》作者：方想.chm
        re.compile(u".*<font class=f2>《(?P<title>[^》]+)》</font>\S*\s*" +
                   u"<tr>\s*<td align=\"center\"><a href=\"(?P<root>[0-9]+)/((?:start|index)\.html?)\">(?:<font[^>]*>)?\s*" +
                   u"<img\s+[^>]*\\bsrc=\"(?P<cover>[^\"]*)\"[^>]*>(?:</font>)?</a></tr>\s*" +
                   u"<td[^>]*>\s*" +
                   u"<p[^>]*>\s*<font class=f8><b>内容简介：</b><br>\s*" +
                   u"(?P<intro>(?:.|\s)*?)</font", re.IGNORECASE | re.MULTILINE),
    )

#     }}}

class EasyChmCollectionParser2(CollectionParser): # {{{
    force_entrys = ( u"index/js/book.js", u"js/book.js")

    re_links = (
        #booklist[0]=['噩盡島Ⅱ','<img src=../bookcover/01.jpg class=cover1>','1_1','莫仁','　　仙界回归百年，地球版图早已重划，……'];
        re.compile(u".*\w+\[\d+\]\s*=\s*\['(?P<title>[^']+)','<img src=(?P<cover>[^'\"]\S+)\s[^>]*>','(?P<root>[^'<>]+)','(?P<author>[^']+)','(?P<intro>[^']+)'\];", re.IGNORECASE),
        #booklist[0]=['神游','天涯凝望','1','徐公子胜治','　　面对文学与传说中的玄幻纷呈时，你是否也梦想拥有这份神奇的精彩人生？其实不必去遐想仙界与异星，玄妙的世界就在你我的身边，身心境界可以延伸到的极致之处。<br>　　这世上真有异人吗？真有神迹吗？——梦境可以化实！妄想可以归真！<br>　　一位市井中懵懂少年是如何成为世间仙侠，又如何遭遇红尘情痴？请舒展心灵的触角来《神游》。'];
        re.compile(u".*\w+\[\d+\]\s*=\s*\['(?P<title>[^']+)','[^']*','(?P<root>[^'<>]+)','(?P<author>[^']+)','(?P<intro>[^']+)'\];", re.IGNORECASE),
    )

    cover_base = ( u"index/", )
    root_base = ( u"txt/", )

#     }}}
#   }}}

class RedirectParser(Parser): # {{{
    re_redirects = (
        re.compile(
            u"<frameset\srows=\"\d+,\*\"[^>]*>\s*" +
            u"<frame\s[^>]*>\s*" +
            u"<frame\s[^>]*\\bsrc=\"(?P<url>[^\"]+)\"[^>]*>\s*" +
            u"</frameset>", re.IGNORECASE),
            
        re.compile(
            u"<table[^>]*>\s*" +
            u"<tr[^>]*>\s*" +
            u"<td[^>]*>\s*" +
            u"<iframe[^>]*>\s*(?:</iframe>)?\s*" +
            u"</td>\s*" +
            u"<td[^>]*>.*?</td>\s*" +
            u"<td[^>]*>\s*" + 
            u"<iframe\s[^>]*\\bsrc=\"(?P<url>[^\"]+)\"[^>]*>\s*(?:</iframe>)?\s*" +
            u"</td>\s*" +
            u"</tr>\s*" +
            u"</table>", re.IGNORECASE | re.DOTALL),

        # <p align="center"><a href="bbb.htm">
        # <img border="0" src="conver.jpg" width="300" height="435"></a></p>
        re.compile(
            u"<p\s+align=\"center\">\s*" +
            u"<a\s+href=\"(?P<url>[^\"]+)\">\s*" +
            u"<img\s[^<]*\\bsrc=\"con?ver.jpg\"[^>]*>\s*" +
            u"</a>\s*" +
            u"</p>", re.IGNORECASE),
        
        # <body topmargin="0" leftmargin="0" rightmargin="0" bottommargin="0" marginwidth="0" marginheight="0" style="overflow:hidden">
        # <iframe frameborder="0" style="width:100%;height:100%" src="cover.htm"></iframe>
        # </body>
        re.compile(
            u"<body[^>]*>\s*" +
            u"<iframe\\b[^>]*\\bsrc=[\"'](?P<url>[^\"']+)[\"'][^>]*></iframe>\s*" +
            u"</body[^>]*>", re.IGNORECASE),
    )


    def parse(self, inputter, top_level, book_title, book_author):
        if not inputter.entry:
            return None

        file_content = inputter.read_all(inputter.entry)
        for re_redirect in self.re_redirects:
            m = re_redirect.search(file_content)
            if m:   # 这个文件是重定向文件，以重定向后的文件为准
                url = m.group("url")

                cover = None
                try:
                    cover_file = m.group("cover")
                    if cover_file:
                        cover = InputterImg(cover_file, inputter)
                except:
                    pass

                title = book_title
                try:
                    title = m.group("title")
                except:
                    pass

                author = book_author
                try:
                    author = m.group("author")
                except:
                    pass

                logging.info(u"{indent}    {src} is redirected to {dest}".format(
                    indent=u"      "*inputter.nested_level, src=inputter.fullpath(), dest=url))

                book = Parser.parse_book(SubInputter(inputter, url), top_level, title=title, author=author, cover=cover)
                if book:
                    return book

        return None
#   }}}
# }}}

# {{{ Converters

#   {{{ -- func to_html
def to_html(content, img_resolver):
    html = u""

    if not content:
        return html

    if not isinstance(content, list):
        content = [ content, ]

    for line in content:
        if isinstance(line, basestring):
            html += u"".join((u"<p class='p'>", escape(line), u"</p>"))
        elif isinstance(line, ContentElement):
            html += line.to_html(img_resolver)
        elif isinstance(line, Img):
            if img_resolver is not None:    # 如果img_resolver是None，忽略图片
                try:
                    html += u"<div class='img'><img alt='{alt}' src='{src}' />{desc}</div>".format(
                        src = img_resolver(line) if img_resolver else line.filename(),
                        alt = escape(line.desc()) if line.desc() else u"img",
                        desc = u"<div class='desc'>{desc}</div>".format(desc=escape(line.desc())) if line.desc() else u""
                        )
                except:
                    if not options.skip_bad_img:
                        raise
        else:
            raise NotImplementedError(u"Don't know how to covert {0} to html!".format(type(line)))

    return html
#   }}}

#   {{{ -- func to_asciidoc
def to_asciidoc(content):
    if not isinstance(content, list):
        content = [ content, ]

    text = u""

    for line in content:
        if isinstance(line, basestring):
            text += line
            text += "\n\n"
        elif isinstance(line, InlineContainer):
            text += line.to_asciidoc()
            text += "\n\n"
        elif isinstance(line, ContentElement):
            text += line.to_asciidoc()
        elif isinstance(line, Img):
            try:
                text += u"\n\nimage:{src}[title=\"{desc}\"]\n\n".format(
                    src = u'{id}{ext}'.format(id=line.id(), ext=line.extension()),
                    desc = escape(line.desc()) if line.desc() else u"")
            except:
                if not options.skip_bad_img:
                    raise
        else:
            raise NotImplementedError(u"Don't know how to covert {0} to html!".format(type(line)))

    return text
#   }}}

#   {{{ -- func to_text
def to_text(content):
    if not isinstance(content, list):
        content = [ content, ]

    text = u""

    for line in content:
        if isinstance(line, basestring):
            text += line
            text += "\n"
        elif isinstance(line, InlineContainer):
            text += line.to_text()
            text += "\n"
        elif isinstance(line, ContentElement):
            text += line.to_text()
        elif isinstance(line, Img):
            pass    # 忽略图片
        else:
            raise NotImplementedError(u"Don't know how to covert {0} to html!".format(type(line)))

    return text
#   }}}

#   {{{ -- func content_size
def content_size(content):
    """ 计算内容content的大小 """
    if not isinstance(content, list):
        content = [ content, ]

    size = 0
    for line in content:
        if isinstance(line, basestring):
            size += len(line)
        elif isinstance(line, ContentElement):
            size += line.content_size()
    
    return size
#   }}}

#   {{{ -- func get_images
def get_images(*args):
    """ 取出content中包含的所有图片对象
    """
    for arg in args:
        if isinstance(arg, ChapterInfo):
            # 处理章节封面
            if arg.cover:
                yield arg.cover

            # 处理章节内容
            for img in get_images(arg.content):
                yield img

            # 处理子章节
            for img in get_images(arg.subchapters):
                yield img
        elif isinstance(arg, Img):
            yield arg
        elif isinstance(arg, ContentElement):
            # 引用中也可能有图片
            for img in arg.get_images():
                yield img
        elif isinstance(arg, list):
            for img in get_images(*arg):
                yield img
#   }}}

class Converter(object): # {{{
    def convert(self, outputter, book):
        raise NotImplementedError()

#   }}}

class HtmlConverter(object): # {{{
    def __init__(self, style):
        self.style   = style

    def get_img_destpath_(self, files, img):
        return files["image"][img.unique_key()]["filename"]

    def css_style(self, extra_css=""):
        return self.style + extra_css
    
    # {{{ ---- func cover_page
    def cover_page(self, files, filename, book, cover):
        html = U"""\
      <div class='book'>
      <div class='cover'><img alt="{title}" src="{cover}" /></div>
      </div>
""".format(
            title = unicode(escape(book.title)),
            cover = os.path.relpath(self.get_img_destpath_(files, cover), os.path.dirname(filename)))

        return html
    # }}}

    # {{{ ---- func title_page
    def title_page(self, filename, book):
        html = u"<div class='book'>"
        if not book.sub_title:
            html += u"""\
            <div class='title_page'>
                <div class='title'>{title}</div>
                <div class='author'>{author}</div>
            </div>
            """.format(
                title         = unicode(escape(book.title)),
                author        = unicode(escape(book.author)))
        else:
            html += u"""\
            <div class='title_page title_page_with_sub_title'>
                <div class='title'>{title}</div>
                <div class='sub_title'>{sub_title}</div>
                <div class='author'>{author}</div>
            </div>
            """.format(
                title         = unicode(escape(book.title)),
                sub_title     = unicode(escape(book.sub_title)),
                author        = unicode(escape(book.author)))

        html += u"</div>"
        return html;
    # }}}

    # {{{ ---- func title_cover_page
    def title_cover_page(self, files, filename, book, cover):
        html = u"<div class='book'>"
        if not book.sub_title:
            html += u"""\
            <div class='title_page title_cover_page'>
                <div class='cover'><img alt="{title}" src="{cover}" /></div>
                <div class='title'>{title}</div>
                <div class='author'>{author}</div>
            </div>
            """.format(
                title         = unicode(escape(book.title)),
                author        = unicode(escape(book.author)),
                cover         = os.path.relpath(self.get_img_destpath_(files, cover), os.path.dirname(filename)))
        else:
            html += u"""\
            <div class='title_page title_page_with_sub_title title_cover_page title_cover_page_with_sub_title'>
                <div class='cover'><img alt="{title}" src="{cover}" /></div>
                <div class='title'>{title}</div>
                <div class='sub_title'>{sub_title}</div>
                <div class='author'>{author}</div>
            </div>
            """.format(
                title         = unicode(escape(book.title)),
                sub_title     = unicode(escape(book.sub_title)),
                author        = unicode(escape(book.author)),
                cover         = os.path.relpath(self.get_img_destpath_(files, cover), os.path.dirname(filename)))

        html += u"</div>\n"
        return html;
    # }}}

    # {{{ ---- func toc_item
    def toc_item(self, files, filename, chapter):
        html = u"<li>\n"

        if chapter.cover:
            html += u"<a href='{link}' class='cover'><img src='{cover}' alt='{title}'/></a>\n".format(
                cover = os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)),
                link = os.path.relpath(chapter.entry_file, os.path.dirname(filename)),
                title = escape(chapter.title))

        html += u"<span class='info'>"

        html += u"<a href='{link}'><span class='title'>{title}</span></a>".format(
            link = os.path.relpath(chapter.entry_file, os.path.dirname(filename)),
            title = escape(chapter.title))

        if chapter.author:
            html += u"<span class='author'>{author}</span>".format(
                author = chapter.author)

        html += u"</span>\n"  # span.info

        intro_lines = u""
        if chapter.intro:
            intro_lines = to_text(chapter.intro)
            if len(intro_lines) > MAX_INLINE_INTRO_SIZE:
                intro_lines = intro_lines[:MAX_INLINE_INTRO_SIZE] + u"……"

            intro_lines = intro_lines.splitlines()

        html += u"<div class='intro'>{intro}</div>".format(
                intro = u"".join(
                    to_html(intro_lines, None)))

        html += u"</li>\n"

        return html
    # }}}

    # {{{ ---- func toc_page
    def toc_page(self, files, filename, book):
        html = u"<div class='book'>\n"
        html += u"<div class='toc_page'>\n"
        html += u"<div class='toc_title'>{title}</div>".format(title=u"目  录")
        html += u"<ul class='toc_list'>"

        for c in book.subchapters:
            html += self.toc_item(files, filename, c)

        html += u"</ul></div></div>\n"

        return html
    # }}}

    # {{{ ---- func chapter_cover_page
    def chapter_cover_page(self, files, filename, chapter):
        html = U"""\
      <div class='chapter'>
      <div class='cover_page'><div class='cover chapter_cover chapter_large_cover'><img alt="{title}" src="{cover}" /></div></div>
      </div>
""".format(
            title = escape(chapter.title_inner or chapter.title), 
            cover = os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)))

        return html
    # }}}

    # {{{ ---- func chapter_title_page
    def chapter_title_page(self, files, filename, chapter):
        title = chapter.title_inner or chapter.title

        extra_class = u""
        img = u""
        if chapter.cover:
            img = u"<div class='cover'><img alt='{title}' src='{cover}' /></div>".format(
                title = escape(title), 
                cover = os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)))

            extra_class += u"title_cover_page"

        if chapter.sub_title:
            extra_class += u"title_page_with_sub_title"

        html = u"""\
        <div class='chapter'>
        <div class='title_page {extra_class}' id='{id}'>{img}
""".format(
            extra_class = extra_class,
            id    = chapter.id,
            img   = img)

        if title:
            html += u"""\
        <p class='title title_{level} h{hlevel}'>{title}</p>
""".format(
            hlevel = chapter.level,
            level  = chapter.level,
            title  = escape(title))

        if chapter.sub_title:
            html += u"""\
        <p class='sub_title sub_title_{level} sub_title_h{hlevel} h{hlevel}'>{sub_title}</p>
""".format(
            hlevel = chapter.level,
            level  = chapter.level,
            sub_title  = escape(chapter.sub_title))

        if chapter.author:
            html += u"""\
        <p class='author author_{level}'>{author}</p>
""".format(
            hlevel = chapter.level,
            level  = chapter.level,
            author  = escape(chapter.author))

        html += u"</div></div>\n"

        return html
    # }}}

    # {{{ ---- func chapter_toc_page
    def chapter_toc_page(self, files, filename, chapter):
        title = chapter.title_inner or chapter.title or u"目录"

        # 上面各层的链接
        ancestors = u""
        #while (ancestor = chapter.parent):
        #    if ancestors:
        #        ancestors = " - " + ancestors

        #    ancestors = u"<a href='{link}'>{title}</a>".format(
        #        link = os.path.relpath(ancestor.entry_file, os.path.dirname(filename)),
        #        title = escape(ancestor.title)) + ancestors
        
        html = u"<div class='chapter'><div class='toc_page toc_page'>\n"
        if ancestors:
            html += u"<span class='toc_ancestors'>" + ancestors + "</span>\n"

        if chapter.cover and chapter.cover.height() <= MAX_EMBED_COVER_HEIGHT:
            html += u"<div class='cover'><img alt='{title}' src='{cover}' /></div>".format(
                title = escape(title), 
                cover = os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)))

        html += u"<div class='toc_title'>{title}</div>".format(title=escape(title))

        if chapter.author:
            html += u"<div class='toc_author'>{author}</div>".format(author=escape(chapter.author))

        inline_preamble = False

        if chapter.content and not chapter.content_file:    # 有章节前言，且应嵌入（content_file==u""）
            # 章节的前言少于指定长度，可以整体嵌入目录页
            inline_preamble = True

            html += u"<div class='preamble'>{preamble}</div>".format(
                preamble=to_html(
                    chapter.content,
                    lambda img: os.path.relpath(self.get_img_destpath_(files, img), os.path.dirname(filename))))

        html += u"<ul class='toc_list'>"

        # 如果章节本身也有内容，则生成一个目录项
        if chapter.content and chapter.content_file:
            html += u"<li><a href='{link}'>{title}</a></li>".format(
                    link = os.path.relpath(chapter.content_file, os.path.dirname(filename)),
                    title = u"前言")

        for c in chapter.subchapters:
            html += self.toc_item(files, filename, c)

        html += u"</ul></div></div>"

        return html
    # }}}

    # {{{ ---- func chapter_navbar
    def chapter_navbar(self, filename, chapter, link_to_toc=False):
        links = list()

        prev = chapter.prev
        if not prev:    # 一直往上找
            c = chapter
            while c.parent:
                c = c.parent
                if c.prev:
                    # 找出最底层的章节
                    prev = c.prev
                    while prev.subchapters:
                        prev = prev.subchapters[-1]

                    break

        if prev:
            links.append(u"<a href='{link}'>上一章节</a>".format(
                link = os.path.relpath(
                    prev.toc_file if link_to_toc and prev.toc_file else prev.entry_file,
                    os.path.dirname(filename))))

        if not options.no_toc:
            if chapter.parent and chapter.parent.toc_file:
                links.append(u"<a href='{link}'>上层菜单</a>".format(
                    link = os.path.relpath(chapter.parent.toc_file, os.path.dirname(filename))))

            links.append(u"<a href='{link}'>主菜单</a>".format(
                link = os.path.relpath(TOC_PAGE + HTML_EXT, os.path.dirname(filename))))

        next = chapter.next
        # 如果本层没有下个章节，则跳到父章节的下一个章节
        if not next and chapter.parent and chapter.parent.next:
            next = chapter.parent.next

        if next:
            links.append(u"<a href='{link}'>下一章节</a>".format(
                link = os.path.relpath(
                    next.toc_file if link_to_toc and next.toc_file else next.entry_file,
                    os.path.dirname(filename))))

        # return u"<div class='chapter_navbar'><table><tr><td>{links}</td></tr></table><hr/></div>\n".format(
        #         links = u" | ".join(links))
        return u"<div class='chapter_navbar'><div class='chapter_navbar_inner'><p>{links}</p></div><hr/></div>\n".format(
                links = u" | ".join(links))
    # }}}

    # {{{ ---- func chapter_content_begin
    def chapter_content_begin(self, files, filename, chapter):
        title = chapter.title_inner or chapter.title

        img = u""
        extra_class = u""

        hlevel = chapter.level if chapter.level <= 6 else 6

        # 更大的图片将专门生成封面页
        if chapter.cover and chapter.cover.height() <= MAX_EMBED_COVER_HEIGHT:
            img = u"<div class='cover chapter_cover'><img alt='{title}' src='{cover}' /></div>".format(
                title=escape(title), 
                cover=os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)))

            extra_class = u"chapter_cover_header"

        html = u"""\
        <div class='chapter_content_begin chapter_content_begin_{level} chapter_content_begin_h{hlevel} {extra_class}' id='{id}'>{img}
""".format(
            level = chapter.level,
            hlevel = hlevel,
            extra_class = extra_class,
            id    = chapter.id,
            img   = img)

        if title:
            html += u"""\
        <p class='title chapter_title_{level} h{hlevel}'>{title}</p>
""".format(
            hlevel = hlevel,
            level  = chapter.level,
            title  = escape(title))

        for c in ['sub_title', 'author', 'originated', 'publish_date', 'source']:
            v = getattr(chapter, c)
            if v:
                html += u"<p class='p chapter_{name} chapter_{name}_{level} chapter_{name}_h{level}'>{value}</p>\n""".format(
                    name = c, value = v, level=chapter.level, hlevel=hlevel)

        if chapter.intro:
            html += u"".join([
                u"<div class='chapter_intro chapter_intro_{level}'>\n".format(level=chapter.level),
                to_html(
                    chapter.intro,
                    lambda img: os.path.relpath(self.get_img_destpath_(files, img), os.path.dirname(filename))),
                u"</div>\n"])

        html += u"</div>"

        return html
    # }}}

    # {{{ ---- func chapter_content
    def chapter_content(self, files, filename, chapter):
        result = u"<div class='chapter_content chapter_content_{level}'>\n".format(level=chapter.level)
        return result + to_html(
                chapter.content,
                lambda img: os.path.relpath(self.get_img_destpath_(files, img), os.path.dirname(filename))
            ) + u"</div>";
    # }}}

    # {{{ ---- func chapter_preamble
    def chapter_preamble(self, files, filename, book):
        result = u"<div class='preamble'>\n"
        return result + to_html(
                book.content,
                lambda img: os.path.relpath(self.get_img_destpath_(files, img), os.path.dirname(filename))
            ) + u"</div>";
    # }}}

    # {{{ ---- func chapter_content_end
    def chapter_content_end(self, filename, chapter):
        return u"<div class='chapter_content_end chapter_content_end_{level}'></div>".format(level=chapter.level)
    # }}}

    # {{{ ---- func html_header
    def html_header(self, filename, title, style="", cssfile=""):
        styles = u""
        if cssfile:
            styles += '<link type="text/css" rel="stylesheet" href="{0}" />\n'.format(
                os.path.relpath(cssfile, os.path.dirname(filename)))

        if style:
            styles += "<style type='text/css'>{0}</style>".format(style)

        return u"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
<title>{title}</title>
{styles}
</head>
<body>
""".format(title=escape(title), styles=styles)
    # }}}

    # {{{ ---- func html_footer
    def html_footer(self, filename, book):
        return u"""\
</body>
</html>
"""
    # }}}

    # {{{ ---- func append_image
    def append_image(self, files, img, id=u""):
        if not img:
            return u''

        # 未保存时才保存
        if not files["image"].has_key(img.unique_key()):
            if not id:
                id = u'{prefix}{idx}'.format(prefix=IMAGE_PREFIX, idx=len(files["image"])+1)

            img.set_id(id)

            try:
                img.resize(MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT)       

                files["image"][img.unique_key()] = {
                    "filename": u'{path}{id}{ext}'.format(
                                path=IMAGE_PATH, id=img.id(), ext=img.extension()),
                    "content":  img.content(),
                    "id":       img.id(),
                }
            except:
                files["image"][img.unique_key()] = {
                    "filename": u'{path}{id}{ext}'.format(
                                path=IMAGE_PATH, id=img.id(), ext=img.extension()),
                    "content":  "",
                    "id":       img.id(),
                }
                pass
    # }}} 

    # {{{ ---- func create_preamble_files
    def create_preamble_files(self, files, path, book):
        if not book.content:
            return

        filename = u"{name}{ext}".format(
            name=os.path.join(path, PREAMBLE_PAGE), ext=HTML_EXT)

        if files:
            files["html"].append({
                "filename": filename,
                "title": u"preamble",
                "content":  u"".join((
                    self.html_header(filename, book.title, cssfile=CSS_FILE),
                    self.chapter_preamble(files, filename, book),
                    self.html_footer(filename, book),
                    )).encode("utf-8"),
                "id":       PREAMBLE_PAGE
                })

    # }}}

    # {{{ ---- func create_chapter_images
    def create_chapter_images(self, files, chapter):
        if chapter.cover:
            # 要检查一下封面是否确实可用
            if not chapter.cover.is_valid():
                chapter.cover = None
            else:
                # 加入封面图片
                self.append_image(files, chapter.cover)

        # 生成章节中的图片
        for img in get_images(chapter.intro, chapter.content):
            try:
                self.append_image(files, img)
            except Exception as e:
                if not options.skip_bad_img:  # 允许跳过图片错误
                    raise

        for c in chapter.subchapters:
            self.create_chapter_images(files, c)
    # }}}

    # {{{ ---- func create_chapter_files
    def create_chapter_files(self, files, path, book, chapters):
        """
        如果files为空，则不生成真正的文件，而只是决定各章节的文件名，并写入chapter.entry_file属性中
        """
        first_chapter_page = ""     # chapters中，首个chapter所在的文件名，上层章节可能会合并到这个文件

        for chapter in chapters:
            if chapter.cover and chapter.cover.height() > MAX_EMBED_COVER_HEIGHT:
                # 有大封面，生成单独的封面页
                cover_page_filename = u"{name}{ext}".format(
                    name=os.path.join(path, CHAPTER_COVER_PAGE_ID_FORMAT.format(chapter.id)), ext=HTML_EXT)

                if not chapter.entry_file:
                    chapter.entry_file = cover_page_filename

                if files:
                    files["html"].append({
                        "filename": cover_page_filename,
                        "title": u"{0} cover page".format(chapter.title),
                        "content":  u"".join((
                            self.html_header(cover_page_filename, chapter.title, cssfile=CSS_FILE),
                            self.chapter_cover_page(files, cover_page_filename, chapter),
                            self.html_footer(cover_page_filename, book),
                            )).encode("utf-8"),
                        "id":       CHAPTER_COVER_PAGE_ID_FORMAT.format(chapter.id),
                        })

            if chapter.level == CHAPTER_TOP_LEVEL and chapter.subchapters:
                # 顶层章节，且有子章节，生成标题页。无子章节的顶层章节也不需要生成标题页
                title_page_filename = u"{name}{ext}".format(
                    name=os.path.join(path, CHAPTER_TITLE_PAGE_ID_FORMAT.format(chapter.id)), ext=HTML_EXT)

                if not chapter.entry_file:
                    chapter.entry_file = title_page_filename

                if files:
                    files["html"].append({
                        "filename": title_page_filename,
                        "title": u"{0} title page".format(chapter.title),
                        "content":  u"".join((
                            self.html_header(title_page_filename, chapter.title, cssfile=CSS_FILE),
                            self.chapter_navbar(title_page_filename, chapter),
                            self.chapter_title_page(files, title_page_filename, chapter),
                            self.html_footer(title_page_filename, book),
                            )).encode("utf-8"),
                        "id":       CHAPTER_TITLE_PAGE_ID_FORMAT.format(chapter.id),
                        })

            if not options.no_toc and chapter.subchapters:
                # 有子章节，生成章节目录
                toc_page_filename = u"{name}{ext}".format(
                    name=os.path.join(path, CHAPTER_TOC_PAGE_ID_FORMAT.format(chapter.id)), ext=HTML_EXT)

                chapter.toc_file = toc_page_filename

                if not chapter.entry_file:
                    chapter.entry_file = toc_page_filename

                if files:
#                    # 打印本章节的前、后章节
#                    print u"{0} -> {1} -> {2}".format(
#                        chapter.prev.title if chapter.prev else u"None",
#                        chapter.title,
#                        chapter.next.title if chapter.next else u"None")

                    files["html"].append({
                        "filename": toc_page_filename,
                        "title": u"{0} toc page".format(chapter.title),
                        "content":  u"".join((
                            self.html_header(toc_page_filename, chapter.title, cssfile=CSS_FILE),
                            self.chapter_navbar(toc_page_filename, chapter, link_to_toc=True),
                            self.chapter_toc_page(files, toc_page_filename, chapter),
                            self.html_footer(toc_page_filename, book),
                            )).encode("utf-8"),
                        "id":       CHAPTER_TOC_PAGE_ID_FORMAT.format(chapter.id),
                        })

            # 看看要不要生成一个单独的页面
            if     ((chapter.content and # 有内容
                     (not chapter.toc_file or # 有内容且无目录页
                      content_size(chapter.content) > MAX_INLINE_PREAMBLE_SIZE)) or # 有子章节，但章节内容太长，不适合放到章节目录中
                    (not chapter.content and not chapter.toc_file)): # 章节没有目录也没有正文，必须生成一个文件
                filename = u"{name}{ext}".format(name=os.path.join(path, chapter.id), ext=HTML_EXT)
                chapter.content_file = filename

                if not chapter.entry_file:
                    chapter.entry_file = filename

                if files:
                    files["html"].append({
                        "filename": filename,
                        "title": u"{0}".format(chapter.title),
                        "content":  u"".join((
                            self.html_header(filename, chapter.title, cssfile=CSS_FILE),
                            self.chapter_navbar(filename, chapter),
                            self.chapter_content_begin(files, filename, chapter),
                            self.chapter_content(files, filename, chapter),
                            self.html_footer(filename, book),
                            )).encode("utf-8"),
                        "id":       chapter.id,
                        })

            if chapter.subchapters:
                subpath = os.path.join(path, chapter.id) if options.nestdir else path
                self.create_chapter_files(
                    files,
                    subpath,
                    book,
                    chapter.subchapters)

            if not first_chapter_page:
                first_chapter_page = chapter.entry_file

        return first_chapter_page
    # }}}

    # {{{ ---- func convert
    def convert(self, outputter, book):
        files = {
            "image"   : dict(),     # 图片。Img.unique_key() -> 保存位置的映射
            "html"    : list(),     # HTML文件
            "other"   : list(),     # 其它文件
        }

        files["other"].append({
            "filename":CSS_FILE, 
            "content":self.style.encode("utf-8"),
            "id":CSS_FILE,
        })
        
        # 先处理封面图片，使其出现在最开始的位置
        if book.cover:
            # 要检查一下封面是否确实可用
            if book.cover.is_valid():
                self.append_image(files, book.cover, COVER_IMAGE_NAME)
            else:
                book.cover = None

        self.create_chapter_images(files, book)

        # 先决定各章节中用到的文件名（保存到chapter中）
        self.create_preamble_files(None, "", book)
        self.create_chapter_files(None, "", book, book.subchapters)
        # 再真正生成文件
        self.create_preamble_files(files, "", book)
        self.create_chapter_files(files, "", book, book.subchapters)

        # 记录下正文第一页的位置
        book.text_page = files["html"][0]["filename"]

        filename = TITLE_PAGE + HTML_EXT
        files["html"][0:0] = [{
            "filename": filename,
            "content":  u"".join((
                        self.html_header(filename, book.title, cssfile=CSS_FILE),
                        self.title_page(filename, book),
                        self.html_footer(filename, book),
                        )).encode("utf-8"),
            "id":       TITLE_PAGE,
        }]

        if not options.no_toc:
            filename = TOC_PAGE + HTML_EXT
            book.toc_file = filename
            files["html"][1:0] = [{
                "filename": filename,
                "content":  u"".join((
                            self.html_header(filename, book.title, cssfile=CSS_FILE),
                            self.toc_page(files, filename, book),
                            self.html_footer(filename, book),
                            )).encode("utf-8"),
                "id":       TOC_PAGE,
            }]

        if book.cover:
            if book.cover.height() <= MAX_EMBED_COVER_HEIGHT:
                # 封面图片较小，可与书名页合并，把原来的书名页换掉
                filename = files["html"][0]["filename"]
                files["html"][0]["content"] = u"".join((
                    self.html_header(filename, book.title, cssfile=CSS_FILE),
                    self.title_cover_page(files, filename, book, book.cover),
                    self.html_footer(filename, book),
                )).encode("utf-8")
            else:
                # 插入封面页
                filename = COVER_PAGE + HTML_EXT
                files["html"][0:0] = [{
                    "filename": filename,
                    "content":  u"".join((
                                self.html_header(filename, book.title, cssfile=CSS_FILE),
                                self.cover_page(files, filename, book, book.cover),
                                self.html_footer(filename, book),
                                )).encode("utf-8"),
                    "id":       COVER_PAGE,
                }]

        for f in files["html"] + files["image"].values() + files["other"]:
            outputter.add_file(
                f["filename"], f["content"],
                id=f["id"] if f.has_key("id") else "",
                title=f["title"] if f.has_key("title") else "")
    # }}}
#   }}}

class EpubConverter(Converter): # {{{
    def __init__(self, style):
        super(EpubConverter, self).__init__()
        self.style = style

    def get_navpoint_depth(self, parent):
        depth = 0
        for elem in parent.childNodes:
            if elem.nodeName == 'navPoint':
                depth = max((depth, self.get_navpoint_depth(elem) + 1))

        return depth

    def add_playorder_to_navpoint(self, parent, playOrderMap=dict(), playOrder=1):
        for elem in parent.childNodes:
            if elem.nodeName == 'navPoint':
                # 取出src
                #src = splittag(splitquery(elem.getElementsByTagName(u"content")[0].getAttribute(u"src"))[0])[0]
                src = elem.getElementsByTagName(u"content")[0].getAttribute(u"src")

                # 如果该src已经出现过，则沿用原来的playOrder
                if playOrderMap.has_key(src):
                    elem.setAttribute("playOrder", unicode(playOrderMap[src]))
                else:
                    playOrderMap[src] = playOrder
                    elem.setAttribute("playOrder", unicode(playOrder))
                    playOrder += 1

                # 处理elem的子节点
                playOrder = self.add_playorder_to_navpoint(elem, playOrderMap, playOrder)

        return playOrder

    def create_navpoint(self, xml, parent, chapter):
        def new_navpoint_elem(id, title, src):
            navPointElem = xml.createElement("navPoint")
            navPointElem.setAttribute("id", unicode(id))

            navLabelElem = xml.createElement("navLabel")
            navPointElem.appendChild(navLabelElem)
            textElem = xml.createElement("text")
            navLabelElem.appendChild(textElem)
            textElem.appendChild(xml.createTextNode(unicode(title)))
            contentElem = xml.createElement("content")
            navPointElem.appendChild(contentElem)
            contentElem.setAttribute("src", unicode(src))

            return navPointElem

        def rearrange_toc_tree(elems, maxSubToc):
            originIdx = 0
            while len(elems) > maxSubToc:
                # 如果所有子节点都已经是二级节点，那么就从第0项重新开始，再加入一层
                if (originIdx >= len(elems)):
                    originIdx = 0

                firstIdx = originIdx
                lastIdx  = originIdx + maxSubToc - 1 if originIdx + maxSubToc <= len(elems) else len(elems) - 1
                firstLabel = elems[firstIdx]["firstLabel"] if elems[firstIdx].has_key("firstLabel") else elems[firstIdx]["title"]
                lastLabel  = elems[lastIdx]["lastLabel"] if elems[lastIdx].has_key("lastLabel") else elems[lastIdx]["title"]
                src = elems[firstIdx]["src"]

                newElem = {
                    "id": elems[firstIdx]["id"] + "m",      # 不断加入'm'作为后缀，生成新的ID
                    "title": u"{firstLabel} .. {lastLabel}".format(firstLabel=firstLabel, lastLabel=lastLabel),
                    "src": src,
                    "firstLabel": firstLabel,
                    "lastLabel": lastLabel,
                    "children": list(),
                }

                for i in xrange(firstIdx, lastIdx + 1):
                    newElem["children"].append(elems.pop(originIdx))

                elems[originIdx:originIdx] = (newElem,)
                originIdx += 1

        def generate_navpoint(chapter, create_toc=False):
            elems = list()

            if create_toc and chapter.toc_file:
                elems.append({
                    "id": TOC_PAGE,
                    "title": u"目录",
                    "src": os.path.join(CONTENT_DIR, chapter.toc_file),
                })

            for subchapter in chapter.subchapters:
                # 有title才生成目录项
                if subchapter.title:
                    src = os.path.join(CONTENT_DIR, subchapter.entry_file)

                    elems.append({
                        "id": subchapter.id,
                        "title": subchapter.title,
                        "src": src,
                        "children": generate_navpoint(subchapter),
                    })

            if not options.plain_toc:
                if options.rearrange_toc:
                    # 调整TOC，使每层的TOC不超过指定的数量
                    rearrange_toc_tree(elems, DEFAULT_MAX_EPUB_SUB_TOC)

            return elems

        def create_navpoints(elems, parent, indent):
            for elem in elems:
                newNavPointElem = new_navpoint_elem(
                    elem["id"], 
                    TOC_INDENT_CHAR * options.toc_indent * indent + elem["title"],
                    elem["src"])

                parent.appendChild(newNavPointElem)
                if elem.has_key("children") and elem["children"]:
                    create_navpoints(elem["children"], newNavPointElem, indent + 1)

        elems = generate_navpoint(chapter, create_toc=True)
        create_navpoints(elems, parent, 0)

    def generate_ncx(self, book, identifier):
        xml = minidom.Document()

        # /ncx
        ncxElem = xml.createElement("ncx")
        xml.appendChild(ncxElem)
        ncxElem.setAttribute("xmlns", "http://www.daisy.org/z3986/2005/ncx/")
        ncxElem.setAttribute("version", "2005-1")

        # /ncx/head
        headElem = xml.createElement("head")
        ncxElem.appendChild(headElem)

        # /ncx/head/meta[name=uid]
        uidElem = xml.createElement("meta")
        headElem.appendChild(uidElem)
        uidElem.setAttribute("name", "dtb:uid")
        uidElem.setAttribute("content", unicode(identifier))

        # /ncx/head/meta[name=generator]
        generatorElem = xml.createElement("meta")
        headElem.appendChild(generatorElem)
        generatorElem.setAttribute("name", "dtb:generator")
        generatorElem.setAttribute("content", u'{prog} {ver}'.format(prog=PROGNAME, ver=VERSION))

        # /ncx/head/meta[name=totalPageCount] pageList中pageTargets的数量
        totalPageCountElem = xml.createElement("meta")
        headElem.appendChild(totalPageCountElem)
        totalPageCountElem.setAttribute("name", "dtb:totalPageCount")
        totalPageCountElem.setAttribute("content", u'0')

        # /ncx/head/meta[name=maxPageNumber] pageTargets中value的最大值
        maxPageNumberElem = xml.createElement("meta")
        headElem.appendChild(maxPageNumberElem)
        maxPageNumberElem.setAttribute("name", "dtb:maxPageNumber")
        maxPageNumberElem.setAttribute("content", u'0')

        # /ncx/docTitle
        titleElem = xml.createElement("docTitle")
        ncxElem.appendChild(titleElem)

        # /ncx/docTitle/text
        textElem = xml.createElement("text")
        titleElem.appendChild(textElem)
        textElem.appendChild(xml.createTextNode(unicode(book.meta_title if book.meta_title else book.title)))

        if book.author:
            # /ncx/docAuthor
            authorElem = xml.createElement("docAuthor")
            ncxElem.appendChild(authorElem)

            # /ncx/docAuthor/text
            textElem = xml.createElement("text")
            authorElem.appendChild(textElem)
            textElem.appendChild(xml.createTextNode(unicode(book.author)))

        # /ncx/navMap
        navMapElem = xml.createElement("navMap")
        ncxElem.appendChild(navMapElem)

        # 生成各navPoint
        self.create_navpoint(xml, navMapElem, book)
        self.add_playorder_to_navpoint(navMapElem)

        # /ncx/head/meta[name=depth]
        depthElem = xml.createElement("meta")
        headElem.appendChild(depthElem)
        depthElem.setAttribute("name", "dtb:depth")
        depthElem.setAttribute("content", unicode(self.get_navpoint_depth(navMapElem)))

        return pretty_xml(xml)

    def generate_opf(self, book, identifier, filelist):
        def get_media_type(filename):
            for m in MEDIA_TYPES:
                if m["pattern"].match(filename):
                    return m["media-type"]

            return "unknown"

        xml = minidom.Document()

        # /package
        packageElem = xml.createElement("package")
        xml.appendChild(packageElem)
        packageElem.setAttribute("xmlns",   "http://www.idpf.org/2007/opf")
        packageElem.setAttribute("version", "2.0")
        packageElem.setAttribute("unique-identifier", UID_ELEM_ID)

        # /package/metadata
        metadataElem = xml.createElement("metadata")
        packageElem.appendChild(metadataElem)
        metadataElem.setAttribute("xmlns:dc",  "http://purl.org/dc/elements/1.1/")
        metadataElem.setAttribute("xmlns:opf", "http://www.idpf.org/2007/opf")

        # /package/metadata/title
        titleElem = xml.createElement("dc:title")
        metadataElem.appendChild(titleElem)
        titleElem.appendChild(xml.createTextNode(unicode(book.meta_title if book.meta_title else book.title)))

        # /package/metadata/creator
        authorElem = xml.createElement("dc:creator")
        metadataElem.appendChild(authorElem)
        authorElem.setAttribute("opf:role", "aut")
        authorElem.appendChild(xml.createTextNode(unicode(book.author)))

        # /package/metadata/subject
        if book.category:
            if isinstance(book.category, basestring):
                subjectElem = xml.createElement("dc:subject")
                metadataElem.appendChild(subjectElem)
                subjectElem.appendChild(xml.createTextNode(unicode(book.category)))
            else:
                for cat in book.category:
                    subjectElem = xml.createElement("dc:subject")
                    metadataElem.appendChild(subjectElem)
                    subjectElem.appendChild(xml.createTextNode(unicode(cat)))

        # /package/metadata/description
        if book.intro:
            descriptionElem = xml.createElement("dc:description")
            metadataElem.appendChild(descriptionElem)
            descriptionElem.appendChild(xml.createTextNode(unicode(to_asciidoc(book.intro))))

        # /package/metadata/identifier
        identifierElem = xml.createElement("dc:identifier")
        identifierElem.setAttribute("opf:scheme", "uuid")
        identifierElem.setAttribute("id", UID_ELEM_ID)
        metadataElem.appendChild(identifierElem)
        identifierElem.appendChild(xml.createTextNode(unicode(identifier)))

        # /package/metadata/identifier for ISBN
        if book.isbn:
            identifierElem = xml.createElement("dc:identifier")
            identifierElem.setAttribute("opf:scheme", "ISBN")
            metadataElem.appendChild(identifierElem)
            identifierElem.appendChild(xml.createTextNode(unicode(book.isbn)))

        # /package/metadata/language
        languageElem = xml.createElement("dc:language")
        metadataElem.appendChild(languageElem)
        languageElem.appendChild(xml.createTextNode("zh-CN"))

        # /package/metadata/contributor
        contributorElem = xml.createElement("dc:contributor")
        metadataElem.appendChild(contributorElem)
        contributorElem.setAttribute("opf:role", "bkp")
        contributorElem.appendChild(xml.createTextNode(u"{prog} v{ver}".format(prog=PROGNAME, ver=VERSION)))

        # /package/metadata/publish_date
        if book.publish_date:
            dateElem = xml.createElement("dc:date")
            dateElem.setAttribute("opf:event", "publication")
            metadataElem.appendChild(dateElem)
            dateElem.appendChild(xml.createTextNode(unicode(book.publish_date)))

        # /package/metadata/modification_date
        dateElem = xml.createElement("dc:date")
        dateElem.setAttribute("opf:event", "modification")
        metadataElem.appendChild(dateElem)
        dateElem.appendChild(xml.createTextNode(time.strftime('%Y-%m-%d')))

        # /package/metadata/meta[cover]
        if book.cover:
            coverElem = xml.createElement("meta")
            coverElem.setAttribute("name", "cover")
            coverElem.setAttribute("content", unicode(book.cover.id()))
            metadataElem.appendChild(coverElem)

        # /package/metadata/meta[calibre:series]
        if book.series:
            seriesElem = xml.createElement("meta")
            seriesElem.setAttribute("name", "calibre:series")
            seriesElem.setAttribute("content", unicode(book.series))
            metadataElem.appendChild(seriesElem)

        # /package/manifest
        manifestElem = xml.createElement("manifest")
        packageElem.appendChild(manifestElem)

        tocElem = xml.createElement("item")
        manifestElem.appendChild(tocElem)
        tocElem.setAttribute("id",         NCX_ID)
        tocElem.setAttribute("href",       NCX_FILE)
        tocElem.setAttribute("media-type", NCX_TYPE)

        for file in filelist:
            path = file["path"]
            idxElem = xml.createElement("item")
            idxElem.setAttribute("id",         unicode(file["id"] if file.has_key("id") and file["id"] else path))
            idxElem.setAttribute("href",       unicode(os.path.join(CONTENT_DIR, path)))
            idxElem.setAttribute("media-type", unicode(get_media_type(path)))
            manifestElem.appendChild(idxElem)

        # /package/spine
        spineElem = xml.createElement("spine")
        packageElem.appendChild(spineElem)
        spineElem.setAttribute("toc", NCX_ID)

        coverPage = u"" # 封面页

        for file in filelist:
            if re.match(u".*\.x?html?", file["path"]):
                itemrefElem = xml.createElement("itemref")
                itemrefElem.setAttribute("idref", unicode(file["id"]))

                # 第一页是封面页
                if not coverPage:
                    coverPage = file["path"]
                    itemrefElem.setAttribute("linear", "no")
                    
                spineElem.appendChild(itemrefElem)

        guideElem = xml.createElement("guide")
        packageElem.appendChild(guideElem)

        if coverPage:
            coverReferenceElem = xml.createElement("reference")
            coverReferenceElem.setAttribute("href", os.path.join(CONTENT_DIR, coverPage))
            coverReferenceElem.setAttribute("type", "cover")
            coverReferenceElem.setAttribute("title", u"Cover")
            guideElem.appendChild(coverReferenceElem)

        tocReferenceElem = xml.createElement("reference")
        tocReferenceElem.setAttribute("href", os.path.join(CONTENT_DIR, book.toc_file))
        tocReferenceElem.setAttribute("type", "toc")
        tocReferenceElem.setAttribute("title", u"目录")
        guideElem.appendChild(tocReferenceElem)

        titleReferenceElem = xml.createElement("reference")
        titleReferenceElem.setAttribute("href", os.path.join(CONTENT_DIR, TITLE_PAGE + HTML_EXT))
        titleReferenceElem.setAttribute("type", "title")
        titleReferenceElem.setAttribute("title", u"Title")
        guideElem.appendChild(titleReferenceElem)

        textReferenceElem = xml.createElement("reference")
        textReferenceElem.setAttribute("href", unicode(os.path.join(CONTENT_DIR, book.text_page)))
        textReferenceElem.setAttribute("type", "text")
        textReferenceElem.setAttribute("title", u"正文")
        guideElem.appendChild(textReferenceElem)

        return pretty_xml(xml)

    def build_epub(self, outputter, opf, ncx, filelist):
        """ 根据opf、ncx及filelist中的文件内容，构造epub文件 """

        CONTAINER='''\
<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
   <rootfiles>
      <rootfile full-path="{0}" media-type="application/oebps-package+xml"/>
   </rootfiles>
</container>'''.format(OPF_FILE)

        logging.info(u"Constructing EPUB file...")
        logging.debug(u"  Creating empty EPUB file...")

        logging.info(u"  Adding structure files...")
            
        outputter.add_file('mimetype', 'application/epub+zip', compression=zipfile.ZIP_STORED)
        outputter.add_file('META-INF/container.xml', CONTAINER)
        outputter.add_file(OPF_FILE, opf)
        outputter.add_file(NCX_FILE, ncx)

        logging.info(u"  Adding content files...")

        count = 0
        for file in filelist:
            logging.debug(u"    Adding {0}{1}".format(
                file["path"], 
                u" : {0}".format(file["title"]) if file.has_key("title") and file["title"] else ""))
            outputter.add_file(os.path.join(CONTENT_DIR, file["path"]), file["content"])
            count += 1

        logging.info(u"    Total {0} files added".format(count))

    def convert(self, outputter, book):
        identifier = unicode(uuid.uuid4())

        logging.info(u"Generating related files...")

        logging.info(u"  Generating content files ...")

        memOutputter = MemOutputter()
        htmlconverter = HtmlConverter(self.style)
        htmlconverter.convert(memOutputter, book)

        filecount = dict()
        othercount = 0
        for file in memOutputter.files:
            for media_type in MEDIA_TYPES:
                if media_type["pattern"].match(file["path"]):
                    if filecount.has_key(media_type["type"]):
                        filecount[media_type["type"]] += 1
                    else:
                        filecount[media_type["type"]] = 1

                    break
            else:
                othercount += 1

        for type in filecount:
            logging.info(u"    {count:4} {type} files".format(type=type, count=filecount[type]))

        if othercount > 0:
            logging.info(u"    {count:4} other files".format(count=othercount))

        logging.info(u"    Total {0} files".format(len(memOutputter.files)))

        logging.info(u"  Generating ncx file ...")
        ncx = self.generate_ncx(book, identifier)

        logging.info(u"  Generating opf file ...")
        opf = self.generate_opf(book, identifier, memOutputter.files)

        self.build_epub(outputter, opf, ncx, memOutputter.files)

        logging.info(u"  EPUB generated.")
# }}}

class TxtConverter(object): # {{{
    def __init__(self, filename):
        super(TxtConverter, self).__init__()
        self.filename = filename

    def convert(self, outputter, book):
        def convert_chapter(chapter):
            text = u"\n"
            attrs = list()

            if chapter.author:
                attrs.append(u"author=\"{author}\"".format(author=chapter.author))

            if chapter.cover:
                attrs.append(u"cover=\"{cover}\"".format(
                    cover=u'{id}{ext}'.format(id=chapter.cover.id(), ext=chapter.cover.extension())))

            if attrs:
                text += u"[" + u",".join(attrs) + u"]\n"

            text += u"=" + u"=" * (chapter.level - CHAPTER_TOP_LEVEL) + u" "
            text += chapter.title
            text += u"\n\n"

            if chapter.intro:
                text += to_asciidoc(chapter.intro)
                text += u"\n"

            text += to_asciidoc(chapter.content)

            for c in chapter.subchapters:
                text += convert_chapter(c)

            return text

        # 先处理所有图片，为图片加上ID
        saved_files = dict()
        for img in get_images(book):
            if not saved_files.has_key(img.unique_key()):
                img.set_id(u'{prefix}{idx}'.format(prefix=IMAGE_PREFIX, idx=len(saved_files)+1))
                img.resize(MAX_IMAGE_WIDTH, MAX_IMAGE_HEIGHT)       
                saved_files[img.unique_key()] = True

                outputter.add_file(
                    u'{id}{ext}'.format(id=img.id(), ext=img.extension()),
                    img.content(),
                    id=img.id())

        text = u"= " + book.title + u"\n"
        text += u":Author: " + book.author + u"\n" if book.author else u""
        text += u":SubTitle: " + book.sub_title + u"\n" if book.sub_title else u""
        text += u":Series: " + book.series + u"\n" if book.series else u""
        text += u":Category: " + book.category + u"\n" if book.category else u""
        text += u":Publisher: " + book.publisher + u"\n" if book.publisher else u""
        text += u":ISBN: " + book.isbn + u"\n" if book.isbn else u""
        text += u":PublishDate: " + book.publish_date + u"\n" if book.publish_date else u""
        text += u":PublishVer: " + book.publish_ver + u"\n" if book.publish_ver else u""

        if book.intro:
            text += u":Description: "
            # Description只允许一段，因此把多段合并到一起
            text += re.sub(r"\n(?:\s|\n)+", "\n", to_asciidoc(book.intro))
            text += u"\n"

        text += u"\n"

        for chapter in book.subchapters:
            text += convert_chapter(chapter)

        outputter.add_file(self.filename, text.encode(options.encoding))
#   }}}

# }}}

# {{{ Outputters
class Outputter(object): # {{{
    def __init__(self):
        self.is_closed = False

    def add_file(self, path, content, **properties):
        raise NotImplementedError()

    def close(self):
        self.is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

#   }}}

class MemOutputter(Outputter): # {{{
    def __init__(self):
        super(MemOutputter, self).__init__()
        self.files = list()

    def add_file(self, path, content, **properties):
        file = {
            "path"       : path,
            "content"    : content,
        }

        for k in properties.keys():
            file[k] = properties[k]

        self.files.append(file)
#   }}}

class FileSysOutputter(Outputter): # {{{
    def add_file(self, path, content, **properties):
        with open(path, 'w+b') as f:
            f.write(content)
#   }}}

class ZipOutputter(Outputter): # {{{
    def __init__(self, outputter, filename):
        super(ZipOutputter, self).__init__()

        self.outputter = outputter
        self.filename = filename
        self.exists_files = dict()  # 用于记录已增加到zip包中的文件
        self.zipfile = StringIO()
        self.zip = zipfile.ZipFile(self.zipfile, 'w', zipfile.ZIP_DEFLATED)

    def add_file(self, path, content, **properties):
        permissions = properties["permissions"] if properties.has_key("permissions") else 0644
        compression = properties["compression"] if properties.has_key("compression") else zipfile.ZIP_DEFLATED

        dirname = os.path.dirname(path)
        # 创建上层目录
        if dirname and not self.exists_files.has_key(dirname):
            self.add_file(dirname, '', permissions=0700)

        zipname = path
        if permissions & 0700 == 0700:
            zipname = os.path.join(path, "")

        info = zipfile.ZipInfo(zipname)
        info.compress_type = compression
        info.date_time = time.localtime(time.time())[:6]
        info.external_attr = permissions << 16L
        self.zip.writestr(info, content)

        self.exists_files[path] = True

    def close(self):
        self.zip.close()
        # 把内容写到下一级Outputter中
        self.outputter.add_file(self.filename, self.zipfile.getvalue())
        self.zipfile.close()

        super(ZipOutputter, self).close()

#   }}}
# }}}

# {{{ convert_book
def convert_book(path, output=u""):
    # {{{ -- func chapters_normalize
    def chapters_normalize(chapter, level, prefix):
        if hasattr(chapter, "id"):
            chapter.id = prefix

        if not chapter.cover:
            c = chapter
            while c:
                author = c.author
                if author:
                    break

                c = c.parent

            chapter.cover = lookup_cover(chapter.title, author, exactly_match=True)

        if chapter.subchapters:
            # 如果父章节没有内容，只有一个子章节，且与子章节名称一样，则可以合并
            if len(chapter.subchapters) == 1 and (
                        (isinstance(chapter, Chapter) and not chapter.content) or                   # 本章节没有内容
                        (not isinstance(chapter, Chapter) and not chapter.subchapters[0].content)   # 子章节没有内容
                    ) and chapter.title == chapter.subchapters[0].title:
                # 把子章节的内容合并到父章节中。如果父章节已经有相应的项目，则使用父章节中的内容
                chapter.title_inner  = chapter.subchapters[0].title_inner  if not chapter.title_inner  else chapter.title_inner
                chapter.author       = chapter.subchapters[0].author       if not chapter.author       else chapter.author
                chapter.cover        = chapter.subchapters[0].cover        if not chapter.cover        else chapter.cover
                chapter.intro        = chapter.subchapters[0].intro        if not chapter.intro        else chapter.intro
                chapter.originated   = chapter.subchapters[0].originated   if not chapter.originated   else chapter.originated
                chapter.publish_date = chapter.subchapters[0].publish_date if not chapter.publish_date else chapter.publish_date
                chapter.source       = chapter.subchapters[0].source       if not chapter.source       else chapter.source
                chapter.content      = chapter.subchapters[0].content      if not chapter.content      else chapter.content
                chapter.subchapters  = chapter.subchapters[0].subchapters

        if isinstance(chapter.intro, basestring):
            chapter.intro = [ chapter.intro ]

        # 建立章节间的导航关系
        #
        for i in xrange(0, len(chapter.subchapters)):
            c = chapter.subchapters[i]

            # 建立章节间的导航关系
            if isinstance(chapter, Chapter):
                c.parent = chapter

            c.prev = chapter.subchapters[i - 1] if i > 0 else None

            if i < len(chapter.subchapters) - 1:    # 同级还有下一章节
                c.next = chapter.subchapters[i + 1]
            elif hasattr(chapter, "next"):          # 指向父章节的下一章节
                c.next = chapter.next
            else:
                c.next = None
            
            # 检查本章节是否是父章节的简介
            if not chapter.intro:
                for re_intro in RE_INTRO_TITLES:
                    if re_intro.match(c.title):
                        # 章节标题符合内容简介标题，作为内容简介
                        logging.debug(u"{indent}    Found Intro '{intro_title}' for {title}".format(
                            indent="  "*(level - 1),
                            intro_title=c.title,
                            title=chapter.title if chapter.title else u"the book"))
                                
                        chapter.intro = c.content
                        break

            chapters_normalize(c, level + 1, prefix + "_" + str(i + 1))
    # }}}

    # {{{ -- get_suitable_inputter
    def get_suitable_inputter(path):
        inputter = None

        if SHORT_CUTS.has_key(path):
            path = SHORT_CUTS[path]

        if re.match(r"https?://", path):
            inputter = UrlInputter(path)
        elif os.path.isfile(path) and os.path.splitext(path)[1].lower() == ".chm":
            try:
                f=CHMFile()

                try:
                    inputter = ChmInputter(path)
                except:
                    pass
            except NameError:
                logging.error(u"chmlib not found")
        elif os.path.exists(path):
            inputter = FileSysInputter(path)
        else:
            logging.error(u"File not found '{0}'".format(path))
            raise NotParseableError(u"'{0}' is not existed!".format(path))

        if not inputter:
            logging.error(u"Can't parse '{0}".format(path))
            raise NotParseableError(u"Can't find suitable Inputter for path '{0}'!".format(path))

        return inputter
    # }}}

    # {{{ -- parse_book
    def parse_book(inputter):
        book = None

        logging.info(u"Parsing book '{0}'...".format(path))

        cover = None
        if options.cover:
            if os.path.exists(options.cover):
                cover = InputterImg(options.cover)
            else:
                logging.error(u"  Error: Cover file '{0}' not found".format(options.cover))
                return Book()

        # 先猜测一下标题和作者
        fileinfo = parse_filename(path, options.title, options.author)

        try:
            book = Parser.parse_book(inputter, CHAPTER_TOP_LEVEL, title=fileinfo["title"], author=fileinfo["author"], cover=cover)
        except NotParseableError as e:
            logging.error(u"  Error: Don't know how to parse '{0}'".format(path))
            logging.error(e.value)
            raise

        reset_level(book, CHAPTER_TOP_LEVEL)
        chapters_normalize(book, CHAPTER_TOP_LEVEL, u"chapter")

        # 仅当保留了当初的标题时，才使用从书名中猜测的信息
        if not book.title or book.title == fileinfo["title"]:
            book.meta_title  = fileinfo["title"] + fileinfo["extra_info"]
            if not book.sub_title:
                book.sub_title = fileinfo["extra_info"]

        if not book.author:
            book.author = fileinfo["author"]

        book.category = options.category if options.category else book.category
        if not book.category and fileinfo["category"]:
            book.category = fileinfo["category"]

        book.cover = cover if cover else book.cover

        # 非离线模式，有标题，无作者或无分类时到网上搜索作者及分类信息
        if book.title and (not book.author or not book.category or not book.cover):
            bookinfo = {
                "title"     : book.title,
                "sub_title" : book.sub_title,
                "author"    : book.author,
                "l1cat"     : book.category,
                "cover"     : book.cover,
            }
            complete_book_info(bookinfo)

            book.sub_title = bookinfo["sub_title"]
            book.author = bookinfo["author"]
            book.category = bookinfo["l1cat"]
            book.cover = bookinfo["cover"]

        if not book.category:
            book.category = DEFAULT_CATEGORY

        return book
    # }}}

    # {{{ -- func print_book_info
    def print_book_info(book):
        logging.info(u"Book Info:")
        logging.info(u"  Book Title:  '{title}'".format(title=book.title))
        logging.info(u"  Book SubTitle:  '{title}'".format(title=book.sub_title))
        logging.info(u"  Book Author: '{author}'".format(author=book.author))
        logging.info(u"  Book Category: '{category}'".format(category=book.category))

        if book.cover:
            logging.info(u"  Cover: Yes")
        else:
            logging.info(u"  Cover: None")
    # }}}

    # {{{ -- Function Body
    if options.plain_toc:
        logging.info(u"Using plain TOC")

    global book_dir

    if os.path.isfile(path):
        book_dir = os.path.abspath(os.path.dirname(path))
    else:
        book_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.join(path, ""))))

    inputter = get_suitable_inputter(path)
    with inputter:
        book = parse_book(inputter)

        print_book_info(book)

        # {{{ Convert book
        if output: 
            if not os.path.exists(output) or not os.path.isfile(output):
                bookfilename = os.path.join(output, book_file_name(
                    book.meta_title if book.meta_title else book.title,
                    book.author,
                    u".epub"))
            else:
                bookfilename = output
        else:
            bookfilename = book_file_name(
                book.meta_title if book.meta_title else book.title,
                book.author,
                u".epub")

        if os.path.splitext(bookfilename)[1].lower() == u".txt":
            with FileSysOutputter() as outputter:
                converter = TxtConverter(bookfilename)
                converter.convert(outputter, book)
        elif os.path.splitext(bookfilename)[1].lower() == u".asciidoc":
            with FileSysOutputter() as outputter:
                converter = TxtConverter(bookfilename)
                converter.convert(outputter, book)
        else:
            style = u""
            for style_file in STYLE_FILES:
                with open(os.path.join(SCRIPT_PATH, style_file)) as f:
                    style += f.read().decode(STYLE_FILE_ENCODING)
                    style += "\n"

            converter = EpubConverter(style)
            with ZipOutputter(FileSysOutputter(), bookfilename) as outputter:
                converter.convert(outputter, book)

        logging.info(u"Saved to {0}".format(bookfilename))
        # }}}

    return 0
    # }}}
# }}}

# {{{ main
if __name__ == "__main__":
    sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
    sys.stderr = codecs.getwriter(locale.getpreferredencoding())(sys.stderr)

    optparser = optparse.OptionParser(
        usage="%prog [options] <chm> [<output_filename>]", 
        description="""\
    Convert chm books into epub format.""",
        version=VERSION)

    optparser.add_option('-t', '--title',   action="store", type="string", dest="title", help="Book title. If omit, guess from filename")
    optparser.add_option('-a', '--author',  action="store", type="string", dest="author", help="Book author. If omit, guess from filename")
    optparser.add_option('-C', '--category',  action="store", type="string", dest="category", help="Book category. If omit, discover from web search")
    optparser.add_option('-e', '--encoding',  action="store", type="string", dest="encoding", default=locale.getpreferredencoding(), help="Default encoding for Txt output. Defaults to current locale (%default)")
    optparser.add_option('-P', '--parse-filename',    action="store_true", dest="parse_filename", default=False, help="Parse title/author from filename, don't convert.")
    optparser.add_option('-O', '--offline', action="store_true", dest="offline", default=False, help="Don't lookup author/category from web search.")
    optparser.add_option('-c', '--cover',   action="store", type="string", dest="cover", default="", help="Book cover image.")
    optparser.add_option('-k', '--keep',    action="store_true", dest="keep", default=False, help="Keep intermediate files.")
    optparser.add_option('--no-toc',    action="store_true", dest="no_toc", default=False, help="Don't generate inline TOC")
    optparser.add_option('-r', '--rearrange-toc',    action="store_true", dest="rearrange_toc", default=False, help="Rearrange TOC to avoid too much items in a level.")
    optparser.add_option('-p', '--plain-toc',    action="store_true", dest="plain_toc", default=False, help="Using only one level TOC.")
    optparser.add_option('-i', '--toc-indent',   action="store", type="int", dest="toc_indent", default=2, help="Indent count in TOC.")
    optparser.add_option('-v', '--verbose', action="store_true", dest="verbose", default=False, help="Be moderatery verbose")
    optparser.add_option('-s', '--silent',  action="store_true", dest="silent", default=False, help="Only show warning and errors")
    optparser.add_option('-n', '--nest-directory',  action="store_true", dest="nestdir", default=False, help="Create one sub directory for every chapte to avoid too much files in a single directory.")
    optparser.add_option('-b', '--skip-bad-img',  action="store_true", dest="skip_bad_img", default=False, help="Ignore and skip bad or missing images")

    (options, args) = optparser.parse_args()

    for k in vars(options):
        if isinstance(getattr(options, k), basestring):
            setattr(options, k, unicode(getattr(options, k), locale.getpreferredencoding()).strip())

    args = [unicode(arg, locale.getpreferredencoding()) for arg in args]

    # Test
    #optparser = InfzmParser()
    #chapter = optparser.parse_chapter(args[0], UrlInputter(u"http://www.infzm.com/enews/infzm"))
    #print u"\n".join(chapter.content)
    #sys.exit(0)
    # end Test

    if len(args) < 1:
        sys.stderr.write("Error: chm filename is missing\n")
        optparser.print_help(sys.stderr)
        sys.exit(2)

    log_format = u"%(asctime)s %(lineno)d %(levelname)s %(message)s"
    if options.silent:
        logging.basicConfig(format=log_format, level=logging.WARNING)
    elif options.verbose:
        logging.basicConfig(format=log_format, level=logging.DEBUG)
    else:
        logging.basicConfig(format=log_format, level=logging.INFO)

    filename = args[0]
    
    output = u""
    if len(args) > 1:
        output = args[1]

    if options.parse_filename:
        l1cat = options.category
        l2cat = ""
        fileinfo = parse_filename(filename, options.title, options.author)

        title  = fileinfo["title"]
        author = fileinfo["author"]

        bookinfo = {
            "title"  : title,
            "author" : author,
            "l1cat"  : l1cat,
            "l2cat"  : l2cat
        }

        options.offline = True  # online书本信息已失效

        # 有标题，无作者或无分类时补全作者及分类信息
        if title and (not author or not l1cat):
            complete_book_info(bookinfo)

        print u"{l1cat}\t{l2cat}\t{title}\t{author}".format(
            title=bookinfo["title"], author=bookinfo["author"], l1cat=bookinfo["l1cat"], l2cat=bookinfo["l2cat"])

#        if bookinfo["cover"]:
#            if bookinfo["cover"].is_valid():
#                print u"Cover is valid"
#            else:
#                print u"Cover is invalid"
#        else:
#            print u"No cover"

        sys.exit(0)
    else:
        sys.exit(convert_book(filename, output))
# }}}
    
