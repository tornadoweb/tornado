import asyncio
import concurrent.futures
import socket
import threading
import unittest.mock as mock
from wsgiref.validate import validator

from tornado.httputil import HTTPHeaders
from tornado.iostream import IOStream, StreamClosedError
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

        # The validator rejects the app before WSGIContainer can see its body,
        # so the body-error cases use the container directly.
        def make_raw_container(app):
            return WSGIContainer(app, executor=executor)

        return RuleRouter(
            [
                ("/simple", make_container(self.simple_wsgi_app)),
                ("/host", make_container(self.host_wsgi_app)),
                ("/barrier", make_container(self.barrier_wsgi_app)),
                ("/streaming_barrier", make_container(self.streaming_barrier_wsgi_app)),
                ("/no_content", make_container(self.no_content_wsgi_app)),
                (
                    "/no_content_with_body",
                    make_raw_container(self.no_content_with_body_wsgi_app),
                ),
                (
                    "/early_hints_with_body",
                    make_raw_container(self.early_hints_with_body_wsgi_app),
                ),
                ("/not_modified", make_container(self.not_modified_wsgi_app)),
                (
                    "/not_modified_with_content_length",
                    make_container(self.not_modified_with_content_length_wsgi_app),
                ),
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

    def no_content_wsgi_app(self, environ, start_response):
        start_response("204 No Content", [("Content-Length", "4")])
        return []

    def no_content_with_body_wsgi_app(self, environ, start_response):
        start_response("204 No Content", [])
        return [b"body"]

    def early_hints_with_body_wsgi_app(self, environ, start_response):
        start_response("103 Early Hints", [])
        return [b"body"]

    def not_modified_wsgi_app(self, environ, start_response):
        start_response("304 Not Modified", [])
        return [b"body"]

    def not_modified_with_content_length_wsgi_app(self, environ, start_response):
        start_response("304 Not Modified", [("Content-Length", "12")])
        return [b"body"]


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

    def test_no_content(self):
        response = self.fetch("/no_content")
        self.assertEqual(response.code, 204)
        self.assertEqual(response.body, b"")
        self.assertNotIn("Content-Length", response.headers)
        self.assertNotIn("Content-Type", response.headers)

    def test_no_content_with_body_is_an_error(self):
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            response = self.fetch("/no_content_with_body")
        self.assertEqual(response.code, 500)

    def test_1xx_with_body_is_an_error(self):
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            response = self.fetch("/early_hints_with_body")
        self.assertEqual(response.code, 500)

    def test_not_modified(self):
        response = self.fetch("/not_modified")
        self.assertEqual(response.code, 304)
        self.assertEqual(response.body, b"")
        self.assertNotIn("Content-Length", response.headers)

    def test_not_modified_with_content_length(self):
        response = self.fetch("/not_modified_with_content_length")
        self.assertEqual(response.code, 304)
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
            elif path == "/odd_reason":
                start_response("200 A <b>r\xe9ason</b>", [("Content-Length", "2")])
                return [b"ok"]
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
        # HTTPHeaders rejects the value as WSGIContainer builds the
        # response, before anything reaches HTTP1Connection.write_headers,
        # so this exercises WSGIContainer's own error handling. The
        # write_headers checks are covered in http1connection_test.
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            response = self.fetch("/bad_header")
            self.assertEqual(response.code, 500)

    def test_unusual_reason_phrase_allowed(self):
        # obs-text and "<" are valid in a reason phrase. (PEP 3333 says the
        # status is a Latin-1 string, and that's how it is sent.) Only
        # RequestHandler.set_status rejects "<", to protect its HTML error
        # page; WSGIContainer passes the app's reason through.
        response = self.fetch("/odd_reason")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.reason, "A <b>r\xe9ason</b>")
        self.assertEqual(response.body, b"ok")

    @gen_test
    async def test_keep_alive_after_error(self):
        # An error that WSGIContainer catches before sending anything gets a
        # clean 500 and leaves the connection usable. An invalid reason
        # phrase is only caught by write_headers, which closes the
        # connection after its 500.
        stream = IOStream(socket.socket())
        await stream.connect(("127.0.0.1", self.get_http_port()))
        self.addCleanup(stream.close)

        async def get(path):
            await stream.write(b"GET %s HTTP/1.1\r\nHost: x\r\n\r\n" % path)
            header_data = await stream.read_until(b"\r\n\r\n")
            start_line, header_block = header_data.decode("latin1").split("\r\n", 1)
            headers = HTTPHeaders.parse(header_block)
            body = await stream.read_bytes(int(headers["Content-Length"]))
            return start_line, headers, body

        with ExpectLog(app_log, "Exception in WSGIContainer"):
            start_line, headers, _ = await get(b"/bad_header")
        self.assertEqual(start_line, "HTTP/1.1 500 Internal Server Error")
        self.assertNotIn("Connection", headers)
        with ExpectLog(app_log, "Exception in WSGIContainer"):
            start_line, _, _ = await get(b"/app_exception")
        self.assertEqual(start_line, "HTTP/1.1 500 Internal Server Error")
        start_line, _, body = await get(b"/whitespace_header")
        self.assertEqual(start_line, "HTTP/1.1 200 OK")
        self.assertEqual(body, b"ok\n")

        with ExpectLog(gen_log, "Exception in write_headers"):
            start_line, headers, _ = await get(b"/bad_reason")
        self.assertEqual(start_line, "HTTP/1.1 500 Internal Server Error")
        self.assertEqual(headers["Connection"], "close")
        with self.assertRaises(StreamClosedError):
            await stream.read_bytes(1)

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
