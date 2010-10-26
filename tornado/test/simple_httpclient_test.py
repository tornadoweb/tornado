#!/usr/bin/env python

import gzip
import logging

from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.web import Application, RequestHandler

class HelloWorldHandler(RequestHandler):
    def get(self):
        name = self.get_argument("name", "world")
        self.set_header("Content-Type", "text/plain")
        self.finish("Hello %s!" % name)

class PostHandler(RequestHandler):
    def post(self):
        self.finish("Post arg1: %s, arg2: %s" % (
            self.get_argument("arg1"), self.get_argument("arg2")))

class ChunkHandler(RequestHandler):
    def get(self):
        self.write("asdf")
        self.flush()
        self.write("qwer")

class AuthHandler(RequestHandler):
    def get(self):
        self.finish(self.request.headers["Authorization"])

class SimpleHTTPClientTestCase(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([
            ("/hello", HelloWorldHandler),
            ("/post", PostHandler),
            ("/chunk", ChunkHandler),
            ("/auth", AuthHandler),
            ], gzip=True)

    def setUp(self):
        super(SimpleHTTPClientTestCase, self).setUp()
        # replace the client defined in the parent class
        self.http_client = SimpleAsyncHTTPClient(io_loop=self.io_loop)

    def test_hello_world(self):
        response = self.fetch("/hello")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.body, "Hello world!")

        response = self.fetch("/hello?name=Ben")
        self.assertEqual(response.body, "Hello Ben!")

    def test_streaming_callback(self):
        # streaming_callback is also tested in test_chunked
        chunks = []
        response = self.fetch("/hello",
                              streaming_callback=chunks.append)
        # with streaming_callback, data goes to the callback and not response.body
        self.assertEqual(chunks, ["Hello world!"])
        self.assertFalse(response.body)

    def test_post(self):
        response = self.fetch("/post", method="POST",
                              body="arg1=foo&arg2=bar")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, "Post arg1: foo, arg2: bar")

    def test_chunked(self):
        response = self.fetch("/chunk")
        self.assertEqual(response.body, "asdfqwer")

        chunks = []
        response = self.fetch("/chunk",
                              streaming_callback=chunks.append)
        self.assertEqual(chunks, ["asdf", "qwer"])
        self.assertFalse(response.body)

    def test_basic_auth(self):
        self.assertEqual(self.fetch("/auth", auth_username="Aladdin",
                                    auth_password="open sesame").body,
                         "Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==")

    def test_gzip(self):
        # All the tests in this file should be using gzip, but this test
        # ensures that it is in fact getting compressed.
        # Setting Accept-Encoding manually bypasses the client's
        # decompression so we can see the raw data.
        response = self.fetch("/chunk", use_gzip=False,
                              headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertNotEqual(response.body, "asdfqwer")
        # Our test data gets bigger when gzipped.  Oops.  :)
        self.assertEqual(len(response.body), 34)
        f = gzip.GzipFile(mode="r", fileobj=response.buffer)
        self.assertEqual(f.read(), "asdfqwer")
