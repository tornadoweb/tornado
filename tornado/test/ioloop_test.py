#!/usr/bin/env python


from __future__ import absolute_import, division, with_statement
import datetime
import socket
import time
import unittest
import tempfile
import fcntl

from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from tornado.testing import AsyncTestCase, LogTrapTestCase, get_unused_port


class TestIOLoopCreation(unittest.TestCase):

    def setUp(self):
        self.reverters = []
        if IOLoop.initialized():
            del IOLoop._instance

    def tearDown(self):
        for reverter in self.reverters:
            reverter()

    def test_instance_methods_ensures_singleton(self):
        io_loop = IOLoop.instance()
        same_io_loop = IOLoop.instance()
        self.assertEqual(io_loop, same_io_loop)
        self.assertTrue(IOLoop.initialized())

    def test_ioloop_creation_without_instance_method_does_not_enforce_singleton(self):
        io_loop = IOLoop()
        self.assertFalse(IOLoop.initialized())
        self.assertNotEqual(io_loop, IOLoop.instance())

    def test_instance_method_locks_ioloop_creation(self):
        class StubLock(object):
            def __init__(self):
                self.acquired = self.released = False

            def __enter__(self):
                self.acquired = True

            def __exit__(self, t, v, tb):
                self.released = True

        stub_lock = StubLock()

        # stub the threading.Lock and ensures it's reverted on tearDown
        original_instance_lock = IOLoop._instance_lock
        IOLoop._instance_lock = stub_lock
        def revert_instance_lock():
            IOLoop._instance_lock = original_instance_lock
        self.reverters.append(revert_instance_lock)

        ioloop = IOLoop.instance()

        self.assertTrue(stub_lock.acquired)
        self.assertTrue(stub_lock.released)

    def test_install_ioloop_as_the_singleton_instance(self):
        io_loop = IOLoop()
        io_loop.install()

        self.assertEqual(io_loop, IOLoop.instance())

    def test_install_should_assert_ioloop_is_not_initialized(self):
        IOLoop.instance()       # initialized

        with self.assertRaises(AssertionError):
            io_loop = IOLoop()
            io_loop.install()

    def test_registers_handler_to_send_bogus_data_when_idle(self):
        context = {}
        def add_handler(self, fd, handler, events):
            context.update({
                    'fd': fd,
                    'handler': handler,
                    'events': events})

        original_add_handler = IOLoop.add_handler
        IOLoop.add_handler = add_handler
        def revert_add_handler():
            IOLoop.add_handler = original_add_handler
        self.reverters.append(revert_add_handler)

        IOLoop()

        self.assertTrue(context)
        self.assertEqual(context['events'], IOLoop.READ)

    def test_sets_CLOEXEC_on_poll_implementations_that_have_file_descriptors(self):
        # fetches a valid file descriptor. note that I don't use the fd created
        # by tempfile.mkstemp() because it alredy set's the CLOEXEC flag
        tmp_file = open(tempfile.mkstemp()[1])
        fd = tmp_file.fileno()
        self.reverters.append(tmp_file.close)

        # stub poll() implementation that returns my known fd
        class FakePoll(object):
            def fileno(self):
                return fd
            def register(self, *args):
                pass

        IOLoop(FakePoll())

        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        self.assertTrue(flags & fcntl.FD_CLOEXEC)


class TestIOLoop(AsyncTestCase, LogTrapTestCase):

    def test_add_callback_wakeup(self):
        # Make sure that add_callback from inside a running IOLoop
        # wakes up the IOLoop immediately instead of waiting for a timeout.
        def callback():
            self.called = True
            self.stop()

        def schedule_callback():
            self.called = False
            self.io_loop.add_callback(callback)
            # Store away the time so we can check if we woke up immediately
            self.start_time = time.time()
        self.io_loop.add_timeout(time.time(), schedule_callback)
        self.wait()
        self.assertAlmostEqual(time.time(), self.start_time, places=2)
        self.assertTrue(self.called)

    def test_add_timeout_timedelta(self):
        self.io_loop.add_timeout(datetime.timedelta(microseconds=1), self.stop)
        self.wait()

    def test_multiple_add(self):
        [sock] = bind_sockets(get_unused_port(), '127.0.0.1',
                              family=socket.AF_INET)
        try:
            self.io_loop.add_handler(sock.fileno(), lambda fd, events: None,
                                     IOLoop.READ)
            # Attempting to add the same handler twice fails
            # (with a platform-dependent exception)
            self.assertRaises(Exception, self.io_loop.add_handler,
                              sock.fileno(), lambda fd, events: None,
                              IOLoop.READ)
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
