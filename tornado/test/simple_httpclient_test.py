import collections
import logging

from tornado.ioloop import IOLoop
from tornado.simple_httpclient import SimpleAsyncHTTPClient, _DEFAULT_CA_CERTS
from tornado.test.httpclient_test import HTTPClientCommonTestCase
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.web import RequestHandler, Application, asynchronous, url

class SimpleHTTPClientCommonTestCase(HTTPClientCommonTestCase):
    def get_http_client(self):
        return SimpleAsyncHTTPClient(io_loop=self.io_loop,
                                     force_instance=True)

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

class SimpleHTTPClientTestCase(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        # callable objects to finish pending /trigger requests
        self.triggers = collections.deque()
        return Application([
            url("/trigger", TriggerHandler, dict(queue=self.triggers,
                                                 wake_callback=self.stop)),
            ])

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

    def xxx_test_default_certificates_exist(self):
        open(_DEFAULT_CA_CERTS).close()

