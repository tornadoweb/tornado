from __future__ import absolute_import, division, print_function, with_statement

import collections
from contextlib import closing
import errno
import gzip
import logging
import os
import re
import socket
import sys

from tornado.httpclient import AsyncHTTPClient
from tornado.httputil import HTTPHeaders
from tornado.ioloop import IOLoop
from tornado.log import gen_log
from tornado.simple_httpclient import SimpleAsyncHTTPClient, _DEFAULT_CA_CERTS
from tornado.test.httpclient_test import ChunkHandler, CountdownHandler, HelloWorldHandler
from tornado.test import httpclient_test
from tornado.testing import AsyncHTTPTestCase, AsyncHTTPSTestCase, AsyncTestCase, bind_unused_port, ExpectLog
from tornado.test.util import unittest, skipOnTravis
from tornado.web import RequestHandler, Application, asynchronous, url


class SimpleHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = SimpleAsyncHTTPClient(io_loop=self.io_loop,
                                       force_instance=True)
        self.assertTrue(isinstance(client, SimpleAsyncHTTPClient))
        return client


class TriggerHandler(RequestHandler):
    def initialize(self, queue, wake_callback):
        self.queue = queue
        self.wake_callback = wake_callback

    @asynchronous
    def get(self):
        logging.debug("queuing trigger")
        self.queue.append(self.finish)
        if self.get_argument("wake", "true") == "true":
            self.wake_callback()


class HangHandler(RequestHandler):
    @asynchronous
    def get(self):
        pass


class ContentLengthHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Length", self.get_argument("value"))
        self.write("ok")


class HeadHandler(RequestHandler):
    def head(self):
        self.set_header("Content-Length", "7")


class OptionsHandler(RequestHandler):
    def options(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.write("ok")


class NoContentHandler(RequestHandler):
    def get(self):
        if self.get_argument("error", None):
            self.set_header("Content-Length", "7")
        self.set_status(204)


class SeeOtherPostHandler(RequestHandler):
    def post(self):
        redirect_code = int(self.request.body)
        assert redirect_code in (302, 303), "unexpected body %r" % self.request.body
        self.set_header("Location", "/see_other_get")
        self.set_status(redirect_code)


class SeeOtherGetHandler(RequestHandler):
    def get(self):
        if self.request.body:
            raise Exception("unexpected body %r" % self.request.body)
        self.write("ok")


class HostEchoHandler(RequestHandler):
    def get(self):
        self.write(self.request.headers["Host"])


class SimpleHTTPClientTestMixin(object):
    def get_app(self):
        # callable objects to finish pending /trigger requests
        self.triggers = collections.deque()
        return Application([
            url("/trigger", TriggerHandler, dict(queue=self.triggers,
                                                 wake_callback=self.stop)),
            url("/chunk", ChunkHandler),
            url("/countdown/([0-9]+)", CountdownHandler, name="countdown"),
            url("/hang", HangHandler),
            url("/hello", HelloWorldHandler),
            url("/content_length", ContentLengthHandler),
            url("/head", HeadHandler),
            url("/options", OptionsHandler),
            url("/no_content", NoContentHandler),
            url("/see_other_post", SeeOtherPostHandler),
            url("/see_other_get", SeeOtherGetHandler),
            url("/host_echo", HostEchoHandler),
        ], gzip=True)

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
        with closing(self.create_client(max_clients=2)) as client:
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
            self.assertEqual(set(seen), set([0, 1]))
            self.assertEqual(len(client.queue), 0)

            # Finish all the pending requests
            self.triggers.popleft()()
            self.triggers.popleft()()
            self.wait(condition=lambda: len(seen) == 4)
            self.assertEqual(set(seen), set([0, 1, 2, 3]))
            self.assertEqual(len(self.triggers), 0)

    def test_redirect_connection_limit(self):
        # following redirects should not consume additional connections
        with closing(self.create_client(max_clients=1)) as client:
            client.fetch(self.get_url('/countdown/3'), self.stop,
                         max_redirects=3)
            response = self.wait()
            response.rethrow()

    def test_default_certificates_exist(self):
        open(_DEFAULT_CA_CERTS).close()

    def test_gzip(self):
        # All the tests in this file should be using gzip, but this test
        # ensures that it is in fact getting compressed.
        # Setting Accept-Encoding manually bypasses the client's
        # decompression so we can see the raw data.
        response = self.fetch("/chunk", use_gzip=False,
                              headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertNotEqual(response.body, b"asdfqwer")
        # Our test data gets bigger when gzipped.  Oops.  :)
        self.assertEqual(len(response.body), 34)
        f = gzip.GzipFile(mode="r", fileobj=response.buffer)
        self.assertEqual(f.read(), b"asdfqwer")

    def test_max_redirects(self):
        response = self.fetch("/countdown/5", max_redirects=3)
        self.assertEqual(302, response.code)
        # We requested 5, followed three redirects for 4, 3, 2, then the last
        # unfollowed redirect is to 1.
        self.assertTrue(response.request.url.endswith("/countdown/5"))
        self.assertTrue(response.effective_url.endswith("/countdown/2"))
        self.assertTrue(response.headers["Location"].endswith("/countdown/1"))

    def test_header_reuse(self):
        # Apps may reuse a headers object if they are only passing in constant
        # headers like user-agent.  The header object should not be modified.
        headers = HTTPHeaders({'User-Agent': 'Foo'})
        self.fetch("/hello", headers=headers)
        self.assertEqual(list(headers.get_all()), [('User-Agent', 'Foo')])

    def test_see_other_redirect(self):
        for code in (302, 303):
            response = self.fetch("/see_other_post", method="POST", body="%d" % code)
            self.assertEqual(200, response.code)
            self.assertTrue(response.request.url.endswith("/see_other_post"))
            self.assertTrue(response.effective_url.endswith("/see_other_get"))
            # request is the original request, is a POST still
            self.assertEqual("POST", response.request.method)

    @skipOnTravis
    def test_request_timeout(self):
        response = self.fetch('/trigger?wake=false', request_timeout=0.1)
        self.assertEqual(response.code, 599)
        self.assertTrue(0.099 < response.request_time < 0.15, response.request_time)
        self.assertEqual(str(response.error), "HTTP 599: Timeout")
        # trigger the hanging request to let it clean up after itself
        self.triggers.popleft()()

    @unittest.skipIf(not socket.has_ipv6, 'ipv6 support not present')
    def test_ipv6(self):
        try:
            self.http_server.listen(self.get_http_port(), address='::1')
        except socket.gaierror as e:
            if e.args[0] == socket.EAI_ADDRFAMILY:
                # python supports ipv6, but it's not configured on the network
                # interface, so skip this test.
                return
            raise
        url = self.get_url("/hello").replace("localhost", "[::1]")

        # ipv6 is currently disabled by default and must be explicitly requested
        self.http_client.fetch(url, self.stop)
        response = self.wait()
        self.assertEqual(response.code, 599)

        self.http_client.fetch(url, self.stop, allow_ipv6=True)
        response = self.wait()
        self.assertEqual(response.body, b"Hello world!")

    def test_multiple_content_length_accepted(self):
        response = self.fetch("/content_length?value=2,2")
        self.assertEqual(response.body, b"ok")
        response = self.fetch("/content_length?value=2,%202,2")
        self.assertEqual(response.body, b"ok")

        response = self.fetch("/content_length?value=2,4")
        self.assertEqual(response.code, 599)
        response = self.fetch("/content_length?value=2,%202,3")
        self.assertEqual(response.code, 599)

    def test_head_request(self):
        response = self.fetch("/head", method="HEAD")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["content-length"], "7")
        self.assertFalse(response.body)

    def test_options_request(self):
        response = self.fetch("/options", method="OPTIONS")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["content-length"], "2")
        self.assertEqual(response.headers["access-control-allow-origin"], "*")
        self.assertEqual(response.body, b"ok")

    def test_no_content(self):
        response = self.fetch("/no_content")
        self.assertEqual(response.code, 204)
        # 204 status doesn't need a content-length, but tornado will
        # add a zero content-length anyway.
        self.assertEqual(response.headers["Content-length"], "0")

        # 204 status with non-zero content length is malformed
        response = self.fetch("/no_content?error=1")
        self.assertEqual(response.code, 599)

    def test_host_header(self):
        host_re = re.compile(b"^localhost:[0-9]+$")
        response = self.fetch("/host_echo")
        self.assertTrue(host_re.match(response.body))

        url = self.get_url("/host_echo").replace("http://", "http://me:secret@")
        self.http_client.fetch(url, self.stop)
        response = self.wait()
        self.assertTrue(host_re.match(response.body), response.body)

    def test_connection_refused(self):
        server_socket, port = bind_unused_port()
        server_socket.close()
        with ExpectLog(gen_log, ".*", required=False):
            self.http_client.fetch("http://localhost:%d/" % port, self.stop)
            response = self.wait()
        self.assertEqual(599, response.code)

        if sys.platform != 'cygwin':
            # cygwin returns EPERM instead of ECONNREFUSED here
            self.assertTrue(str(errno.ECONNREFUSED) in str(response.error),
                            response.error)
            # This is usually "Connection refused".
            # On windows, strerror is broken and returns "Unknown error".
            expected_message = os.strerror(errno.ECONNREFUSED)
            self.assertTrue(expected_message in str(response.error),
                            response.error)


class SimpleHTTPClientTestCase(SimpleHTTPClientTestMixin, AsyncHTTPTestCase):
    def setUp(self):
        super(SimpleHTTPClientTestCase, self).setUp()
        self.http_client = self.create_client()

    def create_client(self, **kwargs):
        return SimpleAsyncHTTPClient(self.io_loop, force_instance=True,
                                     **kwargs)


class SimpleHTTPSClientTestCase(SimpleHTTPClientTestMixin, AsyncHTTPSTestCase):
    def setUp(self):
        super(SimpleHTTPSClientTestCase, self).setUp()
        self.http_client = self.create_client()

    def create_client(self, **kwargs):
        return SimpleAsyncHTTPClient(self.io_loop, force_instance=True,
                                     defaults=dict(validate_cert=False),
                                     **kwargs)


class CreateAsyncHTTPClientTestCase(AsyncTestCase):
    def setUp(self):
        super(CreateAsyncHTTPClientTestCase, self).setUp()
        self.saved = AsyncHTTPClient._save_configuration()

    def tearDown(self):
        AsyncHTTPClient._restore_configuration(self.saved)
        super(CreateAsyncHTTPClientTestCase, self).tearDown()

    def test_max_clients(self):
        AsyncHTTPClient.configure(SimpleAsyncHTTPClient)
        with closing(AsyncHTTPClient(
                self.io_loop, force_instance=True)) as client:
            self.assertEqual(client.max_clients, 10)
        with closing(AsyncHTTPClient(
                self.io_loop, max_clients=11, force_instance=True)) as client:
            self.assertEqual(client.max_clients, 11)

        # Now configure max_clients statically and try overriding it
        # with each way max_clients can be passed
        AsyncHTTPClient.configure(SimpleAsyncHTTPClient, max_clients=12)
        with closing(AsyncHTTPClient(
                self.io_loop, force_instance=True)) as client:
            self.assertEqual(client.max_clients, 12)
        with closing(AsyncHTTPClient(
                self.io_loop, max_clients=13, force_instance=True)) as client:
            self.assertEqual(client.max_clients, 13)
        with closing(AsyncHTTPClient(
                self.io_loop, max_clients=14, force_instance=True)) as client:
            self.assertEqual(client.max_clients, 14)


class HTTP100ContinueTestCase(AsyncHTTPTestCase):
    def respond_100(self, request):
        self.request = request
        self.request.connection.stream.write(
            b"HTTP/1.1 100 CONTINUE\r\n\r\n",
            self.respond_200)

    def respond_200(self):
        self.request.connection.stream.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nA",
            self.request.connection.stream.close)

    def get_app(self):
        # Not a full Application, but works as an HTTPServer callback
        return self.respond_100

    def test_100_continue(self):
        res = self.fetch('/')
        self.assertEqual(res.body, b'A')


class HostnameMappingTestCase(AsyncHTTPTestCase):
    def setUp(self):
        super(HostnameMappingTestCase, self).setUp()
        self.http_client = SimpleAsyncHTTPClient(
            self.io_loop,
            hostname_mapping={
                'www.example.com': '127.0.0.1',
                ('foo.example.com', 8000): ('127.0.0.1', self.get_http_port()),
            })

    def get_app(self):
        return Application([url("/hello", HelloWorldHandler), ])

    def test_hostname_mapping(self):
        self.http_client.fetch(
            'http://www.example.com:%d/hello' % self.get_http_port(), self.stop)
        response = self.wait()
        response.rethrow()
        self.assertEqual(response.body, b'Hello world!')

    def test_port_mapping(self):
        self.http_client.fetch('http://foo.example.com:8000/hello', self.stop)
        response = self.wait()
        response.rethrow()
        self.assertEqual(response.body, b'Hello world!')
