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

extensions = ["sphinx.ext.autodoc", "sphinx_coverage"]

autodoc_member_order = "bysource"

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
    
