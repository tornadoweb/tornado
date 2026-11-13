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

import asyncio
import contextlib
import contextvars
import gc
import io
import logging
import socket
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

import tornado.platform.asyncio
from tornado.platform import asyncio as platform_asyncio
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.platform.asyncio import (
    AddThreadSelectorEventLoop,
    AsyncIOLoop,
    SelectorThread,
    to_asyncio_future,
)
from tornado.test.util import (
    AsyncHTTPTestCase,
    AsyncTestCase,
    TestCase,
    ignore_deprecation,
)
from tornado.testing import ExpectLog, gen_test, setup_with_context_manager
from tornado.web import Application, RequestHandler


class AsyncIOLoopTest(AsyncTestCase):
    @property
    def asyncio_loop(self):
        return self.io_loop.asyncio_loop  # type: ignore

    def test_asyncio_callback(self):
        # Basic test that the asyncio loop is set up correctly.
        async def add_callback():
            asyncio.get_event_loop().call_soon(self.stop)

        self.asyncio_loop.run_until_complete(add_callback())
        self.wait()

    @gen_test
    def test_asyncio_future(self):
        # Test that we can yield an asyncio future from a tornado coroutine.
        # Without 'yield from', we must wrap coroutines in ensure_future.
        x = yield asyncio.ensure_future(
            asyncio.get_event_loop().run_in_executor(None, lambda: 42)
        )
        self.assertEqual(x, 42)

    @gen_test
    def test_asyncio_yield_from(self):
        @gen.coroutine
        def f():
            event_loop = asyncio.get_event_loop()
            x = yield from event_loop.run_in_executor(None, lambda: 42)
            return x

        result = yield f()
        self.assertEqual(result, 42)

    def test_asyncio_adapter(self):
        # This test demonstrates that when using the asyncio coroutine
        # runner (i.e. run_until_complete), the to_asyncio_future
        # adapter is needed. No adapter is needed in the other direction,
        # as demonstrated by other tests in the package.
        @gen.coroutine
        def tornado_coroutine():
            yield gen.moment
            raise gen.Return(42)

        async def native_coroutine_without_adapter():
            return await tornado_coroutine()

        async def native_coroutine_with_adapter():
            return await to_asyncio_future(tornado_coroutine())

        # Use the adapter, but two degrees from the tornado coroutine.
        async def native_coroutine_with_adapter2():
            return await to_asyncio_future(native_coroutine_without_adapter())

        # Tornado supports native coroutines both with and without adapters
        self.assertEqual(self.io_loop.run_sync(native_coroutine_without_adapter), 42)
        self.assertEqual(self.io_loop.run_sync(native_coroutine_with_adapter), 42)
        self.assertEqual(self.io_loop.run_sync(native_coroutine_with_adapter2), 42)

        # Asyncio only supports coroutines that yield asyncio-compatible
        # Futures (which our Future is since 5.0).
        self.assertEqual(
            self.asyncio_loop.run_until_complete(native_coroutine_without_adapter()),
            42,
        )
        self.assertEqual(
            self.asyncio_loop.run_until_complete(native_coroutine_with_adapter()),
            42,
        )
        self.assertEqual(
            self.asyncio_loop.run_until_complete(native_coroutine_with_adapter2()),
            42,
        )

    def test_add_thread_close_idempotent(self):
        loop = AddThreadSelectorEventLoop(asyncio.get_event_loop())  # type: ignore
        loop.close()
        loop.close()


class LeakTest(TestCase):
    def setUp(self):
        # Trigger a cleanup of the mapping so we start with a clean slate.
        AsyncIOLoop(make_current=False).close()

    def tearDown(self):
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except Exception:
            # We may not have a current event loop at this point.
            pass
        else:
            loop.close()

    def test_ioloop_close_leak(self):
        orig_count = len(IOLoop._ioloop_for_asyncio)
        for i in range(10):
            # Create and close an AsyncIOLoop using Tornado interfaces.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                loop = AsyncIOLoop()
                loop.close()
        new_count = len(IOLoop._ioloop_for_asyncio) - orig_count
        self.assertEqual(new_count, 0)

    def test_asyncio_close_leak(self):
        orig_count = len(IOLoop._ioloop_for_asyncio)
        for i in range(10):
            # Create and close an AsyncIOMainLoop using asyncio interfaces.
            loop = asyncio.new_event_loop()
            loop.call_soon(IOLoop.current)
            loop.call_soon(loop.stop)
            loop.run_forever()
            loop.close()
        new_count = len(IOLoop._ioloop_for_asyncio) - orig_count
        # Because the cleanup is run on new loop creation, we have one
        # dangling entry in the map (but only one).
        self.assertEqual(new_count, 1)


class SelectorThreadLeakTest(TestCase):
    # These tests are only relevant on windows, but they should pass anywhere.
    def setUp(self):
        # As a precaution, ensure that we've run an event loop at least once
        # so if it spins up any singleton threads they're already there.
        asyncio.run(self.dummy_tornado_coroutine())
        self.orig_thread_count = threading.active_count()

    def assert_no_thread_leak(self):
        # For some reason we see transient failures here, but I haven't been able
        # to catch it to identify which thread is causing it. Whatever thread it
        # is, it appears to quickly clean up on its own, so just retry a few times.
        # At least some of the time the errant thread was running at the time we
        # captured self.orig_thread_count, so use inequalities.
        deadline = time.time() + 1
        while time.time() < deadline:
            threads = list(threading.enumerate())
            if len(threads) <= self.orig_thread_count:
                break
            time.sleep(0.1)
        self.assertLessEqual(len(threads), self.orig_thread_count, threads)

    async def dummy_tornado_coroutine(self):
        # Just access the IOLoop to initialize the selector thread.
        IOLoop.current()

    def test_asyncio_run(self):
        for i in range(10):
            # asyncio.run calls shutdown_asyncgens for us.
            asyncio.run(self.dummy_tornado_coroutine())
        self.assert_no_thread_leak()

    def test_asyncio_manual(self):
        for i in range(10):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.dummy_tornado_coroutine())
            # Without this step, we'd leak the thread.
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        self.assert_no_thread_leak()

    def test_tornado(self):
        for i in range(10):
            # The IOLoop interfaces are aware of the selector thread and
            # (synchronously) shut it down.
            loop = IOLoop(make_current=False)
            loop.run_sync(self.dummy_tornado_coroutine)
            loop.close()
        self.assert_no_thread_leak()

    def test_atexit_closes_waker_sockets(self):
        # The atexit hook is the backstop for selectors whose loop was never
        # closed. It has to close the waker socketpair as well as shut the
        # thread down: otherwise the sockets survive until the interpreter
        # finalizes them, and each one is reported as an unclosed socket after
        # the test suite has finished.
        loop = asyncio.new_event_loop()
        selector = SelectorThread(loop)
        try:
            loop.run_until_complete(asyncio.sleep(0.05))
            self.assertIn(selector, platform_asyncio._selector_loops)
            platform_asyncio._atexit_callback()
            self.assertEqual(selector._waker_r.fileno(), -1)
            self.assertEqual(selector._waker_w.fileno(), -1)
            self.assertFalse(selector._thread.is_alive())  # type: ignore[union-attr]
        finally:
            selector.close()
            loop.close()

    def test_close_before_thread_manager_starts(self):
        # The task that starts the selector thread is created by a call_soon
        # callback, so a loop that stops immediately can close with that task
        # created but never run. Closing must clean it up; otherwise it is
        # reported as "Task was destroyed but it is pending", and its coroutine
        # as "never awaited", whenever it is eventually garbage collected --
        # which is at an unpredictable point, quite possibly during an
        # unrelated test.
        loop = asyncio.new_event_loop()
        selector = SelectorThread(loop)
        loop.call_soon(loop.stop)
        loop.run_forever()
        task = selector._thread_manager_task
        self.assertIsNotNone(task)
        # Once the task runs it completes immediately, so a task that is not
        # done here is one that never started.
        self.assertFalse(task.done())  # type: ignore[union-attr]
        selector.close()
        loop.close()
        del loop, selector, task
        # An asyncio error logged here would be caught by the log check in
        # tornado.test.util.TestCase, but only if the collection happens while
        # this test is running, so force it.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            gc.collect()
        self.assertNotIn("never awaited", stderr.getvalue())


class SelectorThreadTest(TestCase):
    # SelectorThread is only used automatically on Windows, but it can wrap
    # any event loop, so these tests run everywhere.
    def setUp(self):
        super().setUp()
        self.asyncio_loop = asyncio.new_event_loop()
        self.loop = AddThreadSelectorEventLoop(self.asyncio_loop)  # type: ignore[abstract]
        self.sockets: list[socket.socket] = []
        self.addCleanup(self.close)

    def close(self):
        # Stop the selector thread before closing the sockets it may be
        # selecting on.
        self.loop.close()
        for s in self.sockets:
            s.close()

    def socketpair(self):
        a, b = socket.socketpair()
        a.setblocking(False)
        b.setblocking(False)
        self.sockets.extend([a, b])
        return a, b

    def run_loop(self, coro):
        return self.asyncio_loop.run_until_complete(asyncio.wait_for(coro, 10))

    def test_add_reader_while_selecting(self):
        # A reader added while the selector thread is blocked in select must
        # interrupt it.
        a, b = self.socketpair()

        async def f():
            # Let the selector thread start and block.
            await asyncio.sleep(0.01)
            fut = asyncio.get_running_loop().create_future()
            self.loop.add_reader(a, lambda: fut.set_result(a.recv(10)))
            await asyncio.sleep(0.01)
            b.send(b"x")
            return await fut

        self.assertEqual(self.run_loop(f()), b"x")

    def test_already_readable(self):
        a, b = self.socketpair()
        b.send(b"x")

        async def f():
            fut = asyncio.get_running_loop().create_future()
            self.loop.add_reader(a, lambda: fut.set_result(a.recv(10)))
            return await fut

        self.assertEqual(self.run_loop(f()), b"x")

    def test_ping_pong(self):
        # Exercises the path where data written by one side is found
        # without waiting for the selector thread.
        a, b = self.socketpair()
        n = 100

        async def f():
            done = asyncio.get_running_loop().create_future()
            count = 0

            def on_a():
                a.recv(10)
                a.send(b"x")

            def on_b():
                nonlocal count
                b.recv(10)
                count += 1
                if count == n:
                    done.set_result(None)
                else:
                    b.send(b"x")

            self.loop.add_reader(a, on_a)
            self.loop.add_reader(b, on_b)
            b.send(b"x")
            await done
            self.loop.remove_reader(a)
            self.loop.remove_reader(b)
            return count

        self.assertEqual(self.run_loop(f()), n)

    def test_callback_exception(self):
        # An exception in one callback must not stop delivery of later
        # events.
        a, b = self.socketpair()
        c, d = self.socketpair()

        def bad():
            self.loop.remove_reader(a)
            raise Exception("oops")

        async def f():
            await asyncio.sleep(0.01)
            fut = asyncio.get_running_loop().create_future()
            self.loop.add_reader(a, bad)
            b.send(b"x")
            await asyncio.sleep(0.05)
            self.loop.add_reader(c, lambda: fut.set_result(c.recv(10)))
            d.send(b"y")
            return await fut

        with ExpectLog(logging.getLogger("asyncio"), "Exception in callback"):
            self.assertEqual(self.run_loop(f()), b"y")

    def test_redundant_wakeups_skipped(self):
        # Changes made while the selector thread is in select need only one
        # wakeup between them.
        class CountingWaker:
            def __init__(self, sock):
                self.sock = sock
                self.sends = 0

            def send(self, data):
                self.sends += 1
                return self.sock.send(data)

            def close(self):
                self.sock.close()

        selector = self.loop._selector
        waker = CountingWaker(selector._waker_w)
        selector._waker_w = waker  # type: ignore[assignment]
        socks = [self.socketpair()[0] for i in range(5)]

        async def f():
            # Let the selector thread start and block.
            await asyncio.sleep(0.01)
            for s in socks:
                self.loop.add_reader(s, lambda: None)
            for s in socks:
                self.loop.remove_reader(s)
            # The wakeup is processed before this sleep returns.
            await asyncio.sleep(0.05)

        self.run_loop(f())
        self.assertEqual(waker.sends, 1)


class AnyThreadEventLoopPolicyTest(TestCase):
    def setUp(self):
        setup_with_context_manager(self, ignore_deprecation())
        # Referencing the event loop policy attributes raises deprecation warnings,
        # so instead of importing this at the top of the file we capture it here.
        self.AnyThreadEventLoopPolicy = (
            tornado.platform.asyncio.AnyThreadEventLoopPolicy
        )
        self.orig_policy = asyncio.get_event_loop_policy()
        self.executor = ThreadPoolExecutor(1)

    def tearDown(self):
        asyncio.set_event_loop_policy(self.orig_policy)
        self.executor.shutdown()

    def get_event_loop_on_thread(self):
        def get_and_close_event_loop():
            """Get the event loop. Close it if one is returned.

            Returns the (closed) event loop. This is a silly thing
            to do and leaves the thread in a broken state, but it's
            enough for this test. Closing the loop avoids resource
            leak warnings.
            """
            loop = asyncio.get_event_loop()
            loop.close()
            return loop

        future = self.executor.submit(get_and_close_event_loop)
        return future.result()

    def test_asyncio_accessor(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            # With the default policy, non-main threads don't get an event
            # loop.
            self.assertRaises(
                RuntimeError, self.executor.submit(asyncio.get_event_loop).result
            )
            # Set the policy and we can get a loop.
            asyncio.set_event_loop_policy(self.AnyThreadEventLoopPolicy())
            self.assertIsInstance(
                self.executor.submit(asyncio.get_event_loop).result(),
                asyncio.AbstractEventLoop,
            )
            # Clean up to silence leak warnings. Always use asyncio since
            # IOLoop doesn't (currently) close the underlying loop.
            self.executor.submit(lambda: asyncio.get_event_loop().close()).result()

    def test_tornado_accessor(self):
        # Tornado's IOLoop.current() API can create a loop for any thread,
        # regardless of this event loop policy.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIsInstance(self.executor.submit(IOLoop.current).result(), IOLoop)
            # Clean up to silence leak warnings. Always use asyncio since
            # IOLoop doesn't (currently) close the underlying loop.
            self.executor.submit(lambda: asyncio.get_event_loop().close()).result()

            asyncio.set_event_loop_policy(self.AnyThreadEventLoopPolicy())
            self.assertIsInstance(self.executor.submit(IOLoop.current).result(), IOLoop)
            self.executor.submit(lambda: asyncio.get_event_loop().close()).result()


class SelectorThreadContextvarsTest(AsyncHTTPTestCase):
    ctx_value = "foo"
    test_endpoint = "/"
    tornado_test_ctx = contextvars.ContextVar("tornado_test_ctx", default="default")
    tornado_test_ctx.set(ctx_value)

    def get_app(self) -> Application:
        tornado_test_ctx = self.tornado_test_ctx

        class Handler(RequestHandler):
            async def get(self):
                # On the Windows platform,
                # when a asyncio.events.Handle is created
                # in the SelectorThread without providing a context,
                # it will copy the current thread's context,
                # which can lead to the loss of the main thread's context
                # when executing the handle.
                # Therefore, it is necessary to
                # save a copy of the main thread's context in the SelectorThread
                # for creating the handle.
                self.write(tornado_test_ctx.get())

        return Application([(self.test_endpoint, Handler)])

    def test_context_vars(self):
        self.assertEqual(self.ctx_value, self.fetch(self.test_endpoint).body.decode())
