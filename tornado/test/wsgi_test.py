import asyncio
import concurrent.futures
import threading
from unittest.mock import MagicMock
from wsgiref.validate import validator

from tornado import httputil
from tornado.http1connection import HTTP1Connection
from tornado.routing import RuleRouter
from tornado.test.util import AsyncHTTPTestCase, AsyncTestCase
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


class WSGIValidationTest(AsyncTestCase):
    @gen_test
    async def test_invalid_status_reason_rejected(self):
        def bad_status_app(environ, start_response):
            start_response("400 Bad\x00Request", [("Content-Type", "text/plain")])
            return [b"Error\n"]

        container = WSGIContainer(bad_status_app)
        start_line = httputil.RequestStartLine("GET", "/", "HTTP/1.1")
        headers = httputil.HTTPHeaders({"Host": "localhost"})
        mock_stream = MagicMock()
        mock_stream.closed.return_value = False
        conn = HTTP1Connection(mock_stream, is_client=False)
        conn._request_start_line = start_line
        conn._request_headers = headers

        request = httputil.HTTPServerRequest(
            start_line=start_line, headers=headers, connection=conn
        )
        with self.assertRaises(ValueError) as cm:
            await container.handle_request(request)
        self.assertIn("Illegal characters in reason phrase", str(cm.exception))
