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

from __future__ import absolute_import, division, with_statement

import os
import signal
import thread
import threading
import unittest

try:
    import fcntl
    import twisted
    from twisted.internet.defer import Deferred
    from twisted.internet.interfaces import IReadDescriptor, IWriteDescriptor
    from twisted.internet.protocol import Protocol
    from twisted.web.client import Agent
    from twisted.web.resource import Resource
    from twisted.web.server import Site
    from twisted.python import log
    from tornado.platform.twisted import TornadoReactor
    from zope.interface import implements
except ImportError:
    fcntl = None
    twisted = None
    IReadDescriptor = IWriteDescriptor = None

    def implements(f):
        pass

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.platform.auto import set_close_exec
from tornado.testing import get_unused_port
from tornado.util import import_object
from tornado.web import RequestHandler, Application


def save_signal_handlers():
    saved = {}
    for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGCHLD]:
        saved[sig] = signal.getsignal(sig)
    assert "twisted" not in repr(saved), repr(saved)
    return saved


def restore_signal_handlers(saved):
    for sig, handler in saved.iteritems():
        signal.signal(sig, handler)


class ReactorTestCase(unittest.TestCase):
    def setUp(self):
        self._saved_signals = save_signal_handlers()
        self._io_loop = IOLoop()
        self._reactor = TornadoReactor(self._io_loop)

    def tearDown(self):
        self._io_loop.close(all_fds=True)
        restore_signal_handlers(self._saved_signals)


class ReactorWhenRunningTest(ReactorTestCase):
    def test_whenRunning(self):
        self._whenRunningCalled = False
        self._anotherWhenRunningCalled = False
        self._reactor.callWhenRunning(self.whenRunningCallback)
        self._reactor.run()
        self.assertTrue(self._whenRunningCalled)
        self.assertTrue(self._anotherWhenRunningCalled)

    def whenRunningCallback(self):
        self._whenRunningCalled = True
        self._reactor.callWhenRunning(self.anotherWhenRunningCallback)
        self._reactor.stop()

    def anotherWhenRunningCallback(self):
        self._anotherWhenRunningCalled = True


class ReactorCallLaterTest(ReactorTestCase):
    def test_callLater(self):
        self._laterCalled = False
        self._now = self._reactor.seconds()
        self._timeout = 0.001
        dc = self._reactor.callLater(self._timeout, self.callLaterCallback)
        self.assertEqual(self._reactor.getDelayedCalls(), [dc])
        self._reactor.run()
        self.assertTrue(self._laterCalled)
        self.assertTrue(self._called - self._now > self._timeout)
        self.assertEqual(self._reactor.getDelayedCalls(), [])

    def callLaterCallback(self):
        self._laterCalled = True
        self._called = self._reactor.seconds()
        self._reactor.stop()


class ReactorTwoCallLaterTest(ReactorTestCase):
    def test_callLater(self):
        self._later1Called = False
        self._later2Called = False
        self._now = self._reactor.seconds()
        self._timeout1 = 0.0005
        dc1 = self._reactor.callLater(self._timeout1, self.callLaterCallback1)
        self._timeout2 = 0.001
        dc2 = self._reactor.callLater(self._timeout2, self.callLaterCallback2)
        self.assertTrue(self._reactor.getDelayedCalls() == [dc1, dc2] or
                        self._reactor.getDelayedCalls() == [dc2, dc1])
        self._reactor.run()
        self.assertTrue(self._later1Called)
        self.assertTrue(self._later2Called)
        self.assertTrue(self._called1 - self._now > self._timeout1)
        self.assertTrue(self._called2 - self._now > self._timeout2)
        self.assertEqual(self._reactor.getDelayedCalls(), [])

    def callLaterCallback1(self):
        self._later1Called = True
        self._called1 = self._reactor.seconds()

    def callLaterCallback2(self):
        self._later2Called = True
        self._called2 = self._reactor.seconds()
        self._reactor.stop()


class ReactorCallFromThreadTest(ReactorTestCase):
    def setUp(self):
        super(ReactorCallFromThreadTest, self).setUp()
        self._mainThread = thread.get_ident()

    def tearDown(self):
        self._thread.join()
        super(ReactorCallFromThreadTest, self).tearDown()

    def _newThreadRun(self):
        self.assertNotEqual(self._mainThread, thread.get_ident())
        if hasattr(self._thread, 'ident'):  # new in python 2.6
            self.assertEqual(self._thread.ident, thread.get_ident())
        self._reactor.callFromThread(self._fnCalledFromThread)

    def _fnCalledFromThread(self):
        self.assertEqual(self._mainThread, thread.get_ident())
        self._reactor.stop()

    def _whenRunningCallback(self):
        self._thread = threading.Thread(target=self._newThreadRun)
        self._thread.start()

    def testCallFromThread(self):
        self._reactor.callWhenRunning(self._whenRunningCallback)
        self._reactor.run()


class ReactorCallInThread(ReactorTestCase):
    def setUp(self):
        super(ReactorCallInThread, self).setUp()
        self._mainThread = thread.get_ident()

    def _fnCalledInThread(self, *args, **kwargs):
        self.assertNotEqual(thread.get_ident(), self._mainThread)
        self._reactor.callFromThread(lambda: self._reactor.stop())

    def _whenRunningCallback(self):
        self._reactor.callInThread(self._fnCalledInThread)

    def testCallInThread(self):
        self._reactor.callWhenRunning(self._whenRunningCallback)
        self._reactor.run()


class Reader:
    implements(IReadDescriptor)

    def __init__(self, fd, callback):
        self._fd = fd
        self._callback = callback

    def logPrefix(self):
        return "Reader"

    def close(self):
        self._fd.close()

    def fileno(self):
        return self._fd.fileno()

    def connectionLost(self, reason):
        self.close()

    def doRead(self):
        self._callback(self._fd)


class Writer:
    implements(IWriteDescriptor)

    def __init__(self, fd, callback):
        self._fd = fd
        self._callback = callback

    def logPrefix(self):
        return "Writer"

    def close(self):
        self._fd.close()

    def fileno(self):
        return self._fd.fileno()

    def connectionLost(self, reason):
        self.close()

    def doWrite(self):
        self._callback(self._fd)


class ReactorReaderWriterTest(ReactorTestCase):
    def _set_nonblocking(self, fd):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def setUp(self):
        super(ReactorReaderWriterTest, self).setUp()
        r, w = os.pipe()
        self._set_nonblocking(r)
        self._set_nonblocking(w)
        set_close_exec(r)
        set_close_exec(w)
        self._p1 = os.fdopen(r, "rb", 0)
        self._p2 = os.fdopen(w, "wb", 0)

    def tearDown(self):
        super(ReactorReaderWriterTest, self).tearDown()
        self._p1.close()
        self._p2.close()

    def _testReadWrite(self):
        """
        In this test the writer writes an 'x' to its fd. The reader
        reads it, check the value and ends the test.
        """
        self.shouldWrite = True

        def checkReadInput(fd):
            self.assertEquals(fd.read(), 'x')
            self._reactor.stop()

        def writeOnce(fd):
            if self.shouldWrite:
                self.shouldWrite = False
                fd.write('x')
        self._reader = Reader(self._p1, checkReadInput)
        self._writer = Writer(self._p2, writeOnce)

        self._reactor.addWriter(self._writer)

        # Test that adding the reader twice adds it only once to
        # IOLoop.
        self._reactor.addReader(self._reader)
        self._reactor.addReader(self._reader)

    def testReadWrite(self):
        self._reactor.callWhenRunning(self._testReadWrite)
        self._reactor.run()

    def _testNoWriter(self):
        """
        In this test we have no writer. Make sure the reader doesn't
        read anything.
        """
        def checkReadInput(fd):
            self.fail("Must not be called.")

        def stopTest():
            # Close the writer here since the IOLoop doesn't know
            # about it.
            self._writer.close()
            self._reactor.stop()
        self._reader = Reader(self._p1, checkReadInput)

        # We create a writer, but it should never be invoked.
        self._writer = Writer(self._p2, lambda fd: fd.write('x'))

        # Test that adding and removing the writer leaves us with no writer.
        self._reactor.addWriter(self._writer)
        self._reactor.removeWriter(self._writer)

        # Test that adding and removing the reader doesn't cause
        # unintended effects.
        self._reactor.addReader(self._reader)

        # Wake up after a moment and stop the test
        self._reactor.callLater(0.001, stopTest)

    def testNoWriter(self):
        self._reactor.callWhenRunning(self._testNoWriter)
        self._reactor.run()

# Test various combinations of twisted and tornado http servers,
# http clients, and event loop interfaces.


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.saved_signals = save_signal_handlers()
        self.io_loop = IOLoop()
        self.reactor = TornadoReactor(self.io_loop)

    def tearDown(self):
        self.reactor.disconnectAll()
        self.io_loop.close(all_fds=True)
        restore_signal_handlers(self.saved_signals)

    def start_twisted_server(self):
        class HelloResource(Resource):
            isLeaf = True

            def render_GET(self, request):
                return "Hello from twisted!"
        site = Site(HelloResource())
        self.twisted_port = get_unused_port()
        self.reactor.listenTCP(self.twisted_port, site, interface='127.0.0.1')

    def start_tornado_server(self):
        class HelloHandler(RequestHandler):
            def get(self):
                self.write("Hello from tornado!")
        app = Application([('/', HelloHandler)],
                          log_function=lambda x: None)
        self.tornado_port = get_unused_port()
        app.listen(self.tornado_port, address='127.0.0.1', io_loop=self.io_loop)

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
        client = AsyncHTTPClient(self.io_loop)

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
        d = client.request('GET', url)

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

        def shutdown(ignored):
            self.stop_loop()
        d.addBoth(shutdown)
        runner()
        self.assertTrue(chunks)
        return ''.join(chunks)

    def testTwistedServerTornadoClientIOLoop(self):
        self.start_twisted_server()
        response = self.tornado_fetch(
            'http://localhost:%d' % self.twisted_port, self.run_ioloop)
        self.assertEqual(response.body, 'Hello from twisted!')

    def testTwistedServerTornadoClientReactor(self):
        self.start_twisted_server()
        response = self.tornado_fetch(
            'http://localhost:%d' % self.twisted_port, self.run_reactor)
        self.assertEqual(response.body, 'Hello from twisted!')

    def testTornadoServerTwistedClientIOLoop(self):
        self.start_tornado_server()
        response = self.twisted_fetch(
            'http://localhost:%d' % self.tornado_port, self.run_ioloop)
        self.assertEqual(response, 'Hello from tornado!')

    def testTornadoServerTwistedClientReactor(self):
        self.start_tornado_server()
        response = self.twisted_fetch(
            'http://localhost:%d' % self.tornado_port, self.run_reactor)
        self.assertEqual(response, 'Hello from tornado!')


if twisted is None:
    del ReactorWhenRunningTest
    del ReactorCallLaterTest
    del ReactorTwoCallLaterTest
    del ReactorCallFromThreadTest
    del ReactorCallInThread
    del ReactorReaderWriterTest
    del CompatibilityTests
else:
    # Import and run as much of twisted's test suite as possible.
    # This is unfortunately rather dependent on implementation details,
    # but there doesn't appear to be a clean all-in-one conformance test
    # suite for reactors.
    #
    # This is a list of all test suites using the ReactorBuilder
    # available in Twisted 11.0.0 and 11.1.0 (and a blacklist of
    # specific test methods to be disabled).
    twisted_tests = {
        'twisted.internet.test.test_core.ObjectModelIntegrationTest': [],
        'twisted.internet.test.test_core.SystemEventTestsBuilder': [
            'test_iterate',  # deliberately not supported
            ],
        'twisted.internet.test.test_fdset.ReactorFDSetTestsBuilder': [
            "test_lostFileDescriptor",  # incompatible with epoll and kqueue
            ],
        'twisted.internet.test.test_process.ProcessTestsBuilder': [
            # Doesn't work on python 2.5
            'test_systemCallUninterruptedByChildExit',
            # Doesn't clean up its temp files
            'test_shebang',
            ],
        # Process tests appear to work on OSX 10.7, but not 10.6
        #'twisted.internet.test.test_process.PTYProcessTestsBuilder': [
        #    'test_systemCallUninterruptedByChildExit',
        #    ],
        'twisted.internet.test.test_tcp.TCPClientTestsBuilder': [
            'test_badContext',  # ssl-related; see also SSLClientTestsMixin
            ],
        'twisted.internet.test.test_tcp.TCPPortTestsBuilder': [
            # These use link-local addresses and cause firewall prompts on mac
            'test_buildProtocolIPv6AddressScopeID',
            'test_portGetHostOnIPv6ScopeID',
            'test_serverGetHostOnIPv6ScopeID',
            'test_serverGetPeerOnIPv6ScopeID',
            ],
        'twisted.internet.test.test_tcp.TCPConnectionTestsBuilder': [],
        'twisted.internet.test.test_tcp.WriteSequenceTests': [],
        'twisted.internet.test.test_tcp.AbortConnectionTestCase': [],
        'twisted.internet.test.test_threads.ThreadTestsBuilder': [],
        'twisted.internet.test.test_time.TimeTestsBuilder': [],
        # Extra third-party dependencies (pyOpenSSL)
        #'twisted.internet.test.test_tls.SSLClientTestsMixin': [],
        'twisted.internet.test.test_udp.UDPServerTestsBuilder': [],
        'twisted.internet.test.test_unix.UNIXTestsBuilder': [
            # Platform-specific.  These tests would be skipped automatically
            # if we were running twisted's own test runner.
            'test_connectToLinuxAbstractNamespace',
            'test_listenOnLinuxAbstractNamespace',
            ],
        'twisted.internet.test.test_unix.UNIXDatagramTestsBuilder': [
            'test_listenOnLinuxAbstractNamespace',
            ],
        'twisted.internet.test.test_unix.UNIXPortTestsBuilder': [],
        }
    for test_name, blacklist in twisted_tests.iteritems():
        try:
            test_class = import_object(test_name)
        except (ImportError, AttributeError):
            continue
        for test_func in blacklist:
            if hasattr(test_class, test_func):
                # The test_func may be defined in a mixin, so clobber
                # it instead of delattr()
                setattr(test_class, test_func, lambda self: None)

        def make_test_subclass(test_class):
            class TornadoTest(test_class):
                _reactors = ["tornado.platform.twisted._TestReactor"]

                def buildReactor(self):
                    self.__saved_signals = save_signal_handlers()
                    return test_class.buildReactor(self)

                def unbuildReactor(self, reactor):
                    test_class.unbuildReactor(self, reactor)
                    # Clean up file descriptors (especially epoll/kqueue
                    # objects) eagerly instead of leaving them for the
                    # GC.  Unfortunately we can't do this in reactor.stop
                    # since twisted expects to be able to unregister
                    # connections in a post-shutdown hook.
                    reactor._io_loop.close(all_fds=True)
                    restore_signal_handlers(self.__saved_signals)

            TornadoTest.__name__ = test_class.__name__
            return TornadoTest
        test_subclass = make_test_subclass(test_class)
        globals().update(test_subclass.makeTestCaseClasses())

    # Since we're not using twisted's test runner, it's tricky to get
    # logging set up well.  Most of the time it's easiest to just
    # leave it turned off, but while working on these tests you may want
    # to uncomment one of the other lines instead.
    log.defaultObserver.stop()
    #import sys; log.startLogging(sys.stderr, setStdout=0)
    #log.startLoggingWithObserver(log.PythonLoggingObserver().emit, setStdout=0)

if __name__ == "__main__":
    unittest.main()
