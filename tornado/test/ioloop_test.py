#!/usr/bin/env python


from __future__ import absolute_import, division, with_statement
import datetime
import socket
import threading
import time

from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from tornado.stack_context import ExceptionStackContext
from tornado.testing import AsyncTestCase, LogTrapTestCase, get_unused_port
from tornado.test.util import unittest

try:
    from concurrent import futures
except ImportError:
    futures = None


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


class TestIOLoopFutures(AsyncTestCase, LogTrapTestCase):
    def test_add_future_threads(self):
        with futures.ThreadPoolExecutor(1) as pool:
            self.io_loop.add_future(pool.submit(lambda: None),
                                    lambda future: self.stop(future))
            future = self.wait()
            self.assertTrue(future.done())
            self.assertTrue(future.result() is None)

    def test_add_future_stack_context(self):
        ready = threading.Event()
        def task():
            # we must wait for the ioloop callback to be scheduled before
            # the task completes to ensure that add_future adds the callback
            # asynchronously (which is the scenario in which capturing
            # the stack_context matters)
            ready.wait(1)
            assert ready.isSet(), "timed out"
            raise Exception("worker")
        def callback(future):
            self.future = future
            raise Exception("callback")
        def handle_exception(typ, value, traceback):
            self.exception = value
            self.stop()
            return True

        # stack_context propagates to the ioloop callback, but the worker
        # task just has its exceptions caught and saved in the Future.
        with futures.ThreadPoolExecutor(1) as pool:
            with ExceptionStackContext(handle_exception):
                self.io_loop.add_future(pool.submit(task), callback)
            ready.set()
        self.wait()

        self.assertEqual(self.exception.args[0], "callback")
        self.assertEqual(self.future.exception().args[0], "worker")
TestIOLoopFutures = unittest.skipIf(
    futures is None, "futures module not present")(TestIOLoopFutures)


if __name__ == "__main__":
    unittest.main()
