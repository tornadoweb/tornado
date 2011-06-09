# Ensure we get the local copy of tornado instead of what's on the standard path
import os
import sys
sys.path.insert(0, os.path.abspath("../.."))
import tornado

print tornado.__file__

master_doc = "index"

project = "Tornado"
copyright = "2011, Facebook"

import tornado
version = release = tornado.version

extensions = ["sphinx.ext.autodoc"]

autodoc_member_order = "bysource"
autodoc_default_flags = ["members", "undoc-members"]
