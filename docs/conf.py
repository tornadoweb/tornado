import os
import sphinx.errors
import sys

# Ensure we get the local copy of tornado instead of what's on the standard path
sys.path.insert(0, os.path.abspath(".."))
import tornado

master_doc = "index"

project = "Tornado"
copyright = "The Tornado Authors"

version = release = tornado.version

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinxcontrib.asyncio",
]

primary_domain = "py"
default_role = "py:obj"

autodoc_member_order = "bysource"
autoclass_content = "both"
autodoc_inherit_docstrings = False

# Without this line sphinx includes a copy of object.__init__'s docstring
# on any class that doesn't define __init__.
# https://bitbucket.org/birkenfeld/sphinx/issue/1337/autoclass_content-both-uses-object__init__
autodoc_docstring_signature = False

coverage_skip_undoc_in_source = True
coverage_ignore_modules = [
    "tornado.platform.asyncio",
    "tornado.platform.caresresolver",
    "tornado.platform.twisted",
    "tornado.simple_httpclient",
]
# I wish this could go in a per-module file...
coverage_ignore_classes = [
    # tornado.gen
    "Runner",
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
    # tornado.gen
    "Multi",
]

html_favicon = "favicon.ico"

latex_documents = [
    (
        "index",
        "tornado.tex",
        "Tornado Documentation",
        "The Tornado Authors",
        "manual",
        False,
    )
]

intersphinx_mapping = {"python": ("https://docs.python.org/3/", None)}

on_rtd = os.environ.get("READTHEDOCS", None) == "True"

# On RTD we can't import sphinx_rtd_theme, but it will be applied by
# default anyway.  This block will use the same theme when building locally
# as on RTD.
if not on_rtd:
    import sphinx_rtd_theme

    html_theme = "sphinx_rtd_theme"
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

# Suppress warnings about "class reference target not found" for these types.
# In most cases these types come from type annotations and are for mypy's use.
missing_references = {
    # Generic type variables; nothing to link to.
    "_IOStreamType",
    "_S",
    "_T",
    # Standard library types which are defined in one module and documented
    # in another. We could probably remap them to their proper location if
    # there's not an upstream fix in python and/or sphinx.
    "_asyncio.Future",
    "_io.BytesIO",
    "asyncio.AbstractEventLoop.run_forever",
    "asyncio.events.AbstractEventLoop",
    "concurrent.futures._base.Executor",
    "concurrent.futures._base.Future",
    "futures.Future",
    "socket.socket",
    "TextIO",
    # Other stuff. I'm not sure why some of these are showing up, but
    # I'm just listing everything here to avoid blocking the upgrade of sphinx.
    "Future",
    "httputil.HTTPServerConnectionDelegate",
    "httputil.HTTPServerRequest",
    "OutputTransform",
    "Pattern",
    "RAISE",
    "Rule",
    "tornado.ioloop._Selectable",
    "tornado.locks._ReleasingContextManager",
    "tornado.options._Mockable",
    "tornado.web._ArgDefaultMarker",
    "tornado.web._HandlerDelegate",
    "traceback",
    "WSGIAppType",
    "Yieldable",
}


def missing_reference_handler(app, env, node, contnode):
    if node["reftarget"] in missing_references:
        raise sphinx.errors.NoUri


def setup(app):
    app.connect("missing-reference", missing_reference_handler)
