#!/usr/bin/env python

from __future__ import with_statement

import collections
import gzip
import logging
import socket

from contextlib import closing
from tornado.ioloop import IOLoop
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, get_unused_port
from tornado.web import Application, RequestHandler, asynchronous

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

class HangHandler(RequestHandler):
    @asynchronous
    def get(self):
        pass

class TriggerHandler(RequestHandler):
    def initialize(self, queue, wake_callback):
        self.queue = queue
        self.wake_callback = wake_callback

    @asynchronous
    def get(self):
        logging.info("queuing trigger")
        self.queue.append(self.finish)
        self.wake_callback()

class SimpleHTTPClientTestCase(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        # callable objects to finish pending /trigger requests
        self.triggers = collections.deque()
        return Application([
            ("/hello", HelloWorldHandler),
            ("/post", PostHandler),
            ("/chunk", ChunkHandler),
            ("/auth", AuthHandler),
            ("/hang", HangHandler),
            ("/trigger", TriggerHandler, dict(queue=self.triggers,
                                              wake_callback=self.stop)),
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

    def test_connect_timeout(self):
        # create a socket and bind it to a port, but don't
        # call accept so the connection will timeout.
        #get_unused_port()
        port = get_unused_port()

        with closing(socket.socket()) as sock:
            sock.bind(('', port))
            self.http_client.fetch("http://localhost:%d/" % port,
                                   self.stop,
                                   connect_timeout=0.1)
            response = self.wait()
            self.assertEqual(response.code, 599)
            self.assertEqual(str(response.error), "HTTP 599: Timeout")

    def test_request_timeout(self):
        response = self.fetch('/hang', request_timeout=0.1)
        self.assertEqual(response.code, 599)
        self.assertEqual(str(response.error), "HTTP 599: Timeout")

    def test_singleton(self):
        # Class "constructor" reuses objects on the same IOLoop
        self.assertTrue(SimpleAsyncHTTPClient(self.io_loop) is
                        SimpleAsyncHTTPClient(self.io_loop))
        # unless force_instance is used
        self.assertTrue(SimpleAsyncHTTPClient(self.io_loop) is not
                        SimpleAsyncHTTPClient(self.io_loop,
                                              force_instance=True))
        # different IOLoops use different objects
        io_loop2 = IOLoop()
        self.assertTrue(SimpleAsyncHTTPClient(self.io_loop) is not
                        SimpleAsyncHTTPClient(io_loop2))

    def test_connection_limit(self):
        client = SimpleAsyncHTTPClient(self.io_loop, max_clients=2,
                                       force_instance=True)
        self.assertEqual(client.max_clients, 2)
        seen = []
        # Send 4 requests.  Two can be sent immediately, while the others
        # will be queued
        for i in range(4):
            client.fetch(self.get_url("/trigger"),
                         lambda response, i=i: (seen.append(i), self.stop()))
        self.wait(condition=lambda: len(self.triggers) == 2)
        self.assertEqual(len(client.queue), 2)

        # Finish the first two requests and let the next two through
        self.triggers.popleft()()
        self.triggers.popleft()()
        self.wait(condition=lambda: (len(self.triggers) == 2 and
                                     len(seen) == 2))
        self.assertEqual(seen, [0, 1])
        self.assertEqual(len(client.queue), 0)

