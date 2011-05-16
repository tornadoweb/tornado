#!/usr/bin/env python

from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.util import b
from tornado.web import Application, RequestHandler
import os
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
    def setUp(self):
        super(SSLTest, self).setUp()
        # Replace the client defined in the parent class.
        # Some versions of libcurl have deadlock bugs with ssl,
        # so always run these tests with SimpleAsyncHTTPClient.
        self.http_client = SimpleAsyncHTTPClient(io_loop=self.io_loop,
                                                 force_instance=True)

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
        self.http_client.fetch(self.get_url(path).replace('http', 'https'),
                               self.stop,
                               validate_cert=False,
                               **kwargs)
        return self.wait()

    def test_ssl(self):
        response = self.fetch('/')
        self.assertEqual(response.body, b("Hello world"))

    def test_large_post(self):
        response = self.fetch('/',
                              method='POST',
                              body='A'*5000)
        self.assertEqual(response.body, b("Got 5000 bytes in POST"))

    def test_non_ssl_request(self):
        # Make sure the server closes the connection when it gets a non-ssl
        # connection, rather than waiting for a timeout or otherwise
        # misbehaving.
        self.http_client.fetch(self.get_url("/"), self.stop,
                               request_timeout=3600,
                               connect_timeout=3600)
        response = self.wait()
        self.assertEqual(response.code, 599)

if ssl is None:
    del SSLTest
