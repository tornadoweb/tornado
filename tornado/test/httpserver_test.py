#!/usr/bin/env python

from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.web import Application, RequestHandler
import os
try:
    import pycurl
except ImportError:
    pycurl = None
import re
import unittest
import urllib

try:
    import ssl
except ImportError:
    ssl = None

class HelloWorldRequestHandler(RequestHandler):
    def get(self):
        assert self.request.protocol == "https"
        self.finish("Hello world")

    def post(self):
        self.finish("Got %d bytes in POST" % len(self.request.body))

class SSLTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/', HelloWorldRequestHandler)])

    def get_httpserver_options(self):
        # Testing keys were generated with:
        # openssl req -new -keyout tornado/test/test.key -out tornado/test/test.crt -nodes -days 3650 -x509
        test_dir = os.path.dirname(__file__)
        return dict(ssl_options=dict(
                certfile=os.path.join(test_dir, 'test.crt'),
                keyfile=os.path.join(test_dir, 'test.key')))

    def fetch(self, path, **kwargs):
        def disable_cert_check(curl):
            # Our certificate was not signed by a CA, so don't check it
            curl.setopt(pycurl.SSL_VERIFYPEER, 0)
        self.http_client.fetch(self.get_url(path).replace('http', 'https'),
                               self.stop,
                               prepare_curl_callback=disable_cert_check,
                               **kwargs)
        return self.wait()

    def test_ssl(self):
        response = self.fetch('/')
        self.assertEqual(response.body, "Hello world")

    def test_large_post(self):
        response = self.fetch('/',
                              method='POST',
                              body='A'*5000)
        self.assertEqual(response.body, "Got 5000 bytes in POST")

if (ssl is None or pycurl is None or
    (pycurl.version_info()[5].startswith('GnuTLS') and
     pycurl.version_info()[2] < 0x71400)):
    # Don't try to run ssl tests if we don't have the ssl module (python 2.5).
    # Additionally, when libcurl (< 7.21.0) is compiled against gnutls
    # instead of openssl (which is the default on at least some versions of
    # ubuntu), libcurl does the ssl handshake in blocking mode.  That will
    # cause this test to deadlock as the blocking network ops happen in
    # the same IOLoop as the server.
    del SSLTest
