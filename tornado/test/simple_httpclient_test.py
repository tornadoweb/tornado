from __future__ import with_statement

import collections
import gzip
import logging
import socket

from tornado.ioloop import IOLoop
from tornado.simple_httpclient import SimpleAsyncHTTPClient, _DEFAULT_CA_CERTS
from tornado.test.httpclient_test import HTTPClientCommonTestCase, ChunkHandler, CountdownHandler, HelloWorldHandler
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.util import b
from tornado.web import RequestHandler, Application, asynchronous, url

class SimpleHTTPClientCommonTestCase(HTTPClientCommonTestCase):
    def get_http_client(self):
        client = SimpleAsyncHTTPClient(io_loop=self.io_loop,
                                       force_instance=True)
        self.assertTrue(isinstance(client, SimpleAsyncHTTPClient))
        return client

# Remove the base class from our namespace so the unittest module doesn't
# try to run it again.
del HTTPClientCommonTestCase

class TriggerHandler(RequestHandler):
    def initialize(self, queue, wake_callback):
        self.queue = queue
        self.wake_callback = wake_callback

    @asynchronous
    def get(self):
        logging.info("queuing trigger")
        self.queue.append(self.finish)
        self.wake_callback()

class HangHandler(RequestHandler):
    @asynchronous
    def get(self):
        pass

class ContentLengthHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Length", self.get_argument("value"))
        self.write("ok")

class SimpleHTTPClientTestCase(AsyncHTTPTestCase, LogTrapTestCase):
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
        client = SimpleAsyncHTTPClient(self.io_loop, max_clients=1,
                                       force_instance=True)
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
        self.assertNotEqual(response.body, b("asdfqwer"))
        # Our test data gets bigger when gzipped.  Oops.  :)
        self.assertEqual(len(response.body), 34)
        f = gzip.GzipFile(mode="r", fileobj=response.buffer)
        self.assertEqual(f.read(), b("asdfqwer"))

    def test_max_redirects(self):
        response = self.fetch("/countdown/5", max_redirects=3)
        self.assertEqual(302, response.code)
        # We requested 5, followed three redirects for 4, 3, 2, then the last
        # unfollowed redirect is to 1.
        self.assertTrue(response.request.url.endswith("/countdown/5"))
        self.assertTrue(response.effective_url.endswith("/countdown/2"))
        self.assertTrue(response.headers["Location"].endswith("/countdown/1"))

    def test_request_timeout(self):
        response = self.fetch('/hang', request_timeout=0.1)
        self.assertEqual(response.code, 599)
        self.assertTrue(0.099 < response.request_time < 0.11, response.request_time)
        self.assertEqual(str(response.error), "HTTP 599: Timeout")

    def test_ipv6(self):
        if not socket.has_ipv6:
            # python compiled without ipv6 support, so skip this test
            return
        try:
            self.http_server.listen(self.get_http_port(), address='::1')
        except socket.gaierror, e:
            if e.errno == socket.EAI_ADDRFAMILY:
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
        self.assertEqual(response.body, b("Hello world!"))

    def test_multiple_content_length_accepted(self):
        response = self.fetch("/content_length?value=2,2")
        self.assertEqual(response.body, b("ok"))
        response = self.fetch("/content_length?value=2,%202,2")
        self.assertEqual(response.body, b("ok"))

        response = self.fetch("/content_length?value=2,4")
        self.assertEqual(response.code, 599)
        response = self.fetch("/content_length?value=2,%202,3")
        self.assertEqual(response.code, 599)
