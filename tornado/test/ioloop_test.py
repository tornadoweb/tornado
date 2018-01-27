from __future__ import absolute_import, division, print_function

from concurrent.futures import ThreadPoolExecutor
import contextlib
import datetime
import functools
import socket
import subprocess
import sys
import threading
import time
import types

from tornado.escape import native_str
from tornado import gen
from tornado.ioloop import IOLoop, TimeoutError, PollIOLoop, PeriodicCallback
from tornado.log import app_log
from tornado.platform.select import _Select
from tornado.stack_context import ExceptionStackContext, StackContext, wrap, NullContext
from tornado.testing import AsyncTestCase, bind_unused_port, ExpectLog, gen_test
from tornado.test.util import unittest, skipIfNonUnix, skipOnTravis, skipBefore35, exec_test

try:
    from concurrent import futures
except ImportError:
    futures = None

try:
    import asyncio
except ImportError:
    asyncio = None

try:
    import twisted
except ImportError:
    twisted = None


class FakeTimeSelect(_Select):
    def __init__(self):
        self._time = 1000
        super(FakeTimeSelect, self).__init__()

    def time(self):
        return self._time

    def sleep(self, t):
        self._time += t

    def poll(self, timeout):
        events = super(FakeTimeSelect, self).poll(0)
        if events:
            return events
        self._time += timeout
        return []


class FakeTimeIOLoop(PollIOLoop):
    """IOLoop implementation with a fake and deterministic clock.

    The clock advances as needed to trigger timeouts immediately.
    For use when testing code that involves the passage of time
    and no external dependencies.
    """
    def initialize(self):
        self.fts = FakeTimeSelect()
        super(FakeTimeIOLoop, self).initialize(impl=self.fts,
                                               time_func=self.fts.time)

    def sleep(self, t):
        """Simulate a blocking sleep by advancing the clock."""
        self.fts.sleep(t)


class TestIOLoop(AsyncTestCase):
    def test_add_callback_return_sequence(self):
        # A callback returning {} or [] shouldn't spin the CPU, see Issue #1803.
        self.calls = 0

        loop = self.io_loop
        test = self
        old_add_callback = loop.add_callback

        def add_callback(self, callback, *args, **kwargs):
            test.calls += 1
            old_add_callback(callback, *args, **kwargs)

        loop.add_callback = types.MethodType(add_callback, loop)
        loop.add_callback(lambda: {})
        loop.add_callback(lambda: [])
        loop.add_timeout(datetime.timedelta(milliseconds=50), loop.stop)
        loop.start()
        self.assertLess(self.calls, 10)

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
        # add_callback should not fail if it races with another thread
        # closing the IOLoop. The callbacks are dropped silently
        # without executing.
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
            other_ioloop.add_callback(lambda: None)

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

    def test_remove_timeout_from_timeout(self):
        calls = [False, False]

        # Schedule several callbacks and wait for them all to come due at once.
        # t2 should be cancelled by t1, even though it is already scheduled to
        # be run before the ioloop even looks at it.
        now = self.io_loop.time()

        def t1():
            calls[0] = True
            self.io_loop.remove_timeout(t2_handle)
        self.io_loop.add_timeout(now + 0.01, t1)

        def t2():
            calls[1] = True
        t2_handle = self.io_loop.add_timeout(now + 0.02, t2)
        self.io_loop.add_timeout(now + 0.03, self.stop)
        time.sleep(0.03)
        self.wait()
        self.assertEqual(calls, [True, False])

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
        # The asyncio event loop does not guarantee the order of these
        # callbacks, but PollIOLoop does.
        self.assertEqual(sorted(results), [1, 2, 3, 4])

    def test_add_timeout_return(self):
        # All the timeout methods return non-None handles that can be
        # passed to remove_timeout.
        handle = self.io_loop.add_timeout(self.io_loop.time(), lambda: None)
        self.assertFalse(handle is None)
        self.io_loop.remove_timeout(handle)

    def test_call_at_return(self):
        handle = self.io_loop.call_at(self.io_loop.time(), lambda: None)
        self.assertFalse(handle is None)
        self.io_loop.remove_timeout(handle)

    def test_call_later_return(self):
        handle = self.io_loop.call_later(0, lambda: None)
        self.assertFalse(handle is None)
        self.io_loop.remove_timeout(handle)

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
            self.io_loop.add_callback(lambda: 1 / 0)
            self.io_loop.add_callback(self.stop)
            with ExpectLog(app_log, "Exception in callback"):
                self.wait()

    def test_exception_logging_future(self):
        """The IOLoop examines exceptions from Futures and logs them."""
        with NullContext():
            @gen.coroutine
            def callback():
                self.io_loop.add_callback(self.stop)
                1 / 0
            self.io_loop.add_callback(callback)
            with ExpectLog(app_log, "Exception in callback"):
                self.wait()

    @skipBefore35
    def test_exception_logging_native_coro(self):
        """The IOLoop examines exceptions from awaitables and logs them."""
        namespace = exec_test(globals(), locals(), """
        async def callback():
            # Stop the IOLoop two iterations after raising an exception
            # to give the exception time to be logged.
            self.io_loop.add_callback(self.io_loop.add_callback, self.stop)
            1 / 0
        """)
        with NullContext():
            self.io_loop.add_callback(namespace["callback"])
            with ExpectLog(app_log, "Exception in callback"):
                self.wait()

    def test_spawn_callback(self):
        # An added callback runs in the test's stack_context, so will be
        # re-raised in wait().
        self.io_loop.add_callback(lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            self.wait()
        # A spawned callback is run directly on the IOLoop, so it will be
        # logged without stopping the test.
        self.io_loop.spawn_callback(lambda: 1 / 0)
        self.io_loop.add_callback(self.stop)
        with ExpectLog(app_log, "Exception in callback"):
            self.wait()

    @skipIfNonUnix
    def test_remove_handler_from_handler(self):
        # Create two sockets with simultaneous read events.
        client, server = socket.socketpair()
        try:
            client.send(b'abc')
            server.send(b'abc')

            # After reading from one fd, remove the other from the IOLoop.
            chunks = []

            def handle_read(fd, events):
                chunks.append(fd.recv(1024))
                if fd is client:
                    self.io_loop.remove_handler(server)
                else:
                    self.io_loop.remove_handler(client)
            self.io_loop.add_handler(client, handle_read, self.io_loop.READ)
            self.io_loop.add_handler(server, handle_read, self.io_loop.READ)
            self.io_loop.call_later(0.1, self.stop)
            self.wait()

            # Only one fd was read; the other was cleanly removed.
            self.assertEqual(chunks, [b'abc'])
        finally:
            client.close()
            server.close()


# Deliberately not a subclass of AsyncTestCase so the IOLoop isn't
# automatically set as current.
class TestIOLoopCurrent(unittest.TestCase):
    def setUp(self):
        self.io_loop = None
        IOLoop.clear_current()

    def tearDown(self):
        if self.io_loop is not None:
            self.io_loop.close()

    def test_default_current(self):
        self.io_loop = IOLoop()
        # The first IOLoop with default arguments is made current.
        self.assertIs(self.io_loop, IOLoop.current())
        # A second IOLoop can be created but is not made current.
        io_loop2 = IOLoop()
        self.assertIs(self.io_loop, IOLoop.current())
        io_loop2.close()

    def test_non_current(self):
        self.io_loop = IOLoop(make_current=False)
        # The new IOLoop is not initially made current.
        self.assertIsNone(IOLoop.current(instance=False))
        # Starting the IOLoop makes it current, and stopping the loop
        # makes it non-current. This process is repeatable.
        for i in range(3):
            def f():
                self.current_io_loop = IOLoop.current()
                self.io_loop.stop()
            self.io_loop.add_callback(f)
            self.io_loop.start()
            self.assertIs(self.current_io_loop, self.io_loop)
            # Now that the loop is stopped, it is no longer current.
            self.assertIsNone(IOLoop.current(instance=False))

    def test_force_current(self):
        self.io_loop = IOLoop(make_current=True)
        self.assertIs(self.io_loop, IOLoop.current())
        with self.assertRaises(RuntimeError):
            # A second make_current=True construction cannot succeed.
            IOLoop(make_current=True)
        # current() was not affected by the failed construction.
        self.assertIs(self.io_loop, IOLoop.current())


class TestIOLoopCurrentAsync(AsyncTestCase):
    @gen_test
    def test_clear_without_current(self):
        # If there is no current IOLoop, clear_current is a no-op (but
        # should not fail). Use a thread so we see the threading.Local
        # in a pristine state.
        with ThreadPoolExecutor(1) as e:
            yield e.submit(IOLoop.clear_current)


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

    @gen_test
    def test_run_in_executor_gen(self):
        event1 = threading.Event()
        event2 = threading.Event()

        def sync_func(self_event, other_event):
            self_event.set()
            other_event.wait()
            # Note that return value doesn't actually do anything,
            # it is just passed through to our final assertion to
            # make sure it is passed through properly.
            return self_event

        # Run two synchronous functions, which would deadlock if not
        # run in parallel.
        res = yield [
            IOLoop.current().run_in_executor(None, sync_func, event1, event2),
            IOLoop.current().run_in_executor(None, sync_func, event2, event1)
        ]

        self.assertEqual([event1, event2], res)

    @skipBefore35
    @gen_test
    def test_run_in_executor_native(self):
        event1 = threading.Event()
        event2 = threading.Event()

        def sync_func(self_event, other_event):
            self_event.set()
            other_event.wait()
            return self_event

        # Go through an async wrapper to ensure that the result of
        # run_in_executor works with await and not just gen.coroutine
        # (simply passing the underlying concurrrent future would do that).
        namespace = exec_test(globals(), locals(), """
            async def async_wrapper(self_event, other_event):
                return await IOLoop.current().run_in_executor(
                    None, sync_func, self_event, other_event)
        """)

        res = yield [
            namespace["async_wrapper"](event1, event2),
            namespace["async_wrapper"](event2, event1)
        ]

        self.assertEqual([event1, event2], res)

    @gen_test
    def test_set_default_executor(self):
        count = [0]

        class MyExecutor(futures.ThreadPoolExecutor):
            def submit(self, func, *args):
                count[0] += 1
                return super(MyExecutor, self).submit(func, *args)

        event = threading.Event()

        def sync_func():
            event.set()

        executor = MyExecutor(1)
        loop = IOLoop.current()
        loop.set_default_executor(executor)
        yield loop.run_in_executor(None, sync_func)
        self.assertEqual(1, count[0])
        self.assertTrue(event.is_set())


class TestIOLoopRunSync(unittest.TestCase):
    def setUp(self):
        self.io_loop = IOLoop()

    def tearDown(self):
        self.io_loop.close()

    def test_sync_result(self):
        with self.assertRaises(gen.BadYieldError):
            self.io_loop.run_sync(lambda: 42)

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

    @skipBefore35
    def test_native_coroutine(self):
        namespace = exec_test(globals(), locals(), """
        async def f():
            await gen.Task(self.io_loop.add_callback)
        """)
        self.io_loop.run_sync(namespace['f'])


@unittest.skipIf(asyncio is not None,
                 'IOLoop configuration not available')
class TestPeriodicCallback(unittest.TestCase):
    def setUp(self):
        self.io_loop = FakeTimeIOLoop()
        self.io_loop.make_current()

    def tearDown(self):
        self.io_loop.close()

    def test_basic(self):
        calls = []

        def cb():
            calls.append(self.io_loop.time())
        pc = PeriodicCallback(cb, 10000)
        pc.start()
        self.io_loop.call_later(50, self.io_loop.stop)
        self.io_loop.start()
        self.assertEqual(calls, [1010, 1020, 1030, 1040, 1050])

    def test_overrun(self):
        sleep_durations = [9, 9, 10, 11, 20, 20, 35, 35, 0, 0]
        expected = [
            1010, 1020, 1030,  # first 3 calls on schedule
            1050, 1070,  # next 2 delayed one cycle
            1100, 1130,  # next 2 delayed 2 cycles
            1170, 1210,  # next 2 delayed 3 cycles
            1220, 1230,  # then back on schedule.
        ]
        calls = []

        def cb():
            calls.append(self.io_loop.time())
            if not sleep_durations:
                self.io_loop.stop()
                return
            self.io_loop.sleep(sleep_durations.pop(0))
        pc = PeriodicCallback(cb, 10000)
        pc.start()
        self.io_loop.start()
        self.assertEqual(calls, expected)

    def test_io_loop_set_at_start(self):
        # Check PeriodicCallback uses the current IOLoop at start() time,
        # not at instantiation time.
        calls = []
        io_loop = FakeTimeIOLoop()

        def cb():
            calls.append(io_loop.time())
        pc = PeriodicCallback(cb, 10000)
        io_loop.make_current()
        pc.start()
        io_loop.call_later(50, io_loop.stop)
        io_loop.start()
        self.assertEqual(calls, [1010, 1020, 1030, 1040, 1050])
        io_loop.close()


class TestIOLoopConfiguration(unittest.TestCase):
    def run_python(self, *statements):
        statements = [
            'from tornado.ioloop import IOLoop, PollIOLoop',
            'classname = lambda x: x.__class__.__name__',
        ] + list(statements)
        args = [sys.executable, '-c', '; '.join(statements)]
        return native_str(subprocess.check_output(args)).strip()

    def test_default(self):
        if asyncio is not None:
            # When asyncio is available, it is used by default.
            cls = self.run_python('print(classname(IOLoop.current()))')
            self.assertEqual(cls, 'AsyncIOMainLoop')
            cls = self.run_python('print(classname(IOLoop()))')
            self.assertEqual(cls, 'AsyncIOLoop')
        else:
            # Otherwise, the default is a subclass of PollIOLoop
            is_poll = self.run_python(
                'print(isinstance(IOLoop.current(), PollIOLoop))')
            self.assertEqual(is_poll, 'True')

    @unittest.skipIf(asyncio is not None,
                     "IOLoop configuration not available")
    def test_explicit_select(self):
        # SelectIOLoop can always be configured explicitly.
        default_class = self.run_python(
            'IOLoop.configure("tornado.platform.select.SelectIOLoop")',
            'print(classname(IOLoop.current()))')
        self.assertEqual(default_class, 'SelectIOLoop')

    @unittest.skipIf(asyncio is None, "asyncio module not present")
    def test_asyncio(self):
        cls = self.run_python(
            'IOLoop.configure("tornado.platform.asyncio.AsyncIOLoop")',
            'print(classname(IOLoop.current()))')
        self.assertEqual(cls, 'AsyncIOMainLoop')

    @unittest.skipIf(asyncio is None, "asyncio module not present")
    def test_asyncio_main(self):
        cls = self.run_python(
            'from tornado.platform.asyncio import AsyncIOMainLoop',
            'AsyncIOMainLoop().install()',
            'print(classname(IOLoop.current()))')
        self.assertEqual(cls, 'AsyncIOMainLoop')

    @unittest.skipIf(twisted is None, "twisted module not present")
    @unittest.skipIf(asyncio is not None,
                     "IOLoop configuration not available")
    def test_twisted(self):
        cls = self.run_python(
            'from tornado.platform.twisted import TwistedIOLoop',
            'TwistedIOLoop().install()',
            'print(classname(IOLoop.current()))')
        self.assertEqual(cls, 'TwistedIOLoop')


if __name__ == "__main__":
    unittest.main()
