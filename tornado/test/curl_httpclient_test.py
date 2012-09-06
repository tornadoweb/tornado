from __future__ import absolute_import, division, with_statement
from tornado.test import httpclient_test
from tornado.test.util import unittest

try:
    import pycurl
except ImportError:
    pycurl = None

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient


class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(io_loop=self.io_loop)
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client
CurlHTTPClientCommonTestCase = unittest.skipIf(pycurl is None,
                                               "pycurl module not present")(
    CurlHTTPClientCommonTestCase)
