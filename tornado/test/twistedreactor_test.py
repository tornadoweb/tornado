import os
import sys
import thread

import tornado.twisted.reactor
tornado.twisted.reactor.install()
from twisted.internet import reactor

from twisted.internet.interfaces import IReadDescriptor, IWriteDescriptor

from twisted.python import log

from tornado.twisted.reactor import TornadoReactor
from tornado.testing import AsyncTestCase, LogTrapTestCase
import unittest

from zope.interface import implements

log.startLogging(sys.stdout)

class ReactorWhenRunningTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor()

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
        self._reactor = TornadoReactor()

    def test_callLater(self):
        self._laterCalled = False
        self._now = self._reactor.seconds()
        self._timeout = 0.001
        dc = self._reactor.callLater(self._timeout, self.callLaterCallback)
        self.assertEqual(self._reactor.getDelayedCalls(), [dc])
        self._reactor.run()
        self.assertTrue(self._laterCalled)
        self.assertGreater(self._called - self._now, self._timeout)
        self.assertEqual(self._reactor.getDelayedCalls(), [])

    def callLaterCallback(self):
        self._laterCalled = True
        self._called = self._reactor.seconds()
        self._reactor.stop()

class ReactorTwoCallLaterTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor()

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
        self.assertGreater(self._called1 - self._now, self._timeout1)
        self.assertGreater(self._called2 - self._now, self._timeout2)
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
        self._reactor = TornadoReactor()
        self._mainThread = thread.get_ident()

    def _newThreadRun(self, a, b):
        self.assertEqual(self._thread, thread.get_ident())
        self._reactor.callFromThread(self._fnCalledFromThread)

    def _fnCalledFromThread(self):
        self.assertEqual(self._mainThread, thread.get_ident())
        self._reactor.stop()

    def _whenRunningCallback(self):
        self._thread = thread.start_new_thread(self._newThreadRun, (None, None))

    def testCallFromThread(self):
        self._reactor.callWhenRunning(self._whenRunningCallback)
        self._reactor.run()

class ReactorCallInThread(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor()
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

    def fileno(self):
        return self._fd.fileno()

    def connectionLost(self, reason):
        return

    def doRead(self):
        self._callback(self._fd)

class Writer:
    implements(IWriteDescriptor)

    def __init__(self, fd, callback):
        self._fd = fd
        self._callback = callback

    def logPrefix(self): return "Writer"

    def fileno(self):
        return self._fd.fileno()

    def connectionLost(self, reason):
        return

    def doWrite(self):
        self._callback(self._fd)

class ReactorReaderWriterTest(unittest.TestCase):
    def setUp(self):
        self._reactor = TornadoReactor()
        r, w = os.pipe()
        self._reactor._ioloop._set_nonblocking(r)
        self._reactor._ioloop._set_nonblocking(w)
        self._reactor._ioloop._set_close_exec(r)
        self._reactor._ioloop._set_close_exec(w)
        self._p1 = os.fdopen(r, "rb", 0)
        self._p2 = os.fdopen(w, "wb", 0)

    def _testReadWrite(self):
        """
        In this test the writer writes an 'x' to its fd. The reader
        reads it, check the value and ends the test.
        """
        def checkReadInput(fd):
            self.assertEqual(fd.read(), 'x')
            self._reactor.stop()
        self._reader = Reader(self._p1, checkReadInput)
        self._writer = Writer(self._p2, lambda fd: fd.write('x'))
        self._reactor.addWriter(self._writer)
        self._reactor.removeWriter(self._writer)
        self._reactor.addWriter(self._writer)
        # Test the add/remove reader functionality
        self._reactor.addReader(self._writer)
        self._reactor.removeReader(self._writer)

        self._reactor.addReader(self._reader)
        self._reactor.removeReader(self._reader)
        self._reactor.addReader(self._reader)
        # Test the add/remove writer functionality
        self._reactor.addWriter(self._reader)
        self._reactor.removeWriter(self._reader)

    def testReadWrite(self):
        self._reactor.callWhenRunning(self._testReadWrite)
        self._reactor.run()

if __name__ == "__main__":
    unittest.main()
