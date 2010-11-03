#!/usr/bin/python2
# vim: set fileencoding=utf-8 foldmethod=marker:
# Author: thawk(thawk009@gmail.com)

# {{{ Imports
import codecs
import cookielib
import htmlentitydefs
import inspect
import json
import locale
import logging
import optparse
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import uuid
import zipfile
import Image
from cStringIO import StringIO

from cgi import escape
from time import localtime, time
from urllib import urlencode, quote, basejoin, splittag, splitquery
from urllib2 import build_opener, urlopen, Request, HTTPCookieProcessor
from xml.dom import minidom

try:
    # 大部分情况下都不需要使用chardet，因此没有也行，真正用的时候才报错
    import chardet
except:
    pass

try:
    from pychm import chmlib
except:
    try:
        from chm import chmlib
    except:
        pass
# }}}

VERSION=u"20101102"

# {{{ Contants
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
#COVER_IMAGE_NAME = u"cover"
# 非封面图片的文件名前缀
IMAGE_PREFIX     = u"image_"
IMAGE_PATH       = u"img/"

DEFAULT_MAX_EPUB_SUB_TOC = 10
MAX_EPUB_SUB_TOCS = {       # max epub sub tocs for each level. If not in this list, use DEFAULT_MAX_EPUB_SUB_TOC
    1 : 20,                 # 根目录允许最多20项
}

# 各额外部分的文件名
COVER_PAGE = u"cover"   # 封面
TITLE_PAGE = u"title"   # 书名页

# 存放html页面的目录名称
CONTENT_DIR = u"content"

# 不大于该大小就使用嵌入式封面（上半显示图片，下半显示文字），否则将图片拉伸到全页面
MAX_EMBED_COVER_HEIGHT = 300

# 简介章节的缺省标题
BOOK_INTRO_TITLE = u"内容简介"
CHAPTER_INTRO_TITLE = u"内容简介"

HTTP_RETRY = 2

MEDIA_TYPES = (
    { "type":"html",  "media-type":"application/xhtml+xml",  "pattern":re.compile(r".*\.html?", re.IGNORECASE) },
    { "type":"html",  "media-type":"application/xhtml+xml",  "pattern":re.compile(r".*\.xhtml?", re.IGNORECASE) },
    { "type":"css",   "media-type":"text/css",               "pattern":re.compile(r".*\.css",   re.IGNORECASE) },
    { "type":"image", "media-type":"image/jpeg",             "pattern":re.compile(r".*\.jpe?g", re.IGNORECASE) },
    { "type":"image", "media-type":"image/png",              "pattern":re.compile(r".*\.png",   re.IGNORECASE) },
    { "type":"image", "media-type":"image/gif",              "pattern":re.compile(r".*\.gif",   re.IGNORECASE) },
)

CATEGORY_NEWS_PAPER = u'报刊'
# }}}

# {{{ Globals
options = dict()
# }}}

# {{{ Styles
HTML_STYLE = u"""\
/*基于hi-pda.com上wb.01提供的CSS，略作调整*/

/*SONY：字体安装在系统字体目录*/
/*SONY：字体安装在内存FONT目录*/
/*SONY系统字体*/
/*iRex DR800SG：字体安装在内存fonts/ttf/目录*/
/*iRex DR800SG：字体安装在SD卡fonts目录*/
/*Amazon Kindle2 Duokan*/
/*翰林V3+*/
/*nook：字体安装在系统字体目录*/
/*nook：字体安装在内存里fonts目录*/
/*nook：字体安装在SD卡上fonts目录*/
/*nook：系统字体*/
/*embed*/


@font-face {
	font-family:"zw";
	src:url(res:///opt/sony/ebook/FONT/zw.ttf),
	url(res:///Data/FONT/zw.ttf),
	url(res:///opt/sony/ebook/FONT/tt0011m_.ttf)
	url(res:///fonts/ttf/zw.ttf),
	url(res:///../../media/mmcblk0p1/fonts/zw.ttf),
	url(res:///DK_System/system/font/zw.ttf),
	url(res:///abook/fonts/zw.ttf),
	url(res:///system/fonts/zw.ttf),
	url(res:///system/media/sdcard/fonts/zw.ttf),
	url(res:///sdcard/fonts/zw.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/zw.ttf);
}

@font-face {
	font-family:"fs";
	src:url(res:///opt/sony/ebook/FONT/fs.ttf),
	url(res:///Data/FONT/fs.ttf),
	url(res:///fonts/ttf/fs.ttf),
	url(res:///../../media/mmcblk0p1/fonts/fs.ttf),
	url(res:///DK_System/system/font/fs.ttf),
	url(res:///abook/fonts/fs.ttf),
	url(res:///system/fonts/fs.ttf),
	url(res:///system/media/sdcard/fonts/fs.ttf),
	url(res:///sdcard/fonts/fs.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/fs.ttf);
}

@font-face {
	font-family:"kt";
	src:url(res:///opt/sony/ebook/FONT/kt.ttf),
	url(res:///Data/FONT/kt.ttf),
	url(res:///fonts/ttf/kt.ttf),
	url(res:///../../media/mmcblk0p1/fonts/kt.ttf),
	url(res:///DK_System/system/font/kt.ttf),
	url(res:///abook/fonts/kt.ttf),
	url(res:///system/fonts/kt.ttf),
	url(res:///system/media/sdcard/fonts/kt.ttf),
	url(res:///sdcard/fonts/kt.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/kt.ttf);
}


@font-face {
	font-family:"ht";
	src:url(res:///opt/sony/ebook/FONT/ht.ttf),
	url(res:///Data/FONT/ht.ttf),
	url(res:///opt/sony/ebook/FONT/tt0003m_.ttf)
	url(res:///fonts/ttf/ht.ttf),
	url(res:///../../media/mmcblk0p1/fonts/ht.ttf),
	url(res:///DK_System/system/font/ht.ttf),
	url(res:///abook/fonts/ht.ttf),
	url(res:///system/fonts/ht.ttf),
	url(res:///system/media/sdcard/fonts/ht.ttf),
	url(res:///sdcard/fonts/ht.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/ht.ttf);
}


@font-face {
	font-family:"h1";
	src:url(res:///opt/sony/ebook/FONT/h1.ttf),
	url(res:///Data/FONT/h1.ttf),
	url(res:///fonts/ttf/h1.ttf),
	url(res:///../../media/mmcblk0p1/fonts/h1.ttf),
	url(res:///DK_System/system/font/h1.ttf),
	url(res:///abook/fonts/h1.ttf),
	url(res:///system/fonts/h1.ttf),
	url(res:///system/media/sdcard/fonts/h1.ttf),
	url(res:///sdcard/fonts/h1.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/h1.ttf);
}


@font-face {
	font-family:"h2";
	src:url(res:///opt/sony/ebook/FONT/h2.ttf),
	url(res:///Data/FONT/h2.ttf),
	url(res:///fonts/ttf/h2.ttf),
	url(res:///../../media/mmcblk0p1/fonts/h2.ttf),
	url(res:///DK_System/system/font/h2.ttf),
	url(res:///abook/fonts/h2.ttf),
	url(res:///system/fonts/h2.ttf),
	url(res:///system/media/sdcard/fonts/h2.ttf),
	url(res:///sdcard/fonts/h2.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/h2.ttf);
}


/*@font-face {
	font-family:"h3";
	src:url(res:///opt/sony/ebook/FONT/h3.ttf),
	url(res:///Data/FONT/h3.ttf),
	url(res:///fonts/ttf/h3.ttf),
	url(res:///../../media/mmcblk0p1/fonts/h3.ttf),
	url(res:///DK_System/system/font/h3.ttf),
	url(res:///abook/fonts/h3.ttf),
	url(res:///system/fonts/h3.ttf),
	url(res:///system/media/sdcard/fonts/h3.ttf),
	url(res:///sdcard/fonts/h3.ttf),
	url(res:///system/fonts/DroidSansFallback.ttf),
	url(fonts/h3.ttf);
}*/


body {
	padding: 0%;
	margin-top: 0%;
	margin-bottom: 0%;
	margin-left: 1%;
	margin-right: 1%;
	line-height:120%;
	text-align: justify;
	font-family:"zw";
	font-size:100%;
}
div {
	margin:0px;
	padding:0px;
	line-height:120%;
	text-align: justify;
	font-family:"zw";
}

p {
	text-align: justify;
	text-indent: 0em;
	line-height:120%;
    margin: 0;
    padding: 0.5% 0;
	/*margin-bottom:-0.9em;*/
}

a{
text-decoration:none;
}

.cover {
	/*width:100%;*/
	height:100%;
	text-align:center;
	padding:0px;
}


/*目录页*/
.contents {
	margin-left:20%;
	padding:0px;
	line-height:120%;
	text-align: justify;
	font-family:"ht","zw";
}


/*目录页文章作者*/
.contentauthor {
	padding-left: 20%;
	text-align: right;
	font-family:"kt","zw";
}

/*版权页*/
.copyright {
	margin-top:50px;
	margin-left:20%;
	padding:0px;
	/*line-height:100%;*/
	text-align: justify;
	font-family:"ht","zw";
	font-size:9pt;
}


.center {
	text-align: center;
	margin-left: 0%;
	margin-right: 0%;
}
.left {
	text-align: center;
	margin-left: 0%;
	margin-right: 0%;
}
.right {
	text-align: right;
	margin-left: 0%;
	margin-right: 0%;
}
.quotetitle {
	margin-left: 2em;
	margin-right: 1em;
	border-style: none solid none solid;
	border-width: 0px 1px 0px 5px;
	border-color: #CCCC00;
	text-align: justify;
	font-family:"ht","zw";
}
.heavy {
	font-family:"ht","zw";
	color:blue;
	/*font-weight:bold;*/
	/*font-size:10.5pt;*/
}
.author {
	font-family:"kt","zw";
	color:white;
	font-size:10.5pt;
}
.preface {
	font-family:"fs","zw";
}
.h1note {
	margin-top:5pt;
	margin-bottom:20pt;
	margin-left:38.2%;
	border-style: none none none solid;
	border-width: 0px 0px 0px 10px;
	border-color: blue yellow;
	font-family:"ht","zw";
	font-size:9pt;
}
.h2note {
	margin-top:50pt;
	margin-bottom:20pt;
	margin-left:0.58in;
	border-style: none none none solid;
	border-width: 0px 0px 0px 10px;
	border-color: blue yellow;
	font-family:"ht","zw";
	font-size:9pt;
	padding: 5px 5px 5px 5px;
}
h1 {
	color:blue;
	margin-top:61.8%;
	margin-left:33%;
	line-height:100%;
	text-align: justify;
	border-style: none double none solid;
	border-width: 0px 5px 0px 20px;
	border-color: purple;
	font-weight:bold;
	font-size:xx-large;
	font-family:"h1","ht","zw";
}
h2 {
	color:white;
	margin-top:0;
    margin-bottom:0.2em;
	line-height:100%;
	text-align: justify;
	border-style: none double none solid;
	border-width: 0px 5px 0px 20px;
	border-color: purple;
	background-color: gray;
	padding: 100px 5px 0.5em 5px;
	font-weight:bold;
	font-size:x-large;
	font-family:"h2","ht","zw";
}

/*副标题*/
.h2sub {
	color:orange;
	margin-top:-26px;
	line-height:100%;
	text-align: justify;
	border-style: none double none solid;
	border-width: 0px 5px 0px 20px;
	border-color: blue;
	border-left-color: blue;
	font-weight:bold;
	font-size:medium;
	font-family:"ht","zw";
}

h3 {
	color:blue;
	line-height:120%;
	text-align: justify;
	font-weight:bold;
	font-size:large;
	font-family:"fs","kt","ht","zw";
	/*margin-bottom:-0.9em;*/
    margin-botton: 0.5em;
	border-style: none none solid none;
	border-width: 0px 0px 1px 0px;
	border-color: purple;
}
h4 {
/*	color:gray;*/
	line-height:120%;
	text-align: justify;
	font-weight:bold;
	font-size:medium;
	font-family:"ht","zw";
	margin-bottom:-0.8em;
}
h5 {
	line-height:120%;
	text-align: justify;
	font-weight:bold;
	font-size:small;
	font-family:"kt","zw";
	margin-bottom:-0.9em;
}
h6 {
	line-height:120%;
	text-align: justify;
	font-weight:bold;
	font-size:x-small;
	margin-bottom:-0.9em;
}

/*正文中的分隔线*/
.divline {
	text-align: center;
	color:gray;
}
	

/*文末签名*/
.signature {
	padding-left:40%;
	font-family:"kt","zw";
	color:blue;
}
.date {
	padding-left:40%;
	font-family:"kt","zw";
	color:blue;
}
.from {
	font-family: "kt","zw";
	color: #800000;
}

.title {
  text-align: left;
}
a {
  text-decoration: none;
}
li {
	list-style-type:none;
}
.nostyle {
  list-style-type: none;
}

/** 书名页 **/
.title_page {
	page-break-before:always;
    position: relative;
}

.title_cover_page .cover {
    margin-top:7%;
    height: 50%;
    text-align: center;
}

.cover img {
    height: 100%;
}

.title_page .title {
	color:blue;
	margin-top:61.8%;
	margin-left:38.2%;
	line-height:100%;
	text-align: justify;
	border-style: none double none solid;
	border-width: 0px 5px 0px 20px;
	border-color: fuchsia;
	font-weight:bold;
	font-size:xx-large;
	font-family:"h1","ht","zw";
}

.title_cover_page .title {
    margin-top: 4.8%;
}

.title_page .author {
	color:gray;
	margin-left:38.2%;
	line-height:100%;
	text-align: justify;
    padding: 1em 5px 0px 20px;
	page-break-before:avoid;
	font-weight:bold;
	font-size:large;
	font-family:"fs","zw";
}

.chapter_cover_header .cover {
    margin-top:7%;
    height: 50%;
    text-align: center;
}

.chapter_cover_header h1 {
    margin-top: 4.8%;
}

.chapter_intro {
    margin: 1em;
	text-align: justify;
	font-family:"kt","zw";
    font-size:70%;
    line-height: 100%;
}

.chapter_header_h1 {
	page-break-before: always;
    page-break-after: always;
}

.chapter_header_h2 {
	page-break-before:always;
}

.chapter_author {
    font-family: "kt", "zw";
    text-align: right;
}

.chapter_header_h1 .chapter_author {
	color:gray;
    border:none;
    margin: 0.5em 0 0 33%;
	line-height:100%;
	text-align: justify;
    padding: 0px 5px 0px 20px;
	page-break-before:avoid;
	font-weight:bold;
	font-size:large;
	font-family:"fs","zw";
}

.chapter_header_h2 {
    margin-bottom: 1em;
}

.chapter_header_h2 .chapter_author,
.chapter_header_h2 .chapter_originated,
.chapter_header_h2 .chapter_publish_date,
.chapter_header_h2 .chapter_source
{
	color:blue;
	margin-top:0;
    margin-bottom: 0;
	line-height:100%;
	text-align: right;
	border-style: none double none solid;
	border-width: 0px 5px 0px 20px;
	border-color: gray;
	background-color: silver;
	padding: 5px 5px 5px 5px;
	font-weight:bold;
	font-size:90%;
	font-family:"kt","zw";
}

.section_title {
    margin-top: 0.5em;
    margin-bottom: 0.1em;
	font-family:"ht","kt","zw";
    font-weight:bold;
    font-size: 120%;
    page-break-after:avoid;
}

/* 引用 */
.quote {
	margin-left: 2em;
	margin-right: 1em;
	border-style: none none none solid;
	border-width: 0px 0px 0px 5px;
	border-color: #CCCC00;
    color: #333333;
    font-size:80%;
	font-family:"kt","zw";
}

.img {
    text-align: center;
}

.img .desc {
    margin: 0.2em 0 0.5em 0;
    page-break-before:avoid;
    text-align: center;
	font-family:"kt","zw";
    font-size: 80%;
    color: #666666;
}

.img img {
    page-break-after:avoid;
    max-height: 85%;
}

"""

EPUB_STYLE = HTML_STYLE
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

def getfilelist(chmpath):
    '''
    get filelist of the given path chm file
    return (bool,fileurllist)
    '''
    def callback(cf,ui,lst):
        '''
        innermethod
        '''
        lst.append(ui.path)
        return chmlib.CHM_ENUMERATOR_CONTINUE

    assert isinstance(chmpath,unicode)
    chmfile=chmlib.chm_open(chmpath.encode(sys.getfilesystemencoding()))
    lst=[]
    ok=chmlib.chm_enumerate(chmfile,chmlib.CHM_ENUMERATE_ALL,callback,lst)
    chmlib.chm_close(chmfile)
    return (ok,lst)

# }}}

# {{{ Book structures
#   {{{ -- class Chapter
class Chapter:
    def __init__(self):
        self.title        = u""      # title used in the TOC
        self.title_inner  = u""      # title display in the content. use title if empty
        self.author       = u""
        self.id           = u""
        self.level        = 0
        self.content      = list()   # list of lines
        self.img_list     = list()   # 有些页面上都是图片
        self.subchapters  = list()   # list of Chapter
        self.src          = u""      # filename contains this chapter
        self.cover        = None     # Img instance of the cover of chapter
        self.parent       = None     # 父章节
        self.intro        = None     # 章节概要
        self.originated   = u""      # 发自...
        self.publish_date = u""      # 时间
        self.source       = u""      # 来源
#   }}}

#   {{{ -- class BookInfo
class BookInfo:
    def __init__(self):
        self.title        = u""
        self.sub_title    = u""
        self.author       = u""
        self.category     = u""
        self.chapters     = list()      # list of Chapter
        self.cover        = None        # Img instance of the cover
        self.publisher    = u""
        self.isbn         = u""
        self.publish_date = u""
        self.publist_ver  = u""
#   }}}

#   {{{ -- class LineContainer
class LineContainer(object):
    """ 可以包含若干行的部件 """
    def __init__(self, lines):
        self.lines = lines
#   }}}

#   {{{ -- class Quote
class Quote(LineContainer):
    def __init__(self, lines):
        super(LineContainer, self).__init__(lines)
#   }}}

#   {{{ -- class Section
class Section(object):
    def __init__(self, title):
        self.title = title
#   }}}

#   {{{ -- Img like classes
#     {{{ ---- class Img
class Img(object):
    def __init__(self, filename=u'', desc=u''):
        self.filename_  = filename
        self.extension_ = os.path.splitext(filename)[1].lower()
        self.desc_      = desc

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
#     }}}

#     {{{ ---- class SingleImg
class SingleImg(Img):
    cache = dict()      # a dict of fullpath->image_data

    def __init__(self, filename, inputter=None, desc=u""):
        super(SingleImg, self).__init__(filename, desc)
        self.inputter  = inputter if inputter else FileSysInputter("")
        
        fullpath = inputter.fullpath(filename)

        if not self.cache.has_key(fullpath):
            self.image_data = {
                'id'       : u"",
                'fullpath' : fullpath,
                'inputter' : self.inputter,
                'filename' : filename,
            }

            self.cache[fullpath] = self.image_data
        else:
            self.image_data = self.cache[fullpath]

    def unique_key(self):
        return self.image_data['fullpath']

    def fetch_image_(self):
        if not self.image_data.has_key('content'):
            content = self.image_data['inputter'].read_binary(self.image_data['filename'])

            f = StringIO(content)
            width, height = Image.open(f).size
            f.close()

            self.image_data['content'] = content
            self.image_data['width']   = width
            self.image_data['height']  = height

    def width(self):
        self.fetch_image_()
        return self.image_data['width']

    def height(self):
        self.fetch_image_()
        return self.image_data['height']

    def set_id(self, id):
        assert(not self.image_data['id'])
        self.image_data['id'] = id

    def id(self):
        return self.image_data['id']

    def content(self):
        self.fetch_image_()
        return self.image_data['content']
#     }}}

#     {{{ -- class SuitableImg
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
#     }}}

#   }}}
# }}}

# {{{ Book info utilities
def book_file_name(title, author, suffix):
    title = title.strip()
    if not title:
        title = u"unnamed"


    author = author.strip()
    if author:
        filename = u"《{title}》作者：{author}".format(title=unicode(title), author=unicode(author))
    else:
        filename = u"《{title}》".format(title=unicode(title))

    filename += unicode(suffix.strip())

    return filename

def parse_filename(filename, title, author):
    if not title or not author:
        (guess_title, guess_author) = guess_title_author(filename)

        if not title:
            title = guess_title

        if not author:
            author = guess_author

    return (title, author)

def guess_title_author(filename):
    re_remove_ext = re.compile(u'\.[^.]*$', re.IGNORECASE)
    re_ignore     = re.compile(u'\([^)]*\)|\[[^]]*\]|［[^］]*］|『[^』]*』|【[^】]*】|（[^）]*）', re.IGNORECASE)
    re_title_author_patterns = (
        re.compile(u'.*《(?P<title>[^》]+)》(?:[^:：]*[:：])?(?P<author>[^:：]+)', re.IGNORECASE),
        re.compile(u'(?P<title>.+)作者\s*[:：]\s*(?P<author>.+)', re.IGNORECASE),      # 有'作者'字样
        re.compile(u'(?P<title>.+)[-－_＿:：](?P<author>.+)', re.IGNORECASE),          # -或_或:分隔
        re.compile(u'^(?P<title>[^ 　]+)[ 　]+(?P<author>.+)', re.IGNORECASE),         # 空格分隔
        )
    re_title_only_patterns = (
        re.compile(u'《(?P<title>[^》]+)》', re.IGNORECASE),
        )

    name = re_remove_ext.sub(u"", os.path.basename(filename.strip(u'/')))
    name = re_ignore.sub(u" ", name)

    title  = "";
    author = "";

    for pattern in re_title_author_patterns:
        m = pattern.match(name)
        if m:
            title  = m.group('title')
            author = m.group('author')
            title  = title.strip(u" 　\t- _－＿")
            author = author.strip(u" 　\t- _－＿")

            if title and author:
                break

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

    return (title, author)

def get_book_category(title, author):
    def lookup_zong_heng(title, author, encoding='utf-8'):
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
                u'<a[^>]*>(?P<title>.*?)</a>\s*' +
                u'</h1>\s*' +
                u'<p>\s*' +
                u'作者：<em><a[^>]*>(?P<author>.*?)</a></em>\s*' +
                u'分类：<em><a[^>]*>(?P<category>.*?)</a></em>\s*',
                s, re.IGNORECASE):
            result.append({
                'title'  : re.sub('<[^>]*>', '', match.group('title')),
                'author' : re.sub('<[^>]*>', '', match.group('author')),
                'l1cat'  : re.sub('<[^>]*>', '', match.group('category')),
                'l2cat'  : ""
                })

        logging.debug(u"{0} results from zongheng.".format(len(result)))
        return result

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
        books = json.loads(s)

        for book in books[0]:
            result.append({
                'title'  : book['BookName'],
                'author' : book['AuthorName'],
                'l1cat'  : book['CategoryName'],
                'l2cat'  : book['SubCategoryName']
                })

        logging.debug(u"{0} results from qidian.".format(len(result)))
        return result

    def lookup_book_category(title, author):
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
                    
        if match_book:
            return (match_book["title"], match_book["author"], match_book["l1cat"], match_book["l2cat"])

        return ("", "", "", "")

    r = lookup_book_category(title, author)
    if r[0]:
        return r

    m = re.match(u'(?P<title>.+)(?:合集|全集|系列)', title)
    if m:
        r = lookup_book_category(m.group('title'), author)
        if r[0]:
            return r

    return ("", "", "", "")
# }}}

# {{{ Code cleaner/normalizer

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

re_content_line_sep = re.compile(r"(<\s*br\s*\/?>|(?:</?p(?:\s[^>]*|\s*)>)|\r|\n)+", re.IGNORECASE)
re_content_cleanup_html = re.compile(r"<[^>]*>|\n|\r", re.IGNORECASE)
re_content_img = re.compile(
    u"<img[^>]*?\ssrc=(?P<quote1>['\"])?(?P<url>.*?)(?(quote1)(?P=quote1)|(?=\s|>))" +
    u"(?:[^>]*\salt=(?P<quote2>['\"])?(?P<desc>.*?)(?(quote2)(?P=quote2)|(?=\s|>)))?" +
    u"[^>]*>",
    re.IGNORECASE | re.DOTALL)
    
re_quote = re.compile(
    ur"<(?:q|blockquote)\b[^>]*>(?P<content>.+?)<\s*/\s*q\s*>",
    re.IGNORECASE | re.DOTALL)

# 从<img>的alt属性中提取图片的标题
def content_normalize_from_html(content, inputter, re_imgs=re_content_img):
    def content_normalize_img(content, inputter, re_imgs):
        lines = list()

        if not hasattr(re_imgs, '__iter__'):
            re_imgs = [re_imgs]

        # 找出所有可能的图片位置
        img_pos = list()
        
        for re_img in re_imgs:
            for m in re_img.finditer(content):
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
                lines.extend(content_text_normalize_from_html(content[start_pos:pos["start"]]))

            # 加入图片
            lines.append(SingleImg(pos["url"], inputter, title_normalize(pos["desc"])))

            start_pos = pos["end"]

        # 加入行末的内容
        if start_pos < len(content):
            lines.extend(content_text_normalize_from_html(content[start_pos:]))

        return lines

    lines = list()

    if not content:
        return lines

    # 处理所有引用
    start_pos = 0
    for m in re_quote.finditer(content):
        if m.start() > start_pos:
            lines.extend(content_normalize_img(content[start_pos:m.start()], inputter, re_imgs))

        quote_lines = content_normalize_img(m.group('content'), inputter, re_imgs)
        if quote_lines:
            lines.append(Quote(quote_lines))

        start_pos = m.end()

    # 加入最后的内容
    if start_pos < len(content):
        lines.extend(content_normalize_img(content[start_pos:], inputter, re_imgs))

    return lines

# 忽略图片
def content_text_normalize_from_html(content):
    lines = list()

    if not content:
        return lines

    lines = (re_content_cleanup_html.sub(u"", l) for l in re_content_line_sep.split(content))

    return content_text_normalize((unescape(l) for l in lines))

re_content_skip_lines = re.compile(u"^[^　 \t]*$")
re_content_cleanups = [
    [ re.compile(u"^[ ]{1,6}([^　 \ta-zA-Z])"), u"　　\\1" ],   # 行首的1到6个半角空格规范为两个全角空格
    [ re.compile(u"^[　]{0,3}([^　 \t])"), u"　　\\1" ],        # 行首的0到3个全角空格规范为两个全角空格
]

def content_text_normalize(lines):
    content = list()

    for line in lines:
        for l in line.splitlines():
            for r in re_content_cleanups:
                l = r[0].sub(r[1], l)

            if re_content_skip_lines.match(l):
                continue

            content.append(l)

    return content

def trim(line):
    return re.sub(u"^[ \t　]+|[ \t　]+$", u"", line)

def title_normalize(title):
    if not title:
        return u""

    return re.sub(u"^(·|○)+|(·|○)+$|^[ 　]+|[ 　]$", u"", title, re.IGNORECASE)

def title_normalize_from_html(title):
    if not title:
        return u""

    return re.sub(u"(?i)^(·|○)+|(·|○)+$|^[ 　]+|[ 　]$", u"", unescape(re.sub(u"<[^>]*>", u"", title)))
# }}}

# {{{ Inputters
# {{{ -- Inputter
class Inputter(object):
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
        print "Checking with chardet"
        encoding = chardet.detect(binary)["encoding"]
        print "  encoding is {0}".format(encoding)
        u = unicode(binary, encoding)
        last_encoding = encoding
        return u

    def read_lines(self, filename, encoding=None):
        return self.read_all(filename, encoding).splitlines(False)

    def fullpath(self, filename=None):
        raise NotImplementedError()
#   }}}

#   {{{ -- FileSysInputter
class FileSysInputter(Inputter):
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

    def isfile(self, filename):
        full_filename = self.fullpath(filename)
        return os.path.exists(full_filename) and os.path.isfile(full_filename)

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return os.path.normpath(os.path.join(self.basedir, filename))
#   }}}

#   {{{ -- ChmInputter
class ChmInputter(Inputter):
    def __init__(self, filename, encoding=""):
        def callback(cf,ui,lst):
            lst.append(ui.path)
            return chmlib.CHM_ENUMERATOR_CONTINUE

        super(ChmInputter, self).__init__(encoding)

        self.filename = filename
        self.chmfile  = chmlib.chm_open(filename.encode(sys.getfilesystemencoding()))
        filelist = list()
        ok=chmlib.chm_enumerate(self.chmfile,chmlib.CHM_ENUMERATE_ALL,callback,filelist)
        if not ok:
            raise Exception("chmlib.chm_enumerate failed")

        self.filelist = filelist

    def __enter__(self):
        return self

    def __exit__(self, *args):
        chmlib.chm_close(self.chmfile)

    def read_binary(self, filename):
        filename = os.path.normpath(filename)
        result, ui = chmlib.chm_resolve_object(self.chmfile, os.path.join(u"/", filename).encode("utf-8"))
        if (result != chmlib.CHM_RESOLVE_SUCCESS):
            raise Exception(u"Failed to resolve {0}: {1}".format(filename, result))

        size, content = chmlib.chm_retrieve_object(self.chmfile, ui, 0L, ui.length)
        if (size != ui.length):
            raise Exception(u"Failed to retrieve {0}: filesize is {1}, only got {2}".format(filename, ui.length, size))

        return content

    def isfile(self, filename):
        filename = os.path.normpath(filename)
        result, ui = chmlib.chm_resolve_object(self.chmfile, os.path.join(u"/", filename).encode("utf-8"))
        return result == chmlib.CHM_RESOLVE_SUCCESS

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return os.path.normpath(os.path.join(self.filename, filename))

#   }}}

#   {{{ -- UrlInputter
class UrlInputter(Inputter):
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

    def isfile(self, filename):
        return filename[-1:] != "/"

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return basejoin(self.baseurl, filename)

#   }}}

#   {{{ -- SubInputter
class SubInputter(Inputter):
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
        return self.inputter.read_binary(os.path.join(self.root, filename))

    def isfile(self, filename):
        return self.inputter.isfile(os.path.join(self.root, filename))

    def fullpath(self, filename=None):
        if filename == None:
            filename = self.entry

        return self.inputter.fullpath(os.path.join(self.root, filename))
#   }}}
# }}}

# {{{ Parsers
#   {{{ -- Parser
class Parser(object):
    def parse(self, inputter):
        raise NotImplementedError(u"Parser::parse() is not implemented!")

    @classmethod
    def parse_book(cls, inputter):
        logging.debug(u"{indent}Searching suitable parse for {path}".format(
                indent=u"      "*inputter.nested_level, path=inputter.fullpath()))

        if isinstance(inputter, UrlInputter):
            # 看看有没有与url对应的解释器
            for web_info in WEB_INFOS:
                if web_info["pattern"].match(inputter.fullpath()):
                    parser = globals()[web_info["parser"]]()
                    logging.debug(u"{indent}  Checking '{path}' with {parser}.".format(
                        path=inputter.fullpath(), parser=parser.__class__.__name__, indent=u"      "*inputter.nested_level))

                    try:
                        return parser.parse(inputter)
                    except NotParseableError as e:
                        # try next parser
                        logging.error(u"{indent}    {path} should be parsed with {parser}, but failed: {error}!".format(
                            path=inputter.fullpath(), indent=u"      "*inputter.nested_level, parser=parser.__class__.__name__, error=e))

                        raise NotParseableError(u"{file} is not parseable by any parser".format(file=inputter.fullpath()))
                    
        for parser in (HtmlBuilderCollectionParser(), EasyChmCollectionParser(), IFengBookParser(), TxtParser(), EasyChmParser(), HtmlBuilderParser()):
            logging.debug(u"{indent}  Checking '{path}' with {parser}.".format(
                path=inputter.fullpath(), parser=parser.__class__.__name__, indent=u"      "*inputter.nested_level))

            try:
                return parser.parse(inputter)
            except NotParseableError as e:
                # try next parser
                pass

        logging.error(u"{indent}    {path} is not parseable by any parser".format(
            path=inputter.fullpath(), indent=u"      "*inputter.nested_level))

        raise NotParseableError(u"{file} is not parseable by any parser".format(file=inputter.fullpath()))

#   }}}

#   {{{ -- HtmlBuilderParser
class HtmlBuilderParser(Parser):
    re_idx_comment = re.compile(u"<!--.*?-->")
    re_idx_toc     = re.compile(u".*<font class=f3>[^<]+", re.IGNORECASE)
    re_idx_intro   = re.compile(u".*<td\s+[^>]*\\bclass=m5\\b>(.+?)</td>", re.IGNORECASE)

    re_idx_levels  = (
        ( re.compile(u".*<td[^>]*class=m6[^>]*>(?P<title>[^<]+)</td>", re.IGNORECASE), 
          re.compile(u".*<table[^>]*>\s*<tr[^>]*>\s*<td[^>]*>\s*<p[^>]*>(?P<title>.+?)</td>\s*</tr>\s*</table>", re.IGNORECASE),
        ),
        ( re.compile(u".*<td[^>]*class=m2[^>]*>(?P<title>[^<]+)</td>", re.IGNORECASE), ),
    )
    re_idx_detail  = (
        re.compile(u".*<td[^>]*>[ \t　]*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>(?P<title>[^<]+)</A>.*?</td>", re.IGNORECASE),
        # <td><font size="2"> <A HREF="刘慈欣003.htm" > <font color="#800000">【1】远航！远航！</font></A></font></td>
        # <td width="217"><font size="2"> <A HREF="刘慈欣004.htm" > <font color="#800000">【2】<span style="letter-spacing: -1pt">《东京圣战》和《冷酷的方程式》</span></font></A></font></td>
        # <td><font color="#0000FF">&nbsp;</font><A HREF="刘慈欣000.htm" ><font color="#0000FF">★刘慈欣资料</font></A></td>
        re.compile(u".*<td[^>]*>\s*(?:</?font[^>]*>(?:&nbsp;|\s)*)*<A[^>]*HREF=['\"](?P<url>[^\"']+)['\"][^>]*>(?P<title>.+?)</A>\s*(?:</?font[^>]*>\s*)*</td>", re.IGNORECASE),
    )

    re_title = re.compile(r"\s*<title>\s*([^<]+)\s*", re.IGNORECASE)
    re_content_begin = re.compile(r"<!--(?:HTMLBUILERPART|BookContent Start).*?-->")
    re_content_end = re.compile(r"<!--(?:/HTMLBUILERPART|BookContent End).*?-->")

    # <td align=center><img src=../image4/nkts.jpg class=p1 alt=南柯太守></td>
    #re_img_list = re.compile(u".*<td[^>]*><img src=(?P<src>[^'\" \t]+) class=[^>]* alt=(?P<desc>[^> ]+)></td>")

    def _get_index_filenames(self, inputter):
        index_filenames = list()
        
        if inputter.entry:
            return [inputter.entry]
        else:
            for i in (u"cover.html", u"cover.htm", u"index.html", u"index.htm", ):
                if inputter.isfile(i):
                    index_filenames.append(i)

        if inputter.isfile(u"index1.html"):
            i = 1
            while True:
                filename = u"index{0}.html".format(i)
                if not inputter.isfile(filename):
                    break;
                
                index_filenames.append(filename)
                i += 1

        return index_filenames

    def parse(self, inputter):
        def read_chapter(inputter, filename, indent):
            logging.debug(u"{indent}    Parsing file {filename}...".format(filename=filename, indent=u" "*indent));

            chapter = Chapter()

            is_in_content = False

            try:
                for line in inputter.read_lines(filename):
                    if not line:
                        continue

                    if not chapter.title:
                        m = self.re_title.match(line)
                        if m:
                            chapter.title = title_normalize_from_html(m.group(1))
                            continue
                    
                    # 在正文内容中
                    if is_in_content:
                        m = self.re_content_end.search(line)
                        if not m:
                            chapter.content.extend(content_normalize_from_html(line, inputter))
                            continue

                        # 出现正文结束标志，但前半行可能有内容
                        chapter.content.extend(content_normalize_from_html(line[0:m.start()], inputter))
                        is_in_content = False
                        line = line[m.end():]

                    # 检查正文内容的开始
                    m = self.re_content_begin.search(line)
                    if m:
                        is_in_content = True
                        # 后半行可能有内容
                        chapter.content.extend(content_normalize_from_html(line[m.end():], inputter))
                        continue

            except IOError as e:
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

        intro = None
        root_chapter = Chapter()

        for index_filename in index_filenames:
            logging.info(u"{indent}    Parsing index file: {filename}...".format(filename=index_filename, indent=u"      "*inputter.nested_level))

            chapter_stack = [root_chapter]

            status = 0

            file_content = inputter.read_all(index_filename)
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
                        intro.content = content_text_normalize_from_html(m.group(1))
                        continue

                process_next_line = False
                for r in self.re_idx_detail:
                    m = r.match(file_content)
                    if m:
                        chapter_filename = m.group("url")
                        chapter_title    = title_normalize_from_html(m.group("title"))

                        if chapter_filename == "#":
                            continue

                        if len(chapter_title) == 0:
                            logging.warning(u"{indent}      No title found, ignoring url '{url}' in file '{filename}'".format(
                                url=chapter_filename, filename=index_filename, indent=u"      "*inputter.nested_level))

                            continue

                        next_pos = m.end()

                        status = 2
                        chapter = read_chapter(inputter, chapter_filename, inputter.nested_level * 6 + (chapter_stack[-1].level + 1) * 2)
                        if not chapter:
                            logging.warning(u"{indent}      Content not found for {title}: {filename}".format(
                                title=chapter_title, filename=chapter_filename, indent=u"      "*inputter.nested_level))
                            raise NotParseableError(u"Content not found for {title}: {filename}".format(
                                title=chapter_title, filename=chapter_filename, indent=u"      "*inputter.nested_level))

                        chapter.title = chapter_title   # 以目录中的标题为准
                        chapter.level = chapter_stack[-1].level + 1
                        chapter.parent = chapter_stack[-1]
                        chapter.parent.subchapters.append(chapter)
                        logging.debug(u"{indent}      Chapter: {title}".format(indent="  "*(3*inputter.nested_level+chapter.level), title=chapter.title))

                        process_next_line = True
                        break

                if process_next_line:
                    continue

                process_next_line = False
                for level in range(1, len(self.re_idx_levels) + 1):
                    for r in self.re_idx_levels[level-1]:
                        m = r.match(file_content)
                        if m:
                            next_pos = m.end()

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

        bookinfo = BookInfo()
        bookinfo.chapters = root_chapter.subchapters
        for subchapter in bookinfo.chapters:
            subchapter.parent = None

        if intro:
            bookinfo.chapters[0:0] = [intro]

        return bookinfo
#   }}}

#   {{{ -- EasyChmParser
class EasyChmParser(Parser):
    #re_pages = re.compile(u"\\bpages\s*\[\d+\]\s*=\s*\['(?P<filename>[^']+)'\s*,\s*'(?P<chapter_title>[^']*)'\s*,\s*'([^']*)'\s*(?:,\s*'(?P<l1title>[^']*)')?(?:,\s*'(?P<chapter_intro>[^']*)')?.*?\]\s*;", re.IGNORECASE)
    #re_pages = re.compile(u"\\bpages\s*\[\d+\]\s*=\s*\['(?P<filename>[^']+)'\s*,\s*'(?P<chapter_title>[^']*)'\s*,\s*'([^']*)'\s*(?<upper_titles>(?:,\s*'(?P<l1title>[^']*)')*)(?:,\s*'(?P<chapter_intro>[^']*)')?.*?\]\s*;", re.IGNORECASE)
    #re_pages = re.compile(u"\\pages\s*\[\d+\]\s*=\s*\[\s*'(.+?)'\s*\];")
    #re_pages_field_sep = re.compile(u"'\s*,\s*'")

    re_pages = re.compile(u"\\bpages\s*\[\d+\]\s*=\s*\['(?P<page>.+?)'\]\s*;", re.IGNORECASE)
    re_pages_field_sep = re.compile(u"'\s*,\s*'")

    re_content_first = re.compile(u"document\.write\s*\((\s*.*?)['\"]\s*\)\s*;", re.IGNORECASE | re.MULTILINE)
    re_inner_title_signature = re.compile(u"center")
    re_content_cleanups = [
        [re.compile(u"(?i)document\.write\s*\(\s*['\"]"), u"\n"],
        [re.compile(u"(?i)(?m)['\"]\s*\)\s*;?\s*$"), u""],
    ]
    re_intro_title = re.compile(u"^[ \t　]*【?(?P<title>[^】：:]+)[】：:][ \t　]*$")
    re_intro_removes = [
        re.compile(u"^[ \t　]*\**\.*[ \t　]*$"),
    ]
    re_cover = re.compile(u"<img\s*src=(?P<quote1>['\"])?(?P<src>.*?)(?(quote1)(?P=quote1)|(?=\s|>))", re.IGNORECASE)

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
        # 《徐公子胜治作品合集》.chm.js: pages[0]=['01_01','001回 阴阳一席坐，佛道两骛人','6086','第一卷 阴神篇','神游','神游'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] == fields[4] and fields[4] != fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title3': 4 },
        },
        # 《丹·布朗作品集》作者：[美]丹·布朗.chm.js: pages[0]=['1_01','书籍相关','970','达芬奇密码','达芬奇密码','①'];
        # 《卡徒》（精校文字全本）作者：方想.chm.js: pages[0]=['1_001','第一节 以卡为生','4970','第一集','1','第一集'];
        # 权柄-三戒大师.chm.js: pages[0]=['1_01','第一章 秦少爷初临宝地 防狼术小试牛刀','2876','第一卷 原上草','卷一','第一卷 原上草'];
        # 汤姆.克兰西作品集.chm.js: pages[0]=['01_01','第一章 伦敦市区:一个阳光灿烂的日子','10569','爱国者游戏','爱国者游戏','爱国者游戏'];
        { 'cond' : lambda idx,fields: len(fields) == 6 and fields[5] != fields[4],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3 },
        },

        # 《圣纹师》（实体封面版）作者：拂晓星.chm.js: pages[0]=['1-1','～第一章零之殿下～','7314','·第一集 愿望女神·','<img src=../txt/01.jpg id=...>','·第一集 愿望女神·','掌握人类命运的圣纹师，出现了前所未有的危机！<br>急剧'];
        # 未来军医-胜己.chm.js: pages[0]=['01_01','第001章 诈尸','4297','第一卷 重生现代','<img src=../txt/1.jpg class=cover width=186 height=275>','※洛&#9825xin※精心制作','<img src=../txt/1.jpg class=cover width=600 height=889>'];
        { 'cond' : lambda idx,fields: len(fields) == 7 and fields[4][0:4].lower() == u"<img" and fields[6][0:4].lower() == u"<img",
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [4, 6] },
        },
        # 道门世家-普通.chm.js: pages[0]=['1-1','本集简介','0','第一集','第一集','A～★航星★','<img src=../txt/01.jpg class=cover>','<br>　　我是一个平','<img src=../txt/1.jpg class=cover>','0','第一集'];
        { 'cond' : lambda idx,fields: len(fields) == 11 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and re.search(r"<br\s*>", fields[7], re.IGNORECASE) and fields[10] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [6, 8], 'title2_intro': 7 },
        },
        # 恶魔狂想曲之明日骄阳.chm.js: pages[0]=['1-1','本集简介','0','第一集','第一集','A～★航星★','<img src=../txt/1.jpg class=cover>','<br>　　疾风佣兵','<img src=../txt/1.jpg class=cover>','0','第一集','<img src=../txt/01.jpg class=cover>'];
        { 'cond' : lambda idx,fields: len(fields) == 12 and fields[6][0:4].lower() == u"<img" and fields[8][0:4].lower() == u"<img" and fields[11][0:4].lower() == u"<img" and re.search(r"<br\s*>", fields[7], re.IGNORECASE) and fields[10] == fields[3],
          'map'  : { 'file': 0, 'title1': 1, 'title2': 3, 'title2_cover': [6, 8, 11], 'title2_intro': 7 },
        },
    ]

    def parse(self, inputter):
        def read_chapter(inputter, filename, title):
            chapter = Chapter()
            content = u"".join(inputter.read_lines(filename))

            m = self.re_content_first.search(content)
            if m and self.re_inner_title_signature.search(m.group(1)):
                has_inner_title = True
            else:
                has_inner_title = False

            for cleanup in self.re_content_cleanups:
                content = cleanup[0].sub(cleanup[1], content)

            content = content_text_normalize_from_html(content)

            if has_inner_title:
                chapter.title_inner = trim(content[0])
                chapter.content     = content[1:]
            else:
                chapter.content     = content

            chapter.title = title

            return chapter

        def parse_intro(html, default_title=BOOK_INTRO_TITLE):
            lines = content_text_normalize_from_html(html)
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

        # 如果有多张封面，使用最大的一张
        def parse_cover(htmls):
            if isinstance(htmls, str) or isinstance(htmls, unicode):
                htmls = [htmls,]

            covers = list()

            for html in htmls:
                m = self.re_cover.match(html)
                if m:
                    cover_filename = os.path.join("js", m.group("src"))
                else:   # 也可以直接提供图片的路径
                    cover_filename = html

                if inputter.isfile(cover_filename):
                    covers.append(SingleImg(cover_filename, inputter))

            if not covers:
                return None
            elif len(covers) > 1:
                return SuitableImg(*covers, desc=u'')
            else:
                return covers[0]

        # 如果有入口文件，则入口文件只能是start.htm
        if inputter.entry and inputter.entry != u"start.htm" or not inputter.isfile(os.path.join(u"js", u"page.js")):
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 把pages.js的内容解释到pages列表中
        pages = list()
        for m in self.re_pages.finditer(inputter.read_all(os.path.join(u"js", u"page.js"))):
            pages.append(self.re_pages_field_sep.split(m.group(1)))

        # 逐项处理pages
        max_title_level = 0     # 最大标题层次数，只有1级为1，两级为2...
        top_title_count = 0     # 顶层标题计数，用于对应txt/目录下的jpg文件
        next_intro = None       # 有些格式中，把章节简介和封面放在前面一行
        next_cover = None

        bookinfo = BookInfo()
        intro = None
        root_chapter = Chapter()
        root_chapter.level = sys.maxint
        chapter_stack = [root_chapter]

        for idx in xrange(len(pages)):
            for rule in self.pages_rules:
                if not rule['cond'](idx, pages[idx]):
                    continue

                # 滿足条件
                if rule['map'].has_key('book_cover'):
                    # 提供了书本的封面
                    cover = parse_cover([pages[idx][i] for i in rule['map']['book_cover']])
                    if cover:
                        bookinfo.cover = cover
                        logging.debug(u"{indent}  Found book cover".format(
                            indent=u"      "*inputter.nested_level))
        
                if rule['map'].has_key('book_intro'):
                    # 提供了书本的简介
                    intro = Chapter()
                    intro.title, intro.content = parse_intro(pages[idx][rule['map']['book_intro']], BOOK_INTRO_TITLE)

                if rule['map'].has_key('next_cover'):
                    # 提供了下一章节的封面
                    next_cover = parse_cover([pages[idx][i] for i in rule['map']['next_cover']])
        
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
                        chapter.title = title_normalize_from_html(pages[idx][rule['map'][title_name]])
                    else:
                        chapter = read_chapter(
                            inputter, 
                            os.path.join(u"txt", pages[idx][rule['map']['file']] + u".txt"),
                            title_normalize_from_html(pages[idx][rule['map'][title_name]]))

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
                        chapter.cover = parse_cover([pages[idx][i] for i in rule['map'][title_name + u"_cover"]])

                    # 对于最高层的标题，看看txt/目录有没有对应的封面图片
                    if lvl == max_title_level:
                        top_title_count += 1

                        if not chapter.cover:
                            chapter.cover = parse_cover([u"{0}.jpg".format(top_title_count), u"0{0}.jpg".format(top_title_count)])

                    # 已经生成好chapter，放到适当的位置
                    while lvl >= chapter_stack[-1].level:
                        chapter_stack.pop()

                    chapter.parent = chapter_stack[-1]
                    chapter.parent.subchapters.append(chapter)
                    chapter_stack.append(chapter)

                    logging.debug(u"{indent}    {title}{content}{cover}{intro}".format(
                        indent=u"  "*(3*inputter.nested_level+max_title_level-chapter.level+1), title=chapter.title,
                        content=u"" if chapter.content else u" w/o content",
                        cover=u" w/ cover" if chapter.cover else u"", intro=u" w/ intro" if chapter.intro else u""))

                # 处理完一条pages记录，不再尝试后续的rule
                break

        bookinfo.chapters = root_chapter.subchapters
        for subchapter in bookinfo.chapters:
            subchapter.parent = None

        if intro:
            bookinfo.chapters[0:0] = [intro]

        return bookinfo
#   }}}

#   {{{ -- IFengBookParser
class IFengBookParser(Parser):
    re_info = re.compile(
        u"<div class=\"infoTab\">\s*" +
        u"<table[^>]*>\s*" +
        u"<tr[^>]*>\s*" +
        u".*?<img src=\"(?P<cover>[^\"]+)\".*?</td>\s*" +
        u"<td[^>]*>\s*" +
        u"<span[^>]*><a\s[^>]*>(?P<title>.+?)</a></span>\s*" +
        u"(?:<span class=\"us_gray\">(?P<sub_title>[^<]+)</span>)?" +
        u".*?" +
        u"<td[^>]*id=\"authors\"[^>]*>\s*<a[^>]*>(?P<author>[^<]*)</a>" +
        u".*?" +
        u"<td[^>]*id=\"publisher\"[^>]*>\s*<a[^>]*>(?P<publisher>[^<]*)</a>" +
        u".*?" +
        u"(?:<td[^>]*>ISBN： </td>\s*<td>(?P<isbn>[^<]*)</td>)?" +
        u".*?" +
        u"(?:<td[^>]*>出版日期：\s*</td>\s*<td>(?P<publish_date>[^<]*)</td>)?" +
        u".*?" +
        u"(?:<td[^>]*>版 次：\s*</td>\s*<td>(?P<publish_ver>[^<]*)</td>)?" +
        u".*?" +
        u"(?:<td[^>]*>所属分类：\s*</td>\s*<td>\s*<a[^>]*>(?P<category>[^<]*)</a>)?" +
        u"", re.IGNORECASE | re.DOTALL)
        
    re_preliminaries = (
        re.compile(
            u"<div class=\"autherIntro\">\s*" +
            u"<h2><span>(?P<title>[^<]*)</span></h2>\s*" +
            u"(?P<content>.+?)</div>" +
            u"", re.IGNORECASE | re.DOTALL),
        re.compile(
            u"<div class=\"bookIntro\">\s*" +
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

    def parse(self, inputter):
        if not inputter.entry:
            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        file_content = inputter.read_all(inputter.entry)

        # 找出书的基本信息
        bookinfo = BookInfo()
        m = self.re_info.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. infoTab not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        bookinfo.title = title_normalize_from_html(m.group("title"))
        if m.group("sub_title"):
            bookinfo.sub_title = title_normalize_from_html(m.group("sub_title"))

        bookinfo.author = title_normalize_from_html(m.group("author"))
        bookinfo.category = title_normalize_from_html(m.group("category"))
        if m.group("cover"):
            bookinfo.cover = SingleImg(m.group("cover"), inputter)

        bookinfo.publisher = title_normalize_from_html(m.group("publisher"))
        bookinfo.isbn = title_normalize_from_html(m.group("isbn"))
        bookinfo.publish_date = title_normalize_from_html(m.group("publish_date"))
        bookinfo.publish_ver = title_normalize_from_html(m.group("publish_ver"))

        logging.debug(u"    Book info:")
        logging.debug(u"      BookName: {title}".format(title=bookinfo.title))
        logging.debug(u"      Author:   {author}".format(author=bookinfo.author))
        logging.debug(u"      Category: {category}".format(category=bookinfo.category))

        logging.debug(u"    Parsing book content")

        # 收集前置章节（作者简介、图书简介等）
        preliminaries = list()

        for r in self.re_preliminaries:
            m = r.search(file_content)
            if m:
                chapter = Chapter()
                chapter.title   = title_normalize_from_html(m.group("title"))
                chapter.content.extend(content_text_normalize_from_html(m.group("content")))

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
            chapter.intro = content_text_normalize_from_html(match_part.group("intro"))

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

                subchapter.content.extend(content_text_normalize_from_html(m.group("content")))

                chapter.subchapters.append(subchapter)

            bookinfo.chapters.append(chapter)

        # 看看有没有可以识别的章节
        if len(bookinfo.chapters) <= 0:
            raise NotParseableError(u"{file} is not parseable by {parser}. No chapter detected!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 插入前面的章节
        bookinfo.chapters[0:0] = preliminaries

        return bookinfo
#   }}}

#   {{{ -- InfzmParser
# 南方周末
class InfzmParser(Parser):
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

    #	<dt><span>本期头条:</span><a href="http://www.infzm.com/content/51232" title="翼城人口特区 一个县尘封25年的二胎试验">翼城人口特区 一个县尘封25年的二胎试验</a>
    #		</dt>
    #	<dd class="summary">在放开“二胎”25年之后的山西翼城，人口增长率反而低于全国水平，以性别比例为代表的各项人口指标均优于全国水平</dd>
    # </dl>
    re_topnews = re.compile(
        u'<dl class="topnews">\s*' +
        u'<dt><span>[^<]*</span><a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)">' +
        u'.*?<dd class="summary">(?P<summary>[^<]+)</dd>' +
        u'', re.IGNORECASE | re.DOTALL)

    re_lists = [
        [
            #	<h2>经济</h2>
            #	<dl>
            #		<dt></dt>
            #		<dd>
            #			<ul class="relnews">
            #				<li><a href="http://www.infzm.com/content/51073" title="消灭村庄？——中国新城市化之忧">消灭村庄？——中国新城市化之忧</a></li>
            #				<li><a href="http://www.infzm.com/content/51074" title="一位宜黄官员的来信">一位宜黄官员的来信</a></li>
            #
            #			</ul>
            #
            #		</dd>
            #		</dl>
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
            # 	<dl style="float: left; width: 300px;">
            # 			<dt id="rw_1">观点</dt>
            #   							<dd>
            # 			  <a href="http://www.infzm.com/content/50903" title="来信（20100927）">
            # 			  <span class="jt"></span>来信（20100927）  							  </a>
            # 			  </dd>
            # 			  <a href="http://www.infzm.com/content/50885" title="【世相】助人为恐">
            # 			  <span class="jt"></span>【世相】助人为恐  							  </a>
            # 			  </dd>
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
            #   							<dd>
            # 			  <a href="http://www.infzm.com/content/50903" title="来信（20100927）">
            # 			  <span class="jt"></span>来信（20100927）  							  </a>
            # 			  </dd>
            re.compile(
                u'<dd>\s*' +
                u'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)">',
                re.IGNORECASE)
        ],
    ]

    # <div id="detailContent">
    # 	<h1>【诺贝尔奖2010】钢笔字是如何变成赔率的——诺贝尔奖的博彩游戏</h1>
    # 	<p class="relInfo">
    # 		<span class="author">
    # 			<em>作者:</em>
    # 			<strong>南方周末特约撰稿 魏一帆（Tim Hathaway）　翻译：李宏宇</strong>
    # 
    # 		</span>
    # 			  						<span class="originated">发自北京 伦敦 连线报道</span>
    # 			  						<span class="pubTime">2010-10-13 17:29:24</span>
    # 		<span class="source"><em>来源:</em>南方周末</span>
    # 	</p>
    # 	<div class="contents">
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

        #print m.group("content")
        #print content_normalize_from_html(m.group("content", inputter))
        chapter = Chapter()
        chapter.title = title_normalize_from_html(m.group("title"))
        chapter.author = title_normalize_from_html(m.group("author"))
        chapter.originated = title_normalize_from_html(m.group("originated"))
        chapter.publish_date = title_normalize_from_html(m.group("publish_date"))
        chapter.source = title_normalize_from_html(m.group("source"))

        chapter.content = list()
        start_pos = 0
        content = m.group("content")

        for m in self.re_section_title.finditer(content):
            if m.start() > start_pos:
                chapter.content.extend(content_normalize_from_html(content[start_pos:m.start()], inputter, self.re_news_content_img))

            chapter.content.append(Section(title_normalize_from_html(m.group("title"))))

            start_pos = m.end()

        if start_pos < len(content):
            chapter.content.extend(content_normalize_from_html(content[start_pos:], inputter, self.re_news_content_img))

        return chapter

    def parse(self, inputter):
        if not inputter.entry:
            raise notparseableerror(u"{file} is not parseable by {parser}".format( file=inputter.fullpath(), parser=self.__class__.__name__))

        file_content = inputter.read_all(inputter.entry)
        #print file_content

        # 找出基本信息
        bookinfo = BookInfo()
        m = self.re_info.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. cover not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        bookinfo.title = u"{title}-{version}".format(
            title=title_normalize_from_html(m.group("title")),
            version=title_normalize_from_html(m.group("version")))

        logging.debug(u"    {title}".format(title=bookinfo.title))

        bookinfo.sub_title = title_normalize_from_html(m.group("date"))
        bookinfo.cover = SingleImg(m.group("cover"), inputter)
        bookinfo.author = u"南方报业传媒集团"
        bookinfo.category = CATEGORY_NEWS_PAPER

        m = self.re_topnews.search(file_content)
        if not m:
            raise NotParseableError(u"{file} is not parseable by {parser}. topnews not found!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        logging.debug(u"      TopNews: {title} ({url})".format(title=title_normalize_from_html(m.group("title")), url=m.group("url")))

        chapter = self.parse_chapter(m.group("url"), inputter)
        bookinfo.chapters.append(chapter)

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
                bookinfo.chapters.append(chapter)
            else:
                logging.debug(u"      No sub chapters found, skipping {title}".format(title=chapter.title))
        
        # 不需要重排TOC
        options.rearrange_toc = False

        return bookinfo
#   }}}

#   {{{ -- TxtParser
class TxtParser(Parser):
    def parse(self, inputter):
        if not inputter.entry or inputter.entry[-4:].lower() != ".txt":
            raise NotParseableError(u"{file} is not parseable by {parser}. Not .txt file!".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        root_chapter = Chapter()
        chapter_stack = [root_chapter]

        content = list()
        for line in inputter.read_lines(inputter.entry):
            m = re.match("^(=+|#+)\s(\S.*$)", line)
            if m:
                # 标题行
                level = len(m.group(1))

                if level > chapter_stack[-1].level:
                    # 进入子标题，子标题之前的内容都作为上层标题的简介
                    chapter_stack[-1].intro = content_text_normalize(content)
                else:
                    chapter_stack[-1].content = content_text_normalize(content)

                    while level <= chapter_stack[-1].level:
                        chapter_stack.pop()
                        
                content = list()

                chapter = Chapter()
                chapter.title = title_normalize(m.group(2))
                chapter.level = level
                logging.debug(u"{indent}  Level {level} toc: {title}".format(
                    indent=u"  "*(chapter.level+3*inputter.nested_level), level=chapter.level, title=chapter.title))

                chapter.parent = chapter_stack[-1]
                chapter.parent.subchapters.append(chapter)
                chapter_stack.append(chapter)
            else:   # 非标题行
                content.append(line)

        chapter_stack[-1].content = content_text_normalize(content)

        bookinfo = BookInfo()
        bookinfo.chapters = root_chapter.subchapters
        bookinfo.intro = root_chapter.intro

        return bookinfo
#   }}}

#   {{{ -- CollectionParsers
#     {{{ ---- CollectionParser
class CollectionParser(Parser):
    entrys = ()
    re_comment = re.compile(u"<!--.*?-->")
    re_remove_querys = re.compile(u"[#\?].*$")
    re_levels  = ()
    re_links   = ()
    re_extra     = None
    re_extra_end = None

    def parse(self, inputter):
        bookinfo = BookInfo()
        extra_chapters = list()

        if inputter.entry:
            # 如果已经指定了入口文件则直接使用之
            index_files = (inputter.entry, )
        else:
            index_files = self.entrys

        for index_file in index_files:
            local_extras = list()
            root_chapter = Chapter()
            chapter_stack = [root_chapter]

            if not inputter.isfile(index_file):
                continue

            logging.debug(u"{indent}    Parsing {file}".format(
                file=index_file, indent=u"      "*inputter.nested_level))

            line_iter = (self.re_comment.sub(u"", l) for l in inputter.read_lines(index_file)).__iter__()

            need_read_next_line = True

            links = list()

            try:
                # 扫描整个文件，找出所有链接，保存到links中
                while True:
                    # 下一行未读入，需要读
                    if need_read_next_line:
                        line = line_iter.next()

                    # 缺省每次进入循环都要读入新行，但可以通过本开关跳过读入动作
                    need_read_next_line = True

                    for re_link in self.re_links:
                        m = re_link.match(line)

                        if not m:
                            continue

                        root  = self.re_remove_querys.sub(u"", m.group("root"))
                        title = title_normalize_from_html(m.group("title"))

                        group_dict = m.groupdict()
                        author = group_dict["author"] if group_dict.has_key("author") else u""
                        cover = None
                        if group_dict.has_key("cover") and inputter.isfile(group_dict["cover"]):
                            cover = SingleImg(group_dict["cover"], inputter) 

                        level = chapter_stack[-1].level + 1
                        subinputter = SubInputter(inputter, root)
                        logging.info(u"{indent}    Found sub book: {path}: {title}{cover_info}".format(
                            indent=u"  "*(level+3*inputter.nested_level), path=subinputter.fullpath(), title=title,
                            cover_info=u" with cover" if cover else u""))

                        subpath = subinputter.fullpath()
                        for link in links:
                            if link['path'] == subpath:
                                # 本文件已经处理过了，不再重复处理。前一次也不加单独的父章节了
                                chapter = link['chapter']
                                if chapter and chapter.parent:
                                    # 把前一次的父章节去掉，移到祖父章节下
                                    for subchapter in chapter.subchapters:
                                        subchapter.parent = chapter.parent

                                    idx = chapter.parent.subchapters.index(chapter)
                                    chapter.parent.subchapters[idx:idx+1] = chapter.subchapters

                                    # 标记一下，下次就不会再处理了
                                    link['chapter'] = None
                                    
                                logging.info(u"{indent}      Skip duplicated sub book: {path}: {title}".format(
                                    indent=u"  "*(level+3*inputter.nested_level), path=subinputter.fullpath(), title=title))

                                break
                        else:
                            # 该链接未出现过
                            subbookinfo = Parser.parse_book(subinputter)
                            assert(subbookinfo)

                            chapter = Chapter()
                            chapter.title  = title
                            chapter.author = author
                            chapter.level  = level
                            chapter.cover  = cover
                            chapter.subchapters = subbookinfo.chapters

                            for subchapter in bookinfo.chapters:
                                subchapter.parent = chapter

                            chapter.parent = chapter_stack[-1]
                            chapter.parent.subchapters.append(chapter)

                            links.append({
                                'path'     : subinputter.fullpath(),
                                'chapter'  : chapter,
                            })

                        # 匹配成功，不再检查后续的re_links
                        break

                    for level in range(1, len(self.re_levels) + 1):
                        m = self.re_levels[level-1].match(line)
                        if m:
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
                    if self.re_extra and self.re_extra_end:
                        m = self.re_extra.match(line)
                        if m:
                            chapter = Chapter()
                            chapter.title = title_normalize_from_html(m.group("title"))

                            logging.debug(u"{indent}    Found extra chapter: {title}".format(
                                title=chapter.title, indent=u"      "*inputter.nested_level))

                            need_read_next_line = False # 总会在遇到不能处理的行时才退出下面的循环，因此已经读入下一行
                            while True:
                                line = line_iter.next()
                                if self.re_extra_end.match(line):
                                    break

                                chapter.content.extend(content_text_normalize_from_html(line))

                            if len(chapter.content) > 0:
                                local_extras.append(chapter)

            except StopIteration:
                # 本文件已经处理完
                pass

            if len(links) == 0:
                logging.debug(u"{indent}      No links found. Skipping {file}".format(
                    file=index_file, indent=u"      "*inputter.nested_level))

                continue

            # 把本索引文件中找到的内容加入到bookinfo中
            bookinfo.chapters.extend(root_chapter.subchapters)
            extra_chapters.extend(local_extras)

            for subchapter in bookinfo.chapters:
                subchapter.parent = None

        if len(bookinfo.chapters) == 0:
            logging.debug(u"{indent}    {file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__,
                indent=u"      "*inputter.nested_level))

            raise NotParseableError(u"{file} is not parseable by {parser}".format(
                file=inputter.fullpath(), parser=self.__class__.__name__))

        # 插入前面的额外章节
        bookinfo.chapters[0:0] = extra_chapters

        return bookinfo
#     }}}

#     {{{ ---- HtmlBuilderCollectionParser
class HtmlBuilderCollectionParser(CollectionParser):
    entrys = ( u"cover.html", u"cover.htm" )

    re_levels  = (
        re.compile(u".*<td[^>]*class=m6[^>]*>([^<]+)</td>.*", re.IGNORECASE),
        re.compile(u".*<td[^>]*class=m2[^>]*>([^<]+)</td>.*", re.IGNORECASE),
        )

    re_links = (
        re.compile(u".*<td[^>]*>[ \t　]*<A[^>]*HREF=['\"](?P<root>[^\"']+)/index\.html['\"]\s+title=进入阅读[^>]*>(?P<title>[^<]+)</A>.*", re.IGNORECASE),
        re.compile(
            u".*" +
            u"<td[^>]*>" +
            u"<a[^>]*\shref=(?P<quote1>['\"])?(?P<root>.*?)(?(quote1)(?P=quote1)|(?=\s|>))[^>]*>" +
            u"<img src=(?P<quote2>['\"])?(?P<cover>.*?)(?(quote2)(?P=quote2)|(?=\s|>))[^>]*\s" +
            u"alt=(?P<quote3>['\"])?(?P<title>.*?)☆进入阅读[^>]*>" + 
            u"</a>" +
            u"</td>"),
    )

    re_extra     = re.compile(u"\s*<font class=m2>(?P<title>[^<]+?)(?:[:：])?</font><br>\s*", re.IGNORECASE)
    re_extra_end = re.compile(u".*<(?!br>).*", re.IGNORECASE)

#     }}}

#     {{{ ---- EasyChmCollectionParser
class EasyChmCollectionParser(CollectionParser):
    entrys = ( u"cover.html", u"cover.htm", u"start.html", u"start.htm", u"index.html", u"index.htm" )

    re_links = (
        re.compile(u"\s*<a rel=\"(?P<rel>[^\"]*)\" title=\"开始阅读\" href=\"(?P<root>[^\"]+)/(start|index).html?\">(?P<title>[^<]+)</a>\s*", re.IGNORECASE),
		# <a rel="pic/12.jpg" title="告诉你一个不为所知的：神秘周易八卦" href="12/start.htm">作者：天行健0006</a>
        re.compile(u"\s*<a rel=\"(?:(?P<cover>[^\"]+?\.(?:jpg|png|gif|JPG|PNG|GIF))|[^\"]*)\" title=\"(?P<title>[^\"]+)\" href=\"(?P<root>[0-9]+)/(start|index).html?\">(?:作者：(?P<author>[^<]*)|[^<]*)</a>\s*", re.IGNORECASE),
    )

#     }}}
#   }}}
# }}}

# {{{ Converters

#   {{{ -- Converter
class Converter(object):
    def convert(self, outputter, bookinfo):
        raise NotImplementedError()

#   }}}

#   {{{ -- HtmlConverter
class HtmlConverter(object):
    def __init__(self, style=HTML_STYLE):
        self.style   = style

    def get_img_destpath_(self, files, img):
        return files["image"][img.unique_key()]["filename"]

    def css_style(self, extra_css=""):
        return HTML_STYLE + extra_css

    def cover_page(self, files, filename, bookinfo, cover):
        html = U"""\
      <div class='cover'><img alt="{title}" src="{cover}" /></div>
""".format(
            title = unicode(escape(bookinfo.title)),
            cover = os.path.relpath(self.get_img_destpath_(files, cover), os.path.dirname(filename)))

        return html

    def title_page(self, filename, bookinfo, start):
        html = u"""\
        <div class='title_page'>
            <div class='title'>{title}</div>
            <div class='author'>{author}</div>
            <div class='link_to_toc'></div>
            <!--
            <div class='link_to_start'>
            <p id='link_to_start'><a href='{start}'>{link_to_start}</a></p>
            </div>
            -->
        </div>
""".format(
            title         = unicode(escape(bookinfo.title)),
            author        = unicode(escape(bookinfo.author)),
            start         = unicode(escape(os.path.relpath(start, os.path.dirname(filename)))),
            link_to_start = u"开始阅读")

        return html;

    def title_cover_page(self, files, filename, bookinfo, cover, start):
        html = u"""\
        <div class='title_page title_cover_page'>
            <div class='cover'><img alt="{title}" src="{cover}" /></div>
            <div class='title'>{title}</div>
            <div class='author'>{author}</div>
            <div class='link_to_toc'></div>
            <!--
            <div class='link_to_start'>
            <p id='link_to_start'><a href='{start}'>{link_to_start}</a></p>
            </div>
            -->
        </div>
""".format(
            title         = unicode(escape(bookinfo.title)),
            author        = unicode(escape(bookinfo.author)),
            cover         = os.path.relpath(self.get_img_destpath_(files, cover), os.path.dirname(filename)),
            start         = unicode(escape(os.path.relpath(start, os.path.dirname(filename)))),
            link_to_start = u"开始阅读")

        return html;

    def chapter_header(self, files, filename, chapter):
        title = chapter.title_inner or chapter.title

        img = u""
        extra_class = u""

        hlevel = chapter.level if chapter.level <= 6 else 6

        # 如果没有子章节，则顶层章节也使用h2而不是h1（h1把标题单独放一页）
        if hlevel == 1 and len(chapter.subchapters) == 0:
            hlevel = 2

        if chapter.cover:
            img = u"<div class='cover{extra_class}'><img alt='{title}' src='{cover}' /></div>".format(
                title=escape(title), 
                cover=os.path.relpath(self.get_img_destpath_(files, chapter.cover), os.path.dirname(filename)),
                extra_class = u" large_cover" if chapter.cover.height() > MAX_EMBED_COVER_HEIGHT else u"")

            extra_class += u"chapter_cover_header"

        html = u"""\
        <div class='chapter_header chapter_header_{level} chapter_header_h{hlevel} {extra_class}' id='{id}'>{img}
""".format(
            level = chapter.level,
            hlevel = hlevel,
            extra_class = extra_class,
            id    = chapter.id,
            img   = img)

        if title:
            html += u"""\
        <h{hlevel} class='chapter_title chapter_title_{level}'>{title}</h{hlevel}>
""".format(
            hlevel = hlevel,
            level  = chapter.level,
            title  = escape(title))

        for c in ['author', 'originated', 'publish_date', 'source']:
            v = getattr(chapter, c)
            if v:
                html += u"<p class='chapter_{name}'>{value}</p>\n""".format(name = c, value = v)

        if chapter.intro:
            html += u"".join([
                u"<div class='chapter_intro chapter_intro_{level}'>\n".format(level=chapter.level),
                u"".join((u"<p>" + escape(line) + u"</p>\n" for line in chapter.intro)),
                u"</div>\n"])

        html += u"</div>"

        return html

    def chapter_content(self, files, filename, chapter):
        def dequote_content(line):
            lines = list()

            if isinstance(line, Section):
                lines.append(u''.join((u'<p class="section_title">', escape(line.title), u'</p>')))
            elif isinstance(line, Img):
                lines.append(u"<div class='img'><img alt='{alt}' src='{src}' />{desc}</div>".format(
                    src = os.path.relpath(self.get_img_destpath_(files, line), os.path.dirname(filename)),
                    alt = escape(line.desc()) if line.desc() else u"img",
                    desc = u"<div class='desc'>{desc}</div>".format(desc=escape(line.desc())) if line.desc() else u""
                    ))
            else:
                lines.append(u"".join((u"<p>", escape(line), u"</p>")))

            return lines

        lines = list()

        lines.append(u"<div class='chapter_content chapter_content_{level}'>".format(level=chapter.level))

        for line in chapter.content:
            if isinstance(line, Quote):
                lines.append(u'<div class="quote">')
                for l in line.lines:
                    # 处理引用。引用中可能也有图片
                    lines.extend(dequote_content(l))
                lines.append(u'</div>')
            else:
                lines.extend(dequote_content(line))

        lines.append(u"</div>")
        return u"\n".join(lines)

    def chapter_footer(self, filename, chapter):
        return u"<div class='chapter_footer chapter_footer_{level}'></div>".format(level=chapter.level)

    def html_header(self, filename, title, style="", cssfile=""):
        styles = u""
        if cssfile:
            styles += '<link type="text/css" rel="stylesheet" href="{0}" />\n'.format(
                os.path.relpath(cssfile, os.path.dirname(filename)))

        if style:
            styles += "<style type='text/css'>{0}</style>".format(style)

        return u"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
<title>{title}</title>
{styles}
</head>
<body>
""".format(title=escape(title), styles=styles)

    def html_footer(self, filename, bookinfo):
        return u"""\
</body>
</html>
"""

    def append_image(self, files, img):
        if not img:
            return u''

        # 未保存时才保存
        if not files["image"].has_key(img.unique_key()):
            img.set_id(u'{prefix}{idx}'.format(prefix=IMAGE_PREFIX, idx=len(files["image"])+1))

            files["image"][img.unique_key()] = {
                "filename": u'{path}{prefix}{idx}{ext}'.format(
                            path=IMAGE_PATH, prefix=IMAGE_PREFIX, idx=len(files["image"])+1, ext=img.extension()),
                "content":  img.content(),
                "id":       img.id(),
            }

    # {{{ ---- create_chapter_files
    def create_chapter_files(self, files, path, bookinfo, chapters, prefix_callback=lambda filename: u''):
        first_chapter_page = ""     # chapters中，首个chapter所在的文件名，上层章节可能会合并到这个文件

        for chapter in chapters:
            subpath = path
            if options.nestdir:
                subpath = os.path.join(path, chapter.id)

            if chapter.cover:
                # 加入封面图片
                self.append_image(files, chapter.cover)

            # 生成章节中的图片
            for line in chapter.content:
                if isinstance(line, Img):
                    self.append_image(files, line)
                elif isinstance(line, Quote):
                    # 引用中也可能有图片
                    for l in line.lines:
                        if isinstance(l, Img):
                            self.append_image(files, l)

            if chapter.content or not chapter.subchapters:
                # 有内容，或没有子章节，自成一个文件
                filename = u"{name}{ext}".format(name=os.path.join(path, chapter.id), ext=HTML_EXT)

                files["html"].append({
                    "filename": filename,
                    "content":  u"".join((
                        self.html_header(filename, chapter.title, cssfile=CSS_FILE),
                        prefix_callback(filename),  # 用当前文件名调用prefix_callback得到应插入的html
                        self.chapter_header(files, filename, chapter),
                        self.chapter_content(files, filename, chapter),
                        self.html_footer(filename, bookinfo),
                        )).encode("utf-8"),
                    "id":       chapter.id,
                    })

                if chapter.subchapters:
                    self.create_chapter_files(
                        files,
                        subpath,
                        bookinfo,
                        chapter.subchapters)

            else:
                # 无内容但有子章节，章节标题合并到第一个子章节中
                filename = self.create_chapter_files(
                    files,
                    subpath,
                    bookinfo,
                    chapter.subchapters, 
                    lambda filename: prefix_callback(filename) + self.chapter_header(files, filename, chapter))

            # 同一个文件中所有章节的链接都直接指向文件本身，以解决静读天下中章节会重复的问题
            chapter.src = u"{filename}".format(filename=filename, anchor=chapter.id)
            #chapter.src = u"{filename}#{anchor}".format(filename=filename, anchor=chapter.id)

            if not first_chapter_page:
                first_chapter_page = filename

            # prefix_callback的内容只写一次即可
            prefix_callback = lambda filename: u''

        return first_chapter_page
    # }}}

    def convert(self, outputter, bookinfo):
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
        if bookinfo.cover:
            self.append_image(files, bookinfo.cover)

        first_page = self.create_chapter_files(files, "", bookinfo, bookinfo.chapters)

        filename = TITLE_PAGE + HTML_EXT
        files["html"][0:0] = [{
            "filename": filename,
            "content":  u"".join((
                        self.html_header(filename, bookinfo.title, cssfile=CSS_FILE),
                        self.title_page(filename, bookinfo, first_page),
                        self.html_footer(filename, bookinfo),
                        )).encode("utf-8"),
            "id":       TITLE_PAGE,
        }]

        if bookinfo.cover:
            if bookinfo.cover.height() <= MAX_EMBED_COVER_HEIGHT:
                # 封面图片较小，可与书名页合并，把原来的书名页换掉
                filename = files["html"][0]["filename"]
                files["html"][0]["content"] = u"".join((
                    self.html_header(filename, bookinfo.title, cssfile=CSS_FILE),
                    self.title_cover_page(files, filename, bookinfo, bookinfo.cover, first_page),
                    self.html_footer(filename, bookinfo),
                )).encode("utf-8")
            else:
                # 插入封面页
                filename = COVER_PAGE + HTML_EXT
                files["html"][0:0] = [{
                    "filename": filename,
                    "content":  u"".join((
                                self.html_header(filename, bookinfo.title, cssfile=CSS_FILE),
                                self.cover_page(files, filename, bookinfo, bookinfo.cover),
                                self.html_footer(filename, bookinfo),
                                )).encode("utf-8"),
                    "id":       COVER_PAGE,
                }]

        for f in files["html"] + files["image"].values() + files["other"]:
            outputter.add_file(f["filename"], f["content"], id=f["id"] if f.has_key("id") else "")
#   }}}

# {{{ -- EpubConverter
class EpubConverter(Converter):
    def __init__(self):
        super(EpubConverter, self).__init__()

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

    def create_navpoint(self, xml, parent, chapters):
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

        def rearrange_toc_tree(navPointElems, maxSubToc):
            originIdx = 0
            while len(navPointElems) > maxSubToc:
                # 如果所有子节点都已经是二级节点，那么就从第0项重新开始，再加入一层
                if (originIdx >= len(navPointElems)):
                    originIdx = 0

                firstIdx = originIdx
                lastIdx  = originIdx + maxSubToc - 1 if originIdx + maxSubToc <= len(navPointElems) else len(navPointElems) - 1
                firstLabel = navPointElems[firstIdx]["firstLabel"]
                lastLabel  = navPointElems[lastIdx]["lastLabel"]
                src = navPointElems[firstIdx]["src"]

                newNavPointElem = new_navpoint_elem(
                    navPointElems[firstIdx]["elem"].getAttribute(u"id") + "m",      # 不断加入'm'作为后缀，生成新的ID
                    u"{firstLabel} .. {lastLabel}".format(firstLabel=firstLabel, lastLabel=lastLabel),
                    src)

                for i in xrange(firstIdx, lastIdx + 1):
                    newNavPointElem.appendChild(navPointElems.pop(originIdx)["elem"])

                navPointElems[originIdx:originIdx] = [{"elem":newNavPointElem, "firstLabel":firstLabel, "lastLabel":lastLabel, "src":src}]
                originIdx += 1

        if chapters:
            elems = list()
            for chapter in chapters:
                # 有title才生成目录项
                if chapter.title:
                    src = os.path.join(CONTENT_DIR, chapter.src)
                    navPointElem = new_navpoint_elem(chapter.id, chapter.title, src)
                    elems.append({"elem":navPointElem, "firstLabel":unicode(chapter.title), "lastLabel":unicode(chapter.title), "src":src})
                    self.create_navpoint(xml, navPointElem, chapter.subchapters)
            
            chapter_level = chapters[0].level

            # 调整TOC，使每层的TOC不超过指定的数量
            if options.rearrange_toc:
                maxEpubSubToc = DEFAULT_MAX_EPUB_SUB_TOC
                if MAX_EPUB_SUB_TOCS.has_key(chapter_level):
                    maxEpubSubToc = MAX_EPUB_SUB_TOCS[chapter_level]

                rearrange_toc_tree(elems, maxEpubSubToc)

            for e in elems:
                parent.appendChild(e["elem"])

    def generate_ncx(self, bookinfo, identifier):
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
        generatorElem.setAttribute("content", u'{prog} {ver}'.format(prog=optparser.prog, ver=VERSION))

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
        textElem.appendChild(xml.createTextNode(unicode(bookinfo.title)))

        if bookinfo.author:
            # /ncx/docAuthor
            authorElem = xml.createElement("docAuthor")
            ncxElem.appendChild(authorElem)

            # /ncx/docAuthor/text
            textElem = xml.createElement("text")
            authorElem.appendChild(textElem)
            textElem.appendChild(xml.createTextNode(unicode(bookinfo.author)))

        # /ncx/navMap
        navMapElem = xml.createElement("navMap")
        ncxElem.appendChild(navMapElem)

        # 生成各navPoint
        self.create_navpoint(xml, navMapElem, bookinfo.chapters)
        self.add_playorder_to_navpoint(navMapElem)

        # /ncx/head/meta[name=depth]
        depthElem = xml.createElement("meta")
        headElem.appendChild(depthElem)
        depthElem.setAttribute("name", "dtb:depth")
        depthElem.setAttribute("content", unicode(self.get_navpoint_depth(navMapElem)))

        return pretty_xml(xml)

    def generate_opf(self, bookinfo, identifier, filelist):
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
        titleElem.appendChild(xml.createTextNode(unicode(bookinfo.title)))

        # /package/metadata/creator
        authorElem = xml.createElement("dc:creator")
        metadataElem.appendChild(authorElem)
        authorElem.setAttribute("opf:role", "aut")
        authorElem.appendChild(xml.createTextNode(unicode(bookinfo.author)))

        # /package/metadata/type
        if bookinfo.category:
            typeElem = xml.createElement("dc:type")
            metadataElem.appendChild(typeElem)
            typeElem.appendChild(xml.createTextNode(unicode(bookinfo.category)))

        # /package/metadata/identifier
        identifierElem = xml.createElement("dc:identifier")
        identifierElem.setAttribute("opf:scheme", "uuid")
        identifierElem.setAttribute("id", UID_ELEM_ID)
        metadataElem.appendChild(identifierElem)
        identifierElem.appendChild(xml.createTextNode(unicode(identifier)))

        # /package/metadata/identifier for ISBN
        if bookinfo.isbn:
            identifierElem = xml.createElement("dc:identifier")
            identifierElem.setAttribute("opf:scheme", "ISBN")
            metadataElem.appendChild(identifierElem)
            identifierElem.appendChild(xml.createTextNode(unicode(bookinfo.isbn)))

        # /package/metadata/language
        languageElem = xml.createElement("dc:language")
        metadataElem.appendChild(languageElem)
        languageElem.appendChild(xml.createTextNode("zh-CN"))

        # /package/metadata/publish_date
        if bookinfo.publish_date:
            dateElem = xml.createElement("dc:date")
            dateElem.setAttribute("opf:event", "publication")
            metadataElem.appendChild(dateElem)
            dateElem.appendChild(xml.createTextNode(unicode(bookinfo.publish_date)))

        # /package/metadata/meta[cover]
        if bookinfo.cover:
            coverElem = xml.createElement("meta")
            coverElem.setAttribute("name", "cover")
            coverElem.setAttribute("content", unicode(bookinfo.cover.id()))
            metadataElem.appendChild(coverElem)

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

        for file in filelist:
            if re.match(u".*\.x?html?", file["path"]):
                itemrefElem = xml.createElement("itemref")
                itemrefElem.setAttribute("idref", unicode(file["id"]))
                spineElem.appendChild(itemrefElem)

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
            logging.debug(u"    Adding {0}".format(file["path"]))
            outputter.add_file(os.path.join(CONTENT_DIR, file["path"]), file["content"])
            count += 1

        logging.info(u"    Total {0} files added".format(count))

    def convert(self, outputter, bookinfo):
        identifier = unicode(uuid.uuid4())

        logging.info(u"Generating related files...")

        logging.info(u"  Generating content files ...")

        memOutputter = MemOutputter()
        htmlconverter = HtmlConverter(options, EPUB_STYLE)
        htmlconverter.convert(memOutputter, bookinfo)

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
        ncx = self.generate_ncx(bookinfo, identifier)

        logging.info(u"  Generating opf file ...")
        opf = self.generate_opf(bookinfo, identifier, memOutputter.files)

        self.build_epub(outputter, opf, ncx, memOutputter.files)

        logging.info(u"  EPUB generated.")
# }}}

#   {{{ -- TxtConverter
class TxtConverter(object):
    def __init__(self, filename):
        super(TxtConverter, self).__init__()
        self.filename = filename

    def convert(self, outputter, bookinfo):
        def convert_txt(txtlines, lines):
            if not lines:
                return

            for line in lines:
                if isinstance(line, basestring):
                    txtlines.append(line)
                elif isinstance(line, Section):
                    txtlines.append(line.title)
                elif isinstance(line, LineContainer):
                    convert_txt(txtlines, line.lines)

        def convert_chapter(txtlines, chapter):
            txtlines.append(u"")
            txtlines.append(chapter.title)
            if chapter.author:
                txtlines.append(chapter.author)

            txtlines.append(u"")

            if chapter.intro:
                convert_txt(txtlines, chapter.intro)
                txtlines.append(u"")

            convert_txt(txtlines, chapter.content)

            for c in chapter.subchapters:
                convert_chapter(txtlines, c)

        txtlines = list()
        txtlines.append(bookinfo.title)
        txtlines.append(bookinfo.author)

        for chapter in bookinfo.chapters:
            convert_chapter(txtlines, chapter)

        outputter.add_file(self.filename, u"\n".join(txtlines).encode(options.encoding))

#   }}}

# }}}

# {{{ Outputters
#   {{{ -- Outputter
class Outputter(object):
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

#   {{{ -- MemOutputter
class MemOutputter(Outputter):
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

#   {{{ -- FileSysOutputter
class FileSysOutputter(Outputter):
    def add_file(self, path, content, **properties):
        with open(path, 'w+b') as f:
            f.write(content)
#   }}}

#   {{{ -- ZipOutputter
class ZipOutputter(Outputter):
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
        info.date_time = localtime(time())[:6]
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
def convert_book(path):
    def chapters_normalize(chapters, level, prefix):
        i = 1
        for c in chapters:
            c.id  = prefix + str(i)
            c.level = level

            if c.subchapters:
                chapters_normalize(c.subchapters, level + 1, c.id + "_")

            i += 1

    # {{{ get_suitable_inputter
    def get_suitable_inputter(path):
        inputter = None
        if re.match(r"https?://", path):
            inputter = UrlInputter(path)
        elif os.path.isfile(path) and os.path.splitext(path)[1].lower() == ".chm":
            try:
                chmlib

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

    # {{{ Parse book
    def parse_book(inputter):
        bookinfo = None

        logging.info(u"Parsing book '{0}'...".format(path))

        try:
            bookinfo = Parser.parse_book(inputter)
        except NotParseableError as e:
            logging.error(u"  Error: Don't know how to parse '{0}'".format(path))
            logging.error(e.value)
            raise

        chapters_normalize(bookinfo.chapters, 1, u"chapter_")

        (bookinfo.title, bookinfo.author) = parse_filename(
            path, 
            options.title if options.title else bookinfo.title, 
            options.author if options.author else bookinfo.author)

        bookinfo.category = options.category if options.category else bookinfo.category
        bookinfo.cover = cover if cover else bookinfo.cover

        # 非离线模式，有标题，无作者或无分类时到网上搜索作者及分类信息
        if not options.offline and bookinfo.title and (not bookinfo.author or not bookinfo.category):
            logging.info(u"Searching book information from internet...")

            (title, author, l1cat, l2cat) = get_book_category(bookinfo.title, bookinfo.author)

            if not bookinfo.author:
                bookinfo.author = author

            if not bookinfo.category:
                bookinfo.category = l1cat

        return bookinfo
    # }}}

    def print_book_info(bookinfo):
        logging.info(u"Book Info:")
        logging.info(u"  Book Title:  '{title}'".format(title=bookinfo.title))
        logging.info(u"  Book Author: '{author}'".format(author=bookinfo.author))
        logging.info(u"  Book Category: '{category}'".format(category=bookinfo.category))

        if bookinfo.cover:
            logging.info(u"  Cover: Yes")
        else:
            logging.info(u"  Cover: None")

    # {{{ Environments/Options verification
    cover = None
    if options.cover:
        if os.path.exists(options.cover):
            cover = SingleImg(options.cover)
        else:
            logging.error(u"  Error: Cover file '{0}' not found".format(options.cover))
            return 6
    # }}}

    inputter = get_suitable_inputter(path)
    with inputter:
        bookinfo = parse_book(inputter)

        print_book_info(bookinfo)

        # {{{ Convert book
        if options.output: 
            bookfilename = options.output
        else:
            bookfilename = book_file_name(bookinfo.title, bookinfo.author, u".epub")

        if os.path.splitext(bookfilename)[1].lower() == u".txt":
            with FileSysOutputter() as outputter:
                converter = TxtConverter(bookfilename)
                converter.convert(outputter, bookinfo)
        else:
            converter = EpubConverter(options)
            with ZipOutputter(FileSysOutputter(), bookfilename) as outputter:
                converter.convert(outputter, bookinfo)

        logging.info(u"Saved EPUB to {0}".format(bookfilename))
        # }}}

    return 0
# }}}

# {{{ main
if __name__ == "__main__":
    sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout)
    sys.stderr = codecs.getwriter(locale.getpreferredencoding())(sys.stderr)

    optparser = optparse.OptionParser(
        usage="%prog [options] <chm>", 
        description="""\
    Convert chm books into epub format.""",
        version=VERSION)

    optparser.add_option('-t', '--title',   action="store", type="string", dest="title", help="Book title. If omit, guess from filename")
    optparser.add_option('-a', '--author',  action="store", type="string", dest="author", help="Book author. If omit, guess from filename")
    optparser.add_option('-o', '--ouput',   action="store", type="string", dest="output", help="Ouput filename. If omit, <filename>-<author>.epub")
    optparser.add_option('-C', '--category',  action="store", type="string", dest="category", help="Book category. If omit, discover from web search")
    optparser.add_option('-e', '--encoding',  action="store", type="string", dest="encoding", default=locale.getpreferredencoding(), help="Default encoding for Txt output. Defaults to current locale (%default)")
    optparser.add_option('-p', '--parse-filename',    action="store_true", dest="parse_filename", default=False, help="Parse title/author from filename, don't convert.")
    optparser.add_option('-O', '--offline', action="store_true", dest="offline", default=False, help="Don't lookup author/category from web search.")
    optparser.add_option('-c', '--cover',   action="store", type="string", dest="cover", default="", help="Book cover image.")
    optparser.add_option('-k', '--keep',    action="store_true", dest="keep", default=False, help="Keep intermediate files.")
    optparser.add_option('-R', '--no-rearrange-toc',    action="store_false", dest="rearrange_toc", default=True, help="Rearrange TOC to avoid too much items in a level.")
    optparser.add_option('-v', '--verbose', action="store_true", dest="verbose", default=False, help="Be moderatery verbose")
    optparser.add_option('-s', '--silent',  action="store_true", dest="silent", default=False, help="Only show warning and errors")
    optparser.add_option('-n', '--nest-directory',  action="store_true", dest="nestdir", default=False, help="Create one sub directory for every chapte to avoid too much files in a single directory.")

    (options, args) = optparser.parse_args()

    for k in vars(options):
        if isinstance(getattr(options, k), str):
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

    if options.silent:
        logging.basicConfig(level=logging.WARNING)
    elif options.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    filename = args[0]
    
    if options.parse_filename:
    # 非离线模式，有标题，无作者或无分类时到网上搜索作者及分类信息
        l1cat = options.category
        l2cat = ""
        (title, author) = parse_filename(filename, options.title, options.author)

        if not options.offline and title and (not author or not l1cat):
            (title, author, l1cat, l2cat) = get_book_category(title, author)

        print u"{l1cat}\t{l2cat}\t{title}\t{author}".format(title=title, author=author, l1cat=l1cat, l2cat=l2cat)

        sys.exit(0)
    else:
        sys.exit(convert_book(filename))
# }}}
    
