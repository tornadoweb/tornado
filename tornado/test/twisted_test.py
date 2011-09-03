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

import os
import thread
import threading
import unittest

try:
    import fcntl
    import twisted
    from twisted.internet.interfaces import IReadDescriptor, IWriteDescriptor
    from tornado.platform.twisted import TornadoReactor
    from zope.interface import implements
except ImportError:
    fcntl = None
    twisted = None
    IReadDescriptor = IWriteDescriptor = None
    def implements(f): pass

from tornado.ioloop import IOLoop
from tornado.platform.auto import set_close_exec
from tornado.util import import_object

class ReactorWhenRunningTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())

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

class ReactorCallLaterTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())

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

class ReactorTwoCallLaterTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())

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

class ReactorCallFromThreadTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())
        self._mainThread = thread.get_ident()

    def tearDown(self):
        self._thread.join()

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

class ReactorCallInThread(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())
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

    def logPrefix(self): return "Reader"

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

    def logPrefix(self): return "Writer"

    def close(self):
        self._fd.close()

    def fileno(self):
        return self._fd.fileno()

    def connectionLost(self, reason):
        self.close()

    def doWrite(self):
        self._callback(self._fd)

class ReactorReaderWriterTest(unittest.TestCase):
    def _set_nonblocking(self, fd):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def setUp(self):
        self._reactor = TornadoReactor(IOLoop())
        r, w = os.pipe()
        self._set_nonblocking(r)
        self._set_nonblocking(w)
        set_close_exec(r)
        set_close_exec(w)
        self._p1 = os.fdopen(r, "rb", 0)
        self._p2 = os.fdopen(w, "wb", 0)

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

if twisted is None:
    del ReactorWhenRunningTest
    del ReactorCallLaterTest
    del ReactorTwoCallLaterTest
    del ReactorCallFromThreadTest
    del ReactorCallInThread
    del ReactorReaderWriterTest
else:
    # Import and run as much of twisted's test suite as possible.
    # This is unfortunately rather dependent on implementation details,
    # but there doesn't appear to be a clean all-in-one conformance test
    # suite for reactors.
    # This is a list of all test suites using the ReactorBuilder
    # available in Twisted 11.0.0.  Tests that do not currently pass
    # with the TornadoReactor are commented out.
    twisted_tests = [
        'twisted.internet.test.test_core.ObjectModelIntegrationTest',
        #'twisted.internet.test.test_core.SystemEventTestsBuilder',
        'twisted.internet.test.test_fdset.ReactorFDSetTestsBuilder',
        #'twisted.internet.test.test_process.ProcessTestsBuilder',
        #'twisted.internet.test.test_process.PTYProcessTestsBuilder',
        #'twisted.internet.test.test_tcp.TCPClientTestsBuilder',
        'twisted.internet.test.test_tcp.TCPPortTestsBuilder',
        'twisted.internet.test.test_tcp.TCPConnectionTestsBuilder',
        'twisted.internet.test.test_threads.ThreadTestsBuilder',
        'twisted.internet.test.test_time.TimeTestsBuilder',
        #'twisted.internet.test.test_tls.SSLClientTestsMixin',
        'twisted.internet.test.test_udp.UDPServerTestsBuilder',
        #'twisted.internet.test.test_unix.UNIXTestsBuilder',
        #'twisted.internet.test.test_unix.UNIXDatagramTestsBuilder',
        ]
    for test_name in twisted_tests:
        try:
            test = import_object(test_name)
        except (ImportError, AttributeError):
            continue
        class TornadoTest(test):
            _reactors = ["tornado.platform.twisted._TestReactor"]
        TornadoTest.__name__ = test.__name__
        globals().update(TornadoTest.makeTestCaseClasses())

if __name__ == "__main__":
    unittest.main()
