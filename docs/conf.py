# Ensure we get the local copy of tornado instead of what's on the standard path
import os
import sys
sys.path.insert(0, os.path.abspath(".."))
import tornado

master_doc = "index"

project = "Tornado"
copyright = "2011, Facebook"

version = release = tornado.version

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    ]

primary_domain = 'py'
default_role = 'py:obj'

autodoc_member_order = "bysource"
autoclass_content = "both"

# Without this line sphinx includes a copy of object.__init__'s docstring
# on any class that doesn't define __init__.
# https://bitbucket.org/birkenfeld/sphinx/issue/1337/autoclass_content-both-uses-object__init__
autodoc_docstring_signature = False

coverage_skip_undoc_in_source = True
coverage_ignore_modules = [
    "tornado.platform.asyncio",
    "tornado.platform.twisted",
    ]
# I wish this could go in a per-module file...
coverage_ignore_classes = [
    # tornado.concurrent
    "TracebackFuture",

    # tornado.gen
    "Multi",
    "Runner",

    # tornado.ioloop
    "PollIOLoop",

    # tornado.web
    "ChunkedTransferEncoding",
    "GZipContentEncoding",
    "OutputTransform",
    "TemplateModule",
    "url",

    # tornado.websocket
    "WebSocketProtocol",
    "WebSocketProtocol13",
    "WebSocketProtocol76",
    ]

coverage_ignore_functions = [
    # various modules
    "doctests",
    "main",
]

html_static_path = ['tornado.css']
html_theme = 'default'
html_style = "tornado.css"
highlight_language = "none"
html_theme_options = dict(
    footerbgcolor="#fff",
    footertextcolor="#000",
    sidebarbgcolor="#fff",
    #sidebarbtncolor
    sidebartextcolor="#4d8cbf",
    sidebarlinkcolor="#216093",
    relbarbgcolor="#fff",
    relbartextcolor="#000",
    relbarlinkcolor="#216093",
    bgcolor="#fff",
    textcolor="#000",
    linkcolor="#216093",
    visitedlinkcolor="#216093",
    headbgcolor="#fff",
    headtextcolor="#4d8cbf",
    codebgcolor="#fff",
    codetextcolor="#060",
    bodyfont="Georgia, serif",
    headfont="Calibri, sans-serif",
    stickysidebar=True,
    )
html_favicon = 'favicon.ico'

latex_documents = [
    ('documentation', 'tornado.tex', 'Tornado Documentation', 'Facebook', 'manual', False),
    ]

# HACK: sphinx has limited support for substitutions with the |version|
# variable, but there doesn't appear to be any way to use this in a link
# target.
# http://stackoverflow.com/questions/1227037/substitutions-inside-links-in-rest-sphinx
# The extlink extension can be used to do link substitutions, but it requires a
# portion of the url to be literally contained in the document.  Therefore,
# this link must be referenced as :current_tarball:`z`
extlinks = {
    'current_tarball': (
'https://pypi.python.org/packages/source/t/tornado/tornado-%s.tar.g%%s' % version,
        'tornado-%s.tar.g' % version),
    }

intersphinx_mapping = {
    'python': ('http://python.readthedocs.org/en/latest/', None),
    }
