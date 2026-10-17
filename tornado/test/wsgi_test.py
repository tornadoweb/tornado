import asyncio
import concurrent.futures
import sys
import threading
from wsgiref.validate import validator

from tornado.httputil import HTTPHeaders, HTTPServerRequest, RequestStartLine
from tornado.routing import RuleRouter
from tornado.test.util import AsyncHTTPTestCase
from tornado.testing import gen_test
from tornado.wsgi import WSGIContainer


class WSGIAppMixin:
    # TODO: Now that WSGIAdapter is gone, this is a pretty weak test.
    def get_executor(self):
        raise NotImplementedError()

    def get_app(self):
        executor = self.get_executor()
        # The barrier test in DummyExecutorTest will always wait the full
        # value of this timeout, so we don't want it to be too high.
        self.barrier = threading.Barrier(2, timeout=0.3)

        def make_container(app):
            return WSGIContainer(validator(app), executor=executor)

        return RuleRouter(
            [
                ("/simple", make_container(self.simple_wsgi_app)),
                ("/barrier", make_container(self.barrier_wsgi_app)),
                ("/streaming_barrier", make_container(self.streaming_barrier_wsgi_app)),
            ]
        )

    def respond_plain(self, start_response):
        status = "200 OK"
        response_headers = [("Content-Type", "text/plain")]
        start_response(status, response_headers)

    def simple_wsgi_app(self, environ, start_response):
        self.respond_plain(start_response)
        return [b"Hello world!"]

    def barrier_wsgi_app(self, environ, start_response):
        self.respond_plain(start_response)
        try:
            n = self.barrier.wait()
        except threading.BrokenBarrierError:
            return [b"broken barrier"]
        else:
            return [b"ok %d" % n]

    def streaming_barrier_wsgi_app(self, environ, start_response):
        self.respond_plain(start_response)
        yield b"ok "
        try:
            n = self.barrier.wait()
        except threading.BrokenBarrierError:
            yield b"broken barrier"
        else:
            yield b"%d" % n


class WSGIContainerDummyExecutorTest(WSGIAppMixin, AsyncHTTPTestCase):
    def get_executor(self):
        return None

    def test_simple(self):
        response = self.fetch("/simple")
        self.assertEqual(response.body, b"Hello world!")

    @gen_test
    async def test_concurrent_barrier(self):
        self.barrier.reset()
        resps = await asyncio.gather(
            self.http_client.fetch(self.get_url("/barrier")),
            self.http_client.fetch(self.get_url("/barrier")),
        )
        for resp in resps:
            self.assertEqual(resp.body, b"broken barrier")

    @gen_test
    async def test_concurrent_streaming_barrier(self):
        self.barrier.reset()
        resps = await asyncio.gather(
            self.http_client.fetch(self.get_url("/streaming_barrier")),
            self.http_client.fetch(self.get_url("/streaming_barrier")),
        )
        for resp in resps:
            self.assertEqual(resp.body, b"ok broken barrier")


class WSGIContainerThreadPoolTest(WSGIAppMixin, AsyncHTTPTestCase):
    def get_executor(self):
        return concurrent.futures.ThreadPoolExecutor()

    def test_simple(self):
        response = self.fetch("/simple")
        self.assertEqual(response.body, b"Hello world!")

    @gen_test
    async def test_concurrent_barrier(self):
        self.barrier.reset()
        resps = await asyncio.gather(
            self.http_client.fetch(self.get_url("/barrier")),
            self.http_client.fetch(self.get_url("/barrier")),
        )
        self.assertEqual([b"ok 0", b"ok 1"], sorted([resp.body for resp in resps]))

    @gen_test
    async def test_concurrent_streaming_barrier(self):
        self.barrier.reset()
        resps = await asyncio.gather(
            self.http_client.fetch(self.get_url("/streaming_barrier")),
            self.http_client.fetch(self.get_url("/streaming_barrier")),
        )
        self.assertEqual([b"ok 0", b"ok 1"], sorted([resp.body for resp in resps]))


class WSGIIterableExecutorTest(AsyncHTTPTestCase):
    def get_app(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown)
        self.calls: list[tuple[str, int]] = []

        calls = self.calls

        class Response:
            def __iter__(self):
                calls.append(("iter", threading.get_ident()))
                return iter([b"Hello world!"])

            def close(self):
                calls.append(("close", threading.get_ident()))

        def app(environ, start_response):
            calls.append(("app", threading.get_ident()))
            start_response("200 OK", [("Content-Type", "text/plain")])
            return Response()

        return WSGIContainer(app, executor=self.executor)

    def test_iterable_callbacks(self):
        response = self.fetch("/")
        self.assertEqual(response.body, b"Hello world!")
        self.assertEqual([name for name, _ in self.calls], ["app", "iter", "close"])
        worker = self.calls[0][1]
        self.assertNotEqual(worker, threading.get_ident())
        for name, thread in self.calls[1:]:
            with self.subTest(callback=name):
                self.assertEqual(thread, worker)

    @gen_test
    async def test_close_after_iteration_error(self):
        for fail_in in ("iter", "next"):
            with self.subTest(fail_in=fail_in):
                self.calls.clear()
                calls = self.calls

                class Response:
                    def __iter__(self):
                        if fail_in == "iter":
                            raise RuntimeError("iteration failed")
                        return self

                    def __next__(self):
                        raise RuntimeError("iteration failed")

                    def close(self):
                        calls.append(("close", threading.get_ident()))

                container = WSGIContainer(
                    lambda environ, start_response: Response(), executor=self.executor
                )
                with self.assertRaisesRegex(RuntimeError, "iteration failed"):
                    await container.handle_request(
                        HTTPServerRequest(
                            start_line=RequestStartLine("GET", "/", "HTTP/1.1"),
                            headers=HTTPHeaders({"Host": "localhost"}),
                        )
                    )
                self.assertEqual([name for name, _ in self.calls], ["close"])
                self.assertNotEqual(self.calls[0][1], threading.get_ident())


class WSGILifecycleTest(AsyncHTTPTestCase):
    def get_app(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.addCleanup(self.executor.shutdown)
        self.container = WSGIContainer(
            lambda environ, start_response: self.app(environ, start_response),
            executor=self.executor,
        )
        return self.container

    @gen_test
    async def test_cleanup_before_queued_application(self):
        at_eof = asyncio.Event()
        second_queued = threading.Event()
        closed = threading.Event()
        loop = asyncio.get_running_loop()

        class RecordingPool(concurrent.futures.ThreadPoolExecutor):
            def submit(self, fn, /, *args, **kwargs):
                result = super().submit(fn, *args, **kwargs)
                if at_eof.is_set():
                    second_queued.set()
                return result

        pool = RecordingPool(max_workers=1)
        self.addCleanup(pool.shutdown)
        # Use this pool for the HTTP container, without changing its scheduling.
        self.container.executor = pool

        class Response:
            sent = False

            def __iter__(self):
                return self

            def __next__(self):
                if not self.sent:
                    self.sent = True
                    return b"A"
                loop.call_soon_threadsafe(at_eof.set)
                if not second_queued.wait(2):
                    raise RuntimeError("second request was not queued")
                raise StopIteration

            def close(self):
                closed.set()

        def app(environ, start_response):
            start_response("200 OK", [])
            if environ["PATH_INFO"] == "/a":
                return Response()
            # The bound only lets a broken implementation escape its deadlock.
            return [b"released" if closed.wait(1) else b"cleanup starved"]

        self.app = app
        first = self.http_client.fetch(self.get_url("/a"))
        await at_eof.wait()
        second = self.http_client.fetch(self.get_url("/b"))
        responses = await asyncio.gather(first, second)
        self.assertEqual([r.body for r in responses], [b"A", b"released"])

    @gen_test
    async def test_cancellation_orders_cleanup(self):
        # Two workers allow a separately submitted close to overtake initialization.
        loop = asyncio.get_running_loop()
        for phase in ("app", "iter", "next", "close"):
            with self.subTest(phase=phase):
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
                self.addCleanup(pool.shutdown)
                entered = asyncio.Event()
                finished = asyncio.Event()
                closed = asyncio.Event()
                release = threading.Event()
                resource = []
                close_states = []

                def block():
                    loop.call_soon_threadsafe(entered.set)
                    if not release.wait(2):
                        raise RuntimeError("operation was not released")
                    resource.append("open")
                    loop.call_soon_threadsafe(finished.set)

                class Response:
                    def __iter__(self):
                        if phase == "iter":
                            block()
                        return self

                    def __next__(self):
                        if phase == "next":
                            block()
                        raise StopIteration

                    def close(self):
                        if phase == "close":
                            block()
                        close_states.append(list(resource))
                        resource.clear()
                        loop.call_soon_threadsafe(closed.set)

                def app(environ, start_response):
                    start_response("200 OK", [])
                    if phase == "app":
                        block()
                    return Response()

                task = asyncio.create_task(
                    WSGIContainer(app, executor=pool).handle_request(
                        HTTPServerRequest(
                            start_line=RequestStartLine("GET", "/", "HTTP/1.1"),
                            headers=HTTPHeaders({"Host": "localhost"}),
                        )
                    )
                )
                try:
                    await entered.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    # Task cancellation has been delivered while the worker is held.
                    early_close = list(close_states)
                finally:
                    release.set()
                await finished.wait()
                # Drain worker jobs before asserting, including on broken versions
                # which lose the application result entirely on cancellation.
                pool.shutdown(wait=True)
                await asyncio.sleep(0)
                self.assertEqual(early_close, [])
                self.assertTrue(closed.is_set())
                self.assertEqual(close_states, [["open"]])
                self.assertEqual(resource, [])

    @gen_test
    async def test_blocking_callbacks_allow_loop_progress(self):
        loop = asyncio.get_running_loop()
        progress = []

        def checkpoint(name):
            released = threading.Event()

            def on_loop():
                progress.append(name)
                released.set()

            loop.call_soon_threadsafe(on_loop)
            if not released.wait(1):
                raise RuntimeError("event loop did not progress")

        class Response:
            def __iter__(self):
                checkpoint("iter")
                return iter([b"ok"])

            def close(self):
                checkpoint("close")

        def app(environ, start_response):
            checkpoint("app")
            start_response("200 OK", [])
            return Response()

        self.app = app
        response = await self.http_client.fetch(self.get_url("/"))
        self.assertEqual(response.body, b"ok")
        self.assertEqual(progress, ["app", "iter", "close"])

    @gen_test
    async def test_write_and_lazy_start_response(self):
        def app(environ, start_response):
            write = start_response("201 Created", [("X-Old", "old")])
            write(b"a")
            yield b"b"
            try:
                raise ValueError("replace buffered headers")
            except ValueError:
                write = start_response(
                    "202 Accepted", [("X-New", "new")], sys.exc_info()
                )
            write(b"c")
            yield b"d"

        self.app = app
        response = await self.http_client.fetch(self.get_url("/"))
        self.assertEqual(response.code, 202)
        self.assertEqual(response.body, b"abcd")
        self.assertEqual(response.headers["X-New"], "new")
        self.assertNotIn("X-Old", response.headers)
        self.assertEqual(response.headers["Content-Length"], "4")

    @gen_test
    async def test_error_cleanup(self):
        for phase in (
            "app",
            "iter",
            "next",
            "close",
            "iter_and_close",
            "missing_start",
            "iter_stop",
            "close_stop",
        ):
            with self.subTest(phase=phase):
                calls = []

                class Response:
                    def __iter__(self):
                        calls.append("iter")
                        if phase in ("iter", "iter_and_close"):
                            raise RuntimeError("iter failed")
                        if phase == "iter_stop":
                            raise StopIteration("iter failed")
                        return self

                    def __next__(self):
                        calls.append("next")
                        if phase == "next":
                            raise RuntimeError("next failed")
                        raise StopIteration

                    def close(self):
                        calls.append("close")
                        if phase in ("close", "iter_and_close"):
                            raise RuntimeError("close failed")
                        if phase == "close_stop":
                            raise StopIteration("close failed")

                def app(environ, start_response):
                    calls.append("app")
                    if phase == "app":
                        raise RuntimeError("app failed")
                    if phase != "missing_start":
                        start_response("200 OK", [])
                    return Response()

                container = WSGIContainer(app, executor=self.executor)
                with self.assertRaises(Exception) as cm:
                    await container.handle_request(
                        HTTPServerRequest(
                            start_line=RequestStartLine("GET", "/", "HTTP/1.1"),
                            headers=HTTPHeaders({"Host": "localhost"}),
                        )
                    )
                if phase == "app":
                    self.assertEqual(calls, ["app"])
                else:
                    self.assertEqual(calls[-1], "close")
                    self.assertEqual(calls.count("close"), 1)
                if phase == "iter_and_close":
                    self.assertEqual(str(cm.exception), "close failed")
                    self.assertEqual(str(cm.exception.__context__), "iter failed")
                elif phase.endswith("_stop"):
                    self.assertIsInstance(cm.exception, RuntimeError)
                    self.assertIsInstance(cm.exception.__cause__, StopIteration)
                elif phase == "missing_start":
                    self.assertEqual(
                        str(cm.exception), "WSGI app did not call start_response"
                    )
                else:
                    self.assertEqual(str(cm.exception), phase + " failed")

    @gen_test
    async def test_concurrent_lifecycles(self):
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.addCleanup(pool.shutdown)
        self.container.executor = pool
        barrier = threading.Barrier(2, timeout=2)
        calls = {}

        def app(environ, start_response):
            key = environ["PATH_INFO"]
            events = calls[key] = [("app", threading.get_ident())]
            start_response("200 OK", [])
            barrier.wait()

            class Response:
                sent = False

                def __iter__(self):
                    events.append(("iter", threading.get_ident()))
                    return self

                def __next__(self):
                    events.append(("next", threading.get_ident()))
                    if self.sent:
                        raise StopIteration
                    self.sent = True
                    return key.encode()

                def close(self):
                    events.append(("close", threading.get_ident()))

            return Response()

        self.app = app
        responses = await asyncio.gather(
            self.http_client.fetch(self.get_url("/a")),
            self.http_client.fetch(self.get_url("/b")),
        )
        self.assertEqual([r.body for r in responses], [b"/a", b"/b"])
        for events in calls.values():
            self.assertEqual(
                [name for name, _ in events], ["app", "iter", "next", "next", "close"]
            )
            self.assertEqual(len({thread for _, thread in events}), 1)
            self.assertNotEqual(events[0][1], threading.get_ident())
        self.assertNotEqual(calls["/a"][0][1], calls["/b"][0][1])
