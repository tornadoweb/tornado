# Author: Ovidiu Predescu
# Date: July 2011
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Unittest for the twisted-style reactor.
"""

from __future__ import absolute_import, division, print_function

import logging
import signal
import sys
import warnings

from tornado.escape import utf8
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.testing import bind_unused_port, AsyncTestCase, gen_test
from tornado.test.util import unittest
from tornado.web import RequestHandler, Application

try:
    from twisted.internet.defer import Deferred, inlineCallbacks, returnValue  # type: ignore
    from twisted.internet.protocol import Protocol  # type: ignore
    from twisted.internet.asyncioreactor import AsyncioSelectorReactor
    have_twisted = True
except ImportError:
    have_twisted = False

# The core of Twisted 12.3.0 is available on python 3, but twisted.web is not
# so test for it separately.
try:
    from twisted.web.client import Agent, readBody  # type: ignore
    from twisted.web.resource import Resource  # type: ignore
    from twisted.web.server import Site  # type: ignore
    # As of Twisted 15.0.0, twisted.web is present but fails our
    # tests due to internal str/bytes errors.
    have_twisted_web = sys.version_info < (3,)
except ImportError:
    have_twisted_web = False

skipIfNoTwisted = unittest.skipUnless(have_twisted,
                                      "twisted module not present")


def save_signal_handlers():
    saved = {}
    for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGCHLD]:
        saved[sig] = signal.getsignal(sig)
    if "twisted" in repr(saved):
        # This indicates we're not cleaning up after ourselves properly.
        raise Exception("twisted signal handlers already installed")
    return saved


def restore_signal_handlers(saved):
    for sig, handler in saved.items():
        signal.signal(sig, handler)


# Test various combinations of twisted and tornado http servers,
# http clients, and event loop interfaces.


@skipIfNoTwisted
@unittest.skipIf(not have_twisted_web, 'twisted web not present')
class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.saved_signals = save_signal_handlers()
        self.io_loop = IOLoop()
        self.io_loop.make_current()
        self.reactor = AsyncioSelectorReactor()

    def tearDown(self):
        self.reactor.disconnectAll()
        self.io_loop.clear_current()
        self.io_loop.close(all_fds=True)
        restore_signal_handlers(self.saved_signals)

    def start_twisted_server(self):
        class HelloResource(Resource):
            isLeaf = True

            def render_GET(self, request):
                return "Hello from twisted!"
        site = Site(HelloResource())
        port = self.reactor.listenTCP(0, site, interface='127.0.0.1')
        self.twisted_port = port.getHost().port

    def start_tornado_server(self):
        class HelloHandler(RequestHandler):
            def get(self):
                self.write("Hello from tornado!")
        app = Application([('/', HelloHandler)],
                          log_function=lambda x: None)
        server = HTTPServer(app)
        sock, self.tornado_port = bind_unused_port()
        server.add_sockets([sock])

    def run_ioloop(self):
        self.stop_loop = self.io_loop.stop
        self.io_loop.start()
        self.reactor.fireSystemEvent('shutdown')

    def run_reactor(self):
        self.stop_loop = self.reactor.stop
        self.stop = self.reactor.stop
        self.reactor.run()

    def tornado_fetch(self, url, runner):
        responses = []
        client = AsyncHTTPClient()

        def callback(response):
            responses.append(response)
            self.stop_loop()
        client.fetch(url, callback=callback)
        runner()
        self.assertEqual(len(responses), 1)
        responses[0].rethrow()
        return responses[0]

    def twisted_fetch(self, url, runner):
        # http://twistedmatrix.com/documents/current/web/howto/client.html
        chunks = []
        client = Agent(self.reactor)
        d = client.request(b'GET', utf8(url))

        class Accumulator(Protocol):
            def __init__(self, finished):
                self.finished = finished

            def dataReceived(self, data):
                chunks.append(data)

            def connectionLost(self, reason):
                self.finished.callback(None)

        def callback(response):
            finished = Deferred()
            response.deliverBody(Accumulator(finished))
            return finished
        d.addCallback(callback)

        def shutdown(failure):
            if hasattr(self, 'stop_loop'):
                self.stop_loop()
            elif failure is not None:
                # loop hasn't been initialized yet; try our best to
                # get an error message out. (the runner() interaction
                # should probably be refactored).
                try:
                    failure.raiseException()
                except:
                    logging.error('exception before starting loop', exc_info=True)
        d.addBoth(shutdown)
        runner()
        self.assertTrue(chunks)
        return ''.join(chunks)

    def twisted_coroutine_fetch(self, url, runner):
        body = [None]

        @gen.coroutine
        def f():
            # This is simpler than the non-coroutine version, but it cheats
            # by reading the body in one blob instead of streaming it with
            # a Protocol.
            client = Agent(self.reactor)
            response = yield client.request(b'GET', utf8(url))
            with warnings.catch_warnings():
                # readBody has a buggy DeprecationWarning in Twisted 15.0:
                # https://twistedmatrix.com/trac/changeset/43379
                warnings.simplefilter('ignore', category=DeprecationWarning)
                body[0] = yield readBody(response)
            self.stop_loop()
        self.io_loop.add_callback(f)
        runner()
        return body[0]

    def testTwistedServerTornadoClientIOLoop(self):
        self.start_twisted_server()
        response = self.tornado_fetch(
            'http://127.0.0.1:%d' % self.twisted_port, self.run_ioloop)
        self.assertEqual(response.body, 'Hello from twisted!')

    def testTwistedServerTornadoClientReactor(self):
        self.start_twisted_server()
        response = self.tornado_fetch(
            'http://127.0.0.1:%d' % self.twisted_port, self.run_reactor)
        self.assertEqual(response.body, 'Hello from twisted!')

    def testTornadoServerTwistedClientIOLoop(self):
        self.start_tornado_server()
        response = self.twisted_fetch(
            'http://127.0.0.1:%d' % self.tornado_port, self.run_ioloop)
        self.assertEqual(response, 'Hello from tornado!')

    def testTornadoServerTwistedClientReactor(self):
        self.start_tornado_server()
        response = self.twisted_fetch(
            'http://127.0.0.1:%d' % self.tornado_port, self.run_reactor)
        self.assertEqual(response, 'Hello from tornado!')

    def testTornadoServerTwistedCoroutineClientIOLoop(self):
        self.start_tornado_server()
        response = self.twisted_coroutine_fetch(
            'http://127.0.0.1:%d' % self.tornado_port, self.run_ioloop)
        self.assertEqual(response, 'Hello from tornado!')


@skipIfNoTwisted
class ConvertDeferredTest(AsyncTestCase):
    @gen_test
    def test_success(self):
        @inlineCallbacks
        def fn():
            if False:
                # inlineCallbacks doesn't work with regular functions;
                # must have a yield even if it's unreachable.
                yield
            returnValue(42)
        res = yield fn()
        self.assertEqual(res, 42)

    @gen_test
    def test_failure(self):
        @inlineCallbacks
        def fn():
            if False:
                yield
            1 / 0
        with self.assertRaises(ZeroDivisionError):
            yield fn()


if __name__ == "__main__":
    unittest.main()
