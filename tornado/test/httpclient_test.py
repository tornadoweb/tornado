#!/usr/bin/env python

from __future__ import with_statement

import base64
import binascii
import gzip
import logging
import socket

from contextlib import closing
from tornado.escape import utf8
from tornado.httpclient import AsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, get_unused_port
from tornado.util import b, bytes_type
from tornado.web import Application, RequestHandler, asynchronous, url

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

class CountdownHandler(RequestHandler):
    def get(self, count):
        count = int(count)
        if count > 0:
            self.redirect(self.reverse_url("countdown", count - 1))
        else:
            self.write("Zero")

class EchoPostHandler(RequestHandler):
    def post(self):
        self.write(self.request.body)

# These tests end up getting run redundantly: once here with the default
# HTTPClient implementation, and then again in each implementation's own
# test suite.
class HTTPClientCommonTestCase(AsyncHTTPTestCase, LogTrapTestCase):
    def get_http_client(self):
        """Returns AsyncHTTPClient instance.  May be overridden in subclass."""
        return AsyncHTTPClient(io_loop=self.io_loop)

    def get_app(self):
        return Application([
            url("/hello", HelloWorldHandler),
            url("/post", PostHandler),
            url("/chunk", ChunkHandler),
            url("/auth", AuthHandler),
            url("/hang", HangHandler),
            url("/countdown/([0-9]+)", CountdownHandler, name="countdown"),
            url("/echopost", EchoPostHandler),
            ], gzip=True)

    def setUp(self):
        super(HTTPClientCommonTestCase, self).setUp()
        # replace the client defined in the parent class
        self.http_client = self.get_http_client()

    def test_hello_world(self):
        response = self.fetch("/hello")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain")
        self.assertEqual(response.body, b("Hello world!"))

        response = self.fetch("/hello?name=Ben")
        self.assertEqual(response.body, b("Hello Ben!"))

    def test_streaming_callback(self):
        # streaming_callback is also tested in test_chunked
        chunks = []
        response = self.fetch("/hello",
                              streaming_callback=chunks.append)
        # with streaming_callback, data goes to the callback and not response.body
        self.assertEqual(chunks, [b("Hello world!")])
        self.assertFalse(response.body)

    def test_post(self):
        response = self.fetch("/post", method="POST",
                              body="arg1=foo&arg2=bar")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, b("Post arg1: foo, arg2: bar"))

    def test_chunked(self):
        response = self.fetch("/chunk")
        self.assertEqual(response.body, b("asdfqwer"))

        chunks = []
        response = self.fetch("/chunk",
                              streaming_callback=chunks.append)
        self.assertEqual(chunks, [b("asdf"), b("qwer")])
        self.assertFalse(response.body)

    def test_basic_auth(self):
        self.assertEqual(self.fetch("/auth", auth_username="Aladdin",
                                    auth_password="open sesame").body,
                         b("Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=="))

    def test_gzip(self):
        # All the tests in this file should be using gzip, but this test
        # ensures that it is in fact getting compressed.
        # Setting Accept-Encoding manually bypasses the client's
        # decompression so we can see the raw data.
        response = self.fetch("/chunk", use_gzip=False,
                              headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertNotEqual(response.body, b("asdfqwer"))
        # Our test data gets bigger when gzipped.  Oops.  :)
        self.assertEqual(len(response.body), 34)
        f = gzip.GzipFile(mode="r", fileobj=response.buffer)
        self.assertEqual(f.read(), b("asdfqwer"))

    def test_connect_timeout(self):
        # create a socket and bind it to a port, but don't
        # call accept so the connection will timeout.
        #get_unused_port()
        port = get_unused_port()

        with closing(socket.socket()) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', port))
            sock.listen(1)
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

    def test_follow_redirect(self):
        response = self.fetch("/countdown/2", follow_redirects=False)
        self.assertEqual(302, response.code)
        self.assertTrue(response.headers["Location"].endswith("/countdown/1"))

        response = self.fetch("/countdown/2")
        self.assertEqual(200, response.code)
        self.assertTrue(response.effective_url.endswith("/countdown/0"))
        self.assertEqual(b("Zero"), response.body)

    def test_max_redirects(self):
        response = self.fetch("/countdown/5", max_redirects=3)
        self.assertEqual(302, response.code)
        # We requested 5, followed three redirects for 4, 3, 2, then the last
        # unfollowed redirect is to 1.
        self.assertTrue(response.request.url.endswith("/countdown/5"))
        self.assertTrue(response.effective_url.endswith("/countdown/2"))
        self.assertTrue(response.headers["Location"].endswith("/countdown/1"))

    def test_credentials_in_url(self):
        url = self.get_url("/auth").replace("http://", "http://me:secret@")
        self.http_client.fetch(url, self.stop)
        response = self.wait()
        self.assertEqual(b("Basic ") + base64.b64encode(b("me:secret")),
                         response.body)

    def test_body_encoding(self):
        unicode_body = u"\xe9"
        byte_body = binascii.a2b_hex(b("e9"))

        # unicode string in body gets converted to utf8
        response = self.fetch("/echopost", method="POST", body=unicode_body,
                              headers={"Content-Type": "application/blah"})
        self.assertEqual(response.headers["Content-Length"], "2")
        self.assertEqual(response.body, utf8(unicode_body))

        # byte strings pass through directly
        response = self.fetch("/echopost", method="POST",
                              body=byte_body,
                              headers={"Content-Type": "application/blah"})
        self.assertEqual(response.headers["Content-Length"], "1")
        self.assertEqual(response.body, byte_body)

        # Mixing unicode in headers and byte string bodies shouldn't
        # break anything
        response = self.fetch("/echopost", method="POST", body=byte_body,
                              headers={"Content-Type": "application/blah"},
                              user_agent=u"foo")
        self.assertEqual(response.headers["Content-Length"], "1")
        self.assertEqual(response.body, byte_body)

    def test_ipv6(self):
        url = self.get_url("/hello").replace("localhost", "[::1]")

        # ipv6 is currently disabled by default and must be explicitly requested
        self.http_client.fetch(url, self.stop)
        response = self.wait()
        self.assertEqual(response.code, 599)

        self.http_client.fetch(url, self.stop, allow_ipv6=True)
        response = self.wait()
        self.assertEqual(response.body, b("Hello world!"))

    def test_types(self):
        response = self.fetch("/hello")
        self.assertEqual(type(response.body), bytes_type)
        self.assertEqual(type(response.headers["Content-Type"]), str)
        self.assertEqual(type(response.code), int)
        self.assertEqual(type(response.effective_url), str)
