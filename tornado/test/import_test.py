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
        import tornado.process
        import tornado.simple_httpclient
        import tornado.stack_context
        import tornado.template
        import tornado.testing
        import tornado.util
        import tornado.web
        import tornado.websocket
        import tornado.wsgi
