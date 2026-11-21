import asyncio
import concurrent.futures
import threading
import unittest.mock as mock
from wsgiref.validate import validator

from tornado.log import app_log, gen_log
from tornado.routing import RuleRouter
from tornado.test.util import AsyncHTTPTestCase
from tornado.testing import ExpectLog, gen_test
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


class WSGIValidationTest(AsyncHTTPTestCase):
    def get_app(self):
        def wsgi_app(environ, start_response):
            path = environ.get("PATH_INFO", "")
            if path == "/bad_reason":
                start_response("400 Bad\x00Request", [("Content-Type", "text/plain")])
                return [b"Error\n"]
            elif path == "/bad_header":
                start_response(
                    "200 OK",
                    [("Content-Type", "text/plain"), ("X-Bad", "bad\x00header")],
                )
                return [b"Error\n"]
            elif path == "/whitespace_header":
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", "text/plain"),
                        ("X-Leading", "  leading"),
                        ("X-Trailing", "trailing  "),
                        ("X-Both", "  both  "),
                    ],
                )
                return [b"ok\n"]
            elif path == "/app_exception":
                raise RuntimeError("crash before headers")
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found\n"]

        self.container = WSGIContainer(wsgi_app)
        return self.container

    def test_invalid_status_reason_rejected(self):
        with ExpectLog(gen_log, "Exception in write_headers"):
            response = self.fetch("/bad_reason")
            self.assertEqual(response.code, 500)

    def test_invalid_header_value_rejected(self):
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            response = self.fetch("/bad_header")
            self.assertEqual(response.code, 500)

    def test_header_with_whitespace(self):
        response = self.fetch("/whitespace_header")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.headers["X-Leading"], "leading")
        self.assertEqual(response.headers["X-Trailing"], "trailing")
        self.assertEqual(response.headers["X-Both"], "both")

    def test_app_exception_returns_500(self):
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            response = self.fetch("/app_exception")
            self.assertEqual(response.code, 500)

    def test_exception_after_headers_closes_connection(self):
        with mock.patch.object(
            self.container, "_log", side_effect=RuntimeError("log error")
        ):
            with ExpectLog(app_log, "Exception in WSGIContainer"):
                response = self.fetch("/whitespace_header")
                self.assertEqual(response.code, 200)
