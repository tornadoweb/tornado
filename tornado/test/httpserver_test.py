#!/usr/bin/env python

from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.web import Application, RequestHandler
import os
import pycurl
import re
import unittest
import urllib

try:
    import ssl
except ImportError:
    ssl = None

class HelloWorldRequestHandler(RequestHandler):
    def get(self):
        self.finish("Hello world")

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

    def test_ssl(self):
        def disable_cert_check(curl):
            # Our certificate was not signed by a CA, so don't check it
            curl.setopt(pycurl.SSL_VERIFYPEER, 0)
        self.http_client.fetch(self.get_url('/').replace('http', 'https'),
                               self.stop,
                               prepare_curl_callback=disable_cert_check)
        response = self.wait()
        self.assertEqual(response.body, "Hello world")

if (ssl is None or
    (pycurl.version_info()[5].startswith('GnuTLS') and
     pycurl.version_info()[2] < 0x71400)):
    # Don't try to run ssl tests if we don't have the ssl module (python 2.5).
    # Additionally, when libcurl (< 7.21.0) is compiled against gnutls
    # instead of openssl (which is the default on at least some versions of
    # ubuntu), libcurl does the ssl handshake in blocking mode.  That will
    # cause this test to deadlock as the blocking network ops happen in
    # the same IOLoop as the server.
    del SSLTest
