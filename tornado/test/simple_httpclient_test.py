#!/usr/bin/env python

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

class SimpleHTTPClientTestCase(AsyncHTTPTestCase, LogTrapTestCase):
    def fetch(self, url, **kwargs):
        self.http_client.fetch(url, self.stop, **kwargs)
        return self.wait()

    def get_app(self):
        return Application([
            ("/hello", HelloWorldHandler),
            ("/post", PostHandler),
            ("/chunk", ChunkHandler),
            ])

    def setUp(self):
        super(SimpleHTTPClientTestCase, self).setUp()
        # replace the client defined in the parent class
        self.http_client = SimpleAsyncHTTPClient(io_loop=self.io_loop)

    def test_hello_world(self):
        response = self.fetch(self.get_url("/hello"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.body, "Hello world!")

        response = self.fetch(self.get_url("/hello?name=Ben"))
        self.assertEqual(response.body, "Hello Ben!")

    def test_streaming_callback(self):
        # streaming_callback is also tested in test_chunked
        chunks = []
        response = self.fetch(self.get_url("/hello"),
                              streaming_callback=chunks.append)
        # with streaming_callback, data goes to the callback and not response.body
        self.assertEqual(chunks, ["Hello world!"])
        self.assertFalse(response.body)

    def test_post(self):
        response = self.fetch(self.get_url("/post"), method="POST",
                              body="arg1=foo&arg2=bar")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, "Post arg1: foo, arg2: bar")

    def test_chunked(self):
        response = self.fetch(self.get_url("/chunk"))
        self.assertEqual(response.body, "asdfqwer")

        chunks = []
        response = self.fetch(self.get_url("/chunk"),
                              streaming_callback=chunks.append)
        self.assertEqual(chunks, ["asdf", "qwer"])
        self.assertFalse(response.body)
