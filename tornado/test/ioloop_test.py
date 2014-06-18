#!/usr/bin/env python


from __future__ import absolute_import, division, print_function, with_statement
import contextlib
import datetime
import functools
import socket
import sys
import threading
import time

from tornado import gen
from tornado.ioloop import IOLoop, TimeoutError
from tornado.log import app_log
from tornado.stack_context import ExceptionStackContext, StackContext, wrap, NullContext
from tornado.testing import AsyncTestCase, bind_unused_port, ExpectLog
from tornado.test.util import unittest, skipIfNonUnix, skipOnTravis

try:
    from concurrent import futures
except ImportError:
    futures = None


class TestIOLoop(AsyncTestCase):
    @skipOnTravis
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
        self.io_loop.add_timeout(self.io_loop.time(), schedule_callback)
        self.wait()
        self.assertAlmostEqual(time.time(), self.start_time, places=2)
        self.assertTrue(self.called)

    @skipOnTravis
    def test_add_callback_wakeup_other_thread(self):
        def target():
            # sleep a bit to let the ioloop go into its poll loop
            time.sleep(0.01)
            self.stop_time = time.time()
            self.io_loop.add_callback(self.stop)
        thread = threading.Thread(target=target)
        self.io_loop.add_callback(thread.start)
        self.wait()
        delta = time.time() - self.stop_time
        self.assertLess(delta, 0.1)
        thread.join()

    def test_add_timeout_timedelta(self):
        self.io_loop.add_timeout(datetime.timedelta(microseconds=1), self.stop)
        self.wait()

    def test_multiple_add(self):
        sock, port = bind_unused_port()
        try:
            self.io_loop.add_handler(sock.fileno(), lambda fd, events: None,
                                     IOLoop.READ)
            # Attempting to add the same handler twice fails
            # (with a platform-dependent exception)
            self.assertRaises(Exception, self.io_loop.add_handler,
                              sock.fileno(), lambda fd, events: None,
                              IOLoop.READ)
        finally:
            self.io_loop.remove_handler(sock.fileno())
            sock.close()

    def test_remove_without_add(self):
        # remove_handler should not throw an exception if called on an fd
        # was never added.
        sock, port = bind_unused_port()
        try:
            self.io_loop.remove_handler(sock.fileno())
        finally:
            sock.close()

    def test_add_callback_from_signal(self):
        # cheat a little bit and just run this normally, since we can't
        # easily simulate the races that happen with real signal handlers
        self.io_loop.add_callback_from_signal(self.stop)
        self.wait()

    def test_add_callback_from_signal_other_thread(self):
        # Very crude test, just to make sure that we cover this case.
        # This also happens to be the first test where we run an IOLoop in
        # a non-main thread.
        other_ioloop = IOLoop()
        thread = threading.Thread(target=other_ioloop.start)
        thread.start()
        other_ioloop.add_callback_from_signal(other_ioloop.stop)
        thread.join()
        other_ioloop.close()

    def test_add_callback_while_closing(self):
        # Issue #635: add_callback() should raise a clean exception
        # if called while another thread is closing the IOLoop.
        closing = threading.Event()

        def target():
            other_ioloop.add_callback(other_ioloop.stop)
            other_ioloop.start()
            closing.set()
            other_ioloop.close(all_fds=True)
        other_ioloop = IOLoop()
        thread = threading.Thread(target=target)
        thread.start()
        closing.wait()
        for i in range(1000):
            try:
                other_ioloop.add_callback(lambda: None)
            except RuntimeError as e:
                self.assertEqual("IOLoop is closing", str(e))
                break

    def test_handle_callback_exception(self):
        # IOLoop.handle_callback_exception can be overridden to catch
        # exceptions in callbacks.
        def handle_callback_exception(callback):
            self.assertIs(sys.exc_info()[0], ZeroDivisionError)
            self.stop()
        self.io_loop.handle_callback_exception = handle_callback_exception
        with NullContext():
            # remove the test StackContext that would see this uncaught
            # exception as a test failure.
            self.io_loop.add_callback(lambda: 1 / 0)
        self.wait()

    @skipIfNonUnix  # just because socketpair is so convenient
    def test_read_while_writeable(self):
        # Ensure that write events don't come in while we're waiting for
        # a read and haven't asked for writeability. (the reverse is
        # difficult to test for)
        client, server = socket.socketpair()
        try:
            def handler(fd, events):
                self.assertEqual(events, IOLoop.READ)
                self.stop()
            self.io_loop.add_handler(client.fileno(), handler, IOLoop.READ)
            self.io_loop.add_timeout(self.io_loop.time() + 0.01,
                                     functools.partial(server.send, b'asdf'))
            self.wait()
            self.io_loop.remove_handler(client.fileno())
        finally:
            client.close()
            server.close()

    def test_remove_timeout_after_fire(self):
        # It is not an error to call remove_timeout after it has run.
        handle = self.io_loop.add_timeout(self.io_loop.time(), self.stop)
        self.wait()
        self.io_loop.remove_timeout(handle)

    def test_remove_timeout_cleanup(self):
        # Add and remove enough callbacks to trigger cleanup.
        # Not a very thorough test, but it ensures that the cleanup code
        # gets executed and doesn't blow up.  This test is only really useful
        # on PollIOLoop subclasses, but it should run silently on any
        # implementation.
        for i in range(2000):
            timeout = self.io_loop.add_timeout(self.io_loop.time() + 3600,
                                               lambda: None)
            self.io_loop.remove_timeout(timeout)
        # HACK: wait two IOLoop iterations for the GC to happen.
        self.io_loop.add_callback(lambda: self.io_loop.add_callback(self.stop))
        self.wait()

    def test_timeout_with_arguments(self):
        # This tests that all the timeout methods pass through *args correctly.
        results = []
        self.io_loop.add_timeout(self.io_loop.time(), results.append, 1)
        self.io_loop.add_timeout(datetime.timedelta(seconds=0),
                                 results.append, 2)
        self.io_loop.call_at(self.io_loop.time(), results.append, 3)
        self.io_loop.call_later(0, results.append, 4)
        self.io_loop.call_later(0, self.stop)
        self.wait()
        self.assertEqual(results, [1, 2, 3, 4])

    def test_close_file_object(self):
        """When a file object is used instead of a numeric file descriptor,
        the object should be closed (by IOLoop.close(all_fds=True),
        not just the fd.
        """
        # Use a socket since they are supported by IOLoop on all platforms.
        # Unfortunately, sockets don't support the .closed attribute for
        # inspecting their close status, so we must use a wrapper.
        class SocketWrapper(object):
            def __init__(self, sockobj):
                self.sockobj = sockobj
                self.closed = False

            def fileno(self):
                return self.sockobj.fileno()

            def close(self):
                self.closed = True
                self.sockobj.close()
        sockobj, port = bind_unused_port()
        socket_wrapper = SocketWrapper(sockobj)
        io_loop = IOLoop()
        io_loop.add_handler(socket_wrapper, lambda fd, events: None,
                            IOLoop.READ)
        io_loop.close(all_fds=True)
        self.assertTrue(socket_wrapper.closed)

    def test_handler_callback_file_object(self):
        """The handler callback receives the same fd object it passed in."""
        server_sock, port = bind_unused_port()
        fds = []
        def handle_connection(fd, events):
            fds.append(fd)
            conn, addr = server_sock.accept()
            conn.close()
            self.stop()
        self.io_loop.add_handler(server_sock, handle_connection, IOLoop.READ)
        with contextlib.closing(socket.socket()) as client_sock:
            client_sock.connect(('127.0.0.1', port))
            self.wait()
        self.io_loop.remove_handler(server_sock)
        self.io_loop.add_handler(server_sock.fileno(), handle_connection,
                                 IOLoop.READ)
        with contextlib.closing(socket.socket()) as client_sock:
            client_sock.connect(('127.0.0.1', port))
            self.wait()
        self.assertIs(fds[0], server_sock)
        self.assertEqual(fds[1], server_sock.fileno())
        self.io_loop.remove_handler(server_sock.fileno())
        server_sock.close()

    def test_mixed_fd_fileobj(self):
        server_sock, port = bind_unused_port()
        def f(fd, events):
            pass
        self.io_loop.add_handler(server_sock, f, IOLoop.READ)
        with self.assertRaises(Exception):
            # The exact error is unspecified - some implementations use
            # IOError, others use ValueError.
            self.io_loop.add_handler(server_sock.fileno(), f, IOLoop.READ)
        self.io_loop.remove_handler(server_sock.fileno())
        server_sock.close()

    def test_reentrant(self):
        """Calling start() twice should raise an error, not deadlock."""
        returned_from_start = [False]
        got_exception = [False]
        def callback():
            try:
                self.io_loop.start()
                returned_from_start[0] = True
            except Exception:
                got_exception[0] = True
            self.stop()
        self.io_loop.add_callback(callback)
        self.wait()
        self.assertTrue(got_exception[0])
        self.assertFalse(returned_from_start[0])

    def test_exception_logging(self):
        """Uncaught exceptions get logged by the IOLoop."""
        # Use a NullContext to keep the exception from being caught by
        # AsyncTestCase.
        with NullContext():
            self.io_loop.add_callback(lambda: 1/0)
            self.io_loop.add_callback(self.stop)
            with ExpectLog(app_log, "Exception in callback"):
                self.wait()

    def test_exception_logging_future(self):
        """The IOLoop examines exceptions from Futures and logs them."""
        with NullContext():
            @gen.coroutine
            def callback():
                self.io_loop.add_callback(self.stop)
                1/0
            self.io_loop.add_callback(callback)
            with ExpectLog(app_log, "Exception in callback"):
                self.wait()

    def test_spawn_callback(self):
        # An added callback runs in the test's stack_context, so will be
        # re-arised in wait().
        self.io_loop.add_callback(lambda: 1/0)
        with self.assertRaises(ZeroDivisionError):
            self.wait()
        # A spawned callback is run directly on the IOLoop, so it will be
        # logged without stopping the test.
        self.io_loop.spawn_callback(lambda: 1/0)
        self.io_loop.add_callback(self.stop)
        with ExpectLog(app_log, "Exception in callback"):
            self.wait()


# Deliberately not a subclass of AsyncTestCase so the IOLoop isn't
# automatically set as current.
class TestIOLoopCurrent(unittest.TestCase):
    def setUp(self):
        self.io_loop = IOLoop()

    def tearDown(self):
        self.io_loop.close()

    def test_current(self):
        def f():
            self.current_io_loop = IOLoop.current()
            self.io_loop.stop()
        self.io_loop.add_callback(f)
        self.io_loop.start()
        self.assertIs(self.current_io_loop, self.io_loop)


class TestIOLoopAddCallback(AsyncTestCase):
    def setUp(self):
        super(TestIOLoopAddCallback, self).setUp()
        self.active_contexts = []

    def add_callback(self, callback, *args, **kwargs):
        self.io_loop.add_callback(callback, *args, **kwargs)

    @contextlib.contextmanager
    def context(self, name):
        self.active_contexts.append(name)
        yield
        self.assertEqual(self.active_contexts.pop(), name)

    def test_pre_wrap(self):
        # A pre-wrapped callback is run in the context in which it was
        # wrapped, not when it was added to the IOLoop.
        def f1():
            self.assertIn('c1', self.active_contexts)
            self.assertNotIn('c2', self.active_contexts)
            self.stop()

        with StackContext(functools.partial(self.context, 'c1')):
            wrapped = wrap(f1)

        with StackContext(functools.partial(self.context, 'c2')):
            self.add_callback(wrapped)

        self.wait()

    def test_pre_wrap_with_args(self):
        # Same as test_pre_wrap, but the function takes arguments.
        # Implementation note: The function must not be wrapped in a
        # functools.partial until after it has been passed through
        # stack_context.wrap
        def f1(foo, bar):
            self.assertIn('c1', self.active_contexts)
            self.assertNotIn('c2', self.active_contexts)
            self.stop((foo, bar))

        with StackContext(functools.partial(self.context, 'c1')):
            wrapped = wrap(f1)

        with StackContext(functools.partial(self.context, 'c2')):
            self.add_callback(wrapped, 1, bar=2)

        result = self.wait()
        self.assertEqual(result, (1, 2))


class TestIOLoopAddCallbackFromSignal(TestIOLoopAddCallback):
    # Repeat the add_callback tests using add_callback_from_signal
    def add_callback(self, callback, *args, **kwargs):
        self.io_loop.add_callback_from_signal(callback, *args, **kwargs)


@unittest.skipIf(futures is None, "futures module not present")
class TestIOLoopFutures(AsyncTestCase):
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


class TestIOLoopRunSync(unittest.TestCase):
    def setUp(self):
        self.io_loop = IOLoop()

    def tearDown(self):
        self.io_loop.close()

    def test_sync_result(self):
        self.assertEqual(self.io_loop.run_sync(lambda: 42), 42)

    def test_sync_exception(self):
        with self.assertRaises(ZeroDivisionError):
            self.io_loop.run_sync(lambda: 1 / 0)

    def test_async_result(self):
        @gen.coroutine
        def f():
            yield gen.Task(self.io_loop.add_callback)
            raise gen.Return(42)
        self.assertEqual(self.io_loop.run_sync(f), 42)

    def test_async_exception(self):
        @gen.coroutine
        def f():
            yield gen.Task(self.io_loop.add_callback)
            1 / 0
        with self.assertRaises(ZeroDivisionError):
            self.io_loop.run_sync(f)

    def test_current(self):
        def f():
            self.assertIs(IOLoop.current(), self.io_loop)
        self.io_loop.run_sync(f)

    def test_timeout(self):
        @gen.coroutine
        def f():
            yield gen.Task(self.io_loop.add_timeout, self.io_loop.time() + 1)
        self.assertRaises(TimeoutError, self.io_loop.run_sync, f, timeout=0.01)


if __name__ == "__main__":
    unittest.main()
