import asyncio
import concurrent.futures
import contextvars
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
                ("/host", make_container(self.host_wsgi_app)),
                ("/barrier", make_container(self.barrier_wsgi_app)),
                ("/streaming_barrier", make_container(self.streaming_barrier_wsgi_app)),
            ]
        )

    def respond_plain(self, start_response):
        status = "200 OK"
        response_headers = [("Content-Type", "text/plain")]
        start_response(status, response_headers)

    def host_wsgi_app(self, environ, start_response):
        self.respond_plain(start_response)
        return [("%s %s" % (environ["SERVER_NAME"], environ["SERVER_PORT"])).encode()]

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


class WSGIContainerHostTest(WSGIAppMixin, AsyncHTTPTestCase):
    def get_executor(self):
        return None

    def test_host_with_non_numeric_port(self):
        response = self.fetch("/host", headers={"Host": "example.com:abc"})
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, b"example.com:abc 80")

    def test_ipv6_host(self):
        response = self.fetch("/host", headers={"Host": "[::1]:8000"})
        self.assertEqual(response.body, b"[::1] 8000")

    def test_ipv6_host_without_port(self):
        response = self.fetch("/host", headers={"Host": "[::1]"})
        self.assertEqual(response.body, b"[::1] 80")


class WSGIContainerDummyExecutorTest(WSGIAppMixin, AsyncHTTPTestCase):
    def get_executor(self):
        return None

    def test_simple(self):
        response = self.fetch("/simple")
        self.assertEqual(response.body, b"Hello world!")

    def test_head(self):
        response = self.fetch("/simple", method="HEAD")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.headers["Content-Length"], "12")

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


class WSGIResponseLifecycleTest(AsyncHTTPTestCase):
    def get_app(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.addCleanup(self.executor.shutdown)
        return WSGIContainer(self.application, executor=self.executor)

    def application(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def test_executor_callbacks_share_context(self):
        phase = contextvars.ContextVar("phase", default="unset")
        calls = []

        def record(name):
            calls.append((name, phase.get(), threading.get_ident()))
            phase.set(name)

        class Response:
            def __iter__(self):
                record("iter")
                return self.chunks()

            def chunks(self):
                record("first")
                yield b"first"
                record("second")
                yield b"second"

            def close(self):
                record("close")

        def app(environ, start_response):
            record("app")
            start_response("200 OK", [])
            return Response()

        self.wsgi_app = app
        self.assertEqual(self.fetch("/").body, b"firstsecond")
        self.assertEqual(
            [(name, previous) for name, previous, _ in calls],
            [
                ("app", "unset"),
                ("iter", "app"),
                ("first", "iter"),
                ("second", "first"),
                ("close", "second"),
            ],
        )
        self.assertTrue(all(thread != threading.get_ident() for _, _, thread in calls))

    @gen_test
    async def test_cancellation_waits_for_next_before_closing(self):
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        calls = []

        class Response:
            def __iter__(self):
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(2):
                    raise RuntimeError("test did not release the iterator")
                calls.append("next finished")
                yield b"first"
                calls.append("extra next")

            def close(self):
                calls.append("closed")

        def app(environ, start_response):
            start_response("200 OK", [])
            return Response()

        self.wsgi_app = app
        container = WSGIContainer(self.wsgi_app, executor=self.executor)
        request = HTTPServerRequest(
            start_line=RequestStartLine("GET", "/", "HTTP/1.1"),
            headers=HTTPHeaders({"Host": "localhost"}),
        )
        task = asyncio.create_task(container.handle_request(request))
        try:
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(calls, ["next finished", "closed"])

    @gen_test
    async def test_cancellation_skips_queued_application(self):
        submitted = asyncio.Event()
        release = threading.Event()
        called = threading.Event()

        class NotifyingPool(concurrent.futures.ThreadPoolExecutor):
            def submit(self, fn, /, *args, **kwargs):
                future = super().submit(fn, *args, **kwargs)
                submitted.set()
                return future

        def app(environ, start_response):
            called.set()
            start_response("200 OK", [])
            return []

        pool = NotifyingPool(max_workers=1)
        self.addCleanup(pool.shutdown)
        concurrent.futures.ThreadPoolExecutor.submit(pool, release.wait, 2)
        request = HTTPServerRequest(
            start_line=RequestStartLine("GET", "/", "HTTP/1.1"),
            headers=HTTPHeaders({"Host": "localhost"}),
        )
        task = asyncio.create_task(
            WSGIContainer(app, executor=pool).handle_request(request)
        )
        try:
            await submitted.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), timeout=1)
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        pool.shutdown()
        self.assertFalse(called.is_set())
