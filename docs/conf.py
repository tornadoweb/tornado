# Ensure we get the local copy of tornado instead of what's on the standard path
import os
import sys
import time
sys.path.insert(0, os.path.abspath(".."))
import tornado

master_doc = "index"

project = "Tornado"
copyright = "2009-%s, The Tornado Authors" % time.strftime("%Y")

version = release = tornado.version

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
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
    "tornado.platform.caresresolver",
    "tornado.platform.twisted",
    ]
# I wish this could go in a per-module file...
coverage_ignore_classes = [
    # tornado.concurrent
    "TracebackFuture",

    # tornado.gen
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

    # tornado.escape
    # parse_qs_bytes should probably be documented but it's complicated by
    # having different implementations between py2 and py3.
    "parse_qs_bytes",
]

html_favicon = 'favicon.ico'

latex_documents = [
    ('index', 'tornado.tex', 'Tornado Documentation', 'The Tornado Authors', 'manual', False),
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
    'python': ('https://docs.python.org/3.5/', None),
    }

on_rtd = os.environ.get('READTHEDOCS', None) == 'True'

# On RTD we can't import sphinx_rtd_theme, but it will be applied by
# default anyway.  This block will use the same theme when building locally
# as on RTD.
if not on_rtd:
    import sphinx_rtd_theme
    html_theme = 'sphinx_rtd_theme'
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
