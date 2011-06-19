# Ensure we get the local copy of tornado instead of what's on the standard path
import os
import sys
sys.path.insert(0, os.path.abspath("../.."))
import tornado

# For our version of sphinx_coverage.py.  The version in sphinx 1.0.7
# has too many false positives; this version comes from upstream HG.
sys.path.append(os.path.abspath("."))

master_doc = "index"

project = "Tornado"
copyright = "2011, Facebook"

version = release = tornado.version

extensions = ["sphinx.ext.autodoc", "sphinx_coverage", "sphinx.ext.viewcode"]

primary_domain = 'py'
default_role = 'py:obj'

autodoc_member_order = "bysource"
autoclass_content = "both"

coverage_skip_undoc_in_source = True
# I wish this could go in a per-module file...
coverage_ignore_classes = [
    # tornado.web
    "ChunkedTransferEncoding",
    "GZipContentEncoding",
    "OutputTransform",
    "TemplateModule",
    "url",
    ]

coverage_ignore_functions = [
    # various modules
    "doctests",
    "main",
]
    
html_static_path = [os.path.abspath("../static")]
html_style = "sphinx.css"
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
