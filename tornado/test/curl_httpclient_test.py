from __future__ import absolute_import, division, print_function, with_statement
from tornado.httpclient import HTTPRequest
from tornado.stack_context import ExceptionStackContext
from tornado.testing import AsyncHTTPTestCase
from tornado.test import httpclient_test
from tornado.test.util import unittest
from tornado.web import Application

try:
    import pycurl
except ImportError:
    pycurl = None

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(io_loop=self.io_loop)
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientTestCase(AsyncHTTPTestCase):
    def setUp(self):
        super(CurlHTTPClientTestCase, self).setUp()
        self.http_client = CurlAsyncHTTPClient(self.io_loop)

    def get_app(self):
        return Application([])

    def test_prepare_curl_callback_stack_context(self):
        exc_info = []

        def error_handler(typ, value, tb):
            exc_info.append((typ, value, tb))
            self.stop()
            return True

        with ExceptionStackContext(error_handler):
            request = HTTPRequest(self.get_url('/'),
                                  prepare_curl_callback=lambda curl: 1 / 0)
        self.http_client.fetch(request, callback=self.stop)
        self.wait()
        self.assertEqual(1, len(exc_info))
        self.assertIs(exc_info[0][0], ZeroDivisionError)
