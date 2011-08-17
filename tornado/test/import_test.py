import unittest

class ImportTest(unittest.TestCase):
    def test_import_everything(self):
        # Some of our modules are not otherwise tested.  Import them
        # all (unless they have external dependencies) here to at
        # least ensure that there are no syntax errors.
        import tornado.auth
        import tornado.autoreload
        # import tornado.curl_httpclient  # depends on pycurl
        # import tornado.database  # depends on MySQLdb
        import tornado.escape
        import tornado.httpclient
        import tornado.httpserver
        import tornado.httputil
        import tornado.ioloop
        import tornado.iostream
        import tornado.locale
        import tornado.options
        import tornado.netutil
        # import tornado.platform.twisted # depends on twisted
        import tornado.process
        import tornado.simple_httpclient
        import tornado.stack_context
        import tornado.template
        import tornado.testing
        import tornado.util
        import tornado.web
        import tornado.websocket
        import tornado.wsgi

    # for modules with dependencies, if those dependencies can be loaded,
    # load them too.

    def test_import_pycurl(self):
        try:
            import pycurl
        except ImportError:
            pass
        else:
            import tornado.curl_httpclient

    def test_import_mysqldb(self):
        try:
            import MySQLdb
        except ImportError:
            pass
        else:
            import tornado.database

    def test_import_twisted(self):
        try:
            import twisted
        except ImportError:
            pass
        else:
            import tornado.platform.twisted
