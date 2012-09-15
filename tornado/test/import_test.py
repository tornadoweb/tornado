from __future__ import absolute_import, division, with_statement
import unittest


class ImportTest(unittest.TestCase):
    def test_import_everything(self):
        # Some of our modules are not otherwise tested.  Import them
        # all (unless they have external dependencies) here to at
        # least ensure that there are no syntax errors.
        from .. import auth
        from .. import autoreload
        # from .. import curl_httpclient  # depends on pycurl
        # from .. import database  # depends on MySQLdb
        from .. import escape
        from .. import httpclient
        from .. import httpserver
        from .. import httputil
        from .. import ioloop
        from .. import iostream
        from .. import locale
        from .. import options
        from .. import netutil
        # from .. import platform.twisted # depends on twisted
        from .. import process
        from .. import simple_httpclient
        from .. import stack_context
        from .. import template
        from .. import testing
        from .. import util
        from .. import web
        from .. import websocket
        from .. import wsgi

    # for modules with dependencies, if those dependencies can be loaded,
    # load them too.

    def test_import_pycurl(self):
        try:
            import pycurl
        except ImportError:
            pass
        else:
            from .. import curl_httpclient

    def test_import_mysqldb(self):
        try:
            import MySQLdb
        except ImportError:
            pass
        else:
            from .. import database

    def test_import_twisted(self):
        try:
            import twisted
        except ImportError:
            pass
        else:
            from ..platform import twisted
