import socket

from tornado.http1connection import HTTP1Connection
from tornado.httputil import HTTPMessageDelegate
from tornado.iostream import IOStream
from tornado.locks import Event
from tornado.log import app_log
from tornado.netutil import add_accept_handler
from tornado.test.util import AsyncTestCase
from tornado.testing import ExpectLog, bind_unused_port, gen_test


class HTTP1ConnectionTest(AsyncTestCase):
    code: int | None = None

    def setUp(self):
        super().setUp()
        self.asyncSetUp()

    @gen_test
    def asyncSetUp(self):
        listener, port = bind_unused_port()
        event = Event()

        def accept_callback(conn, addr):
            self.server_stream = IOStream(conn)
            self.addCleanup(self.server_stream.close)
            event.set()

        add_accept_handler(listener, accept_callback)
        self.client_stream = IOStream(socket.socket())
        self.addCleanup(self.client_stream.close)
        yield [self.client_stream.connect(("127.0.0.1", port)), event.wait()]
        self.io_loop.remove_handler(listener)
        listener.close()

    @gen_test
    def test_1xx_does_not_read_a_second_body(self):
        # An informational (1xx) response is followed by the real response,
        # which is read by a recursive call to _read_message. Once that
        # returns, the outer call has nothing left to do: it must not fall
        # through and read a second body, which would finish the delegate
        # a second time and start a spurious read-until-close.
        conn = HTTP1Connection(self.client_stream, True)
        self.server_stream.write(b"HTTP/1.1 100 CONTINUE\r\n\r\n")
        self.server_stream.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello")
        self.server_stream.close()

        body = []
        finish_count = []
        close_count = []

        class Delegate(HTTPMessageDelegate):
            def data_received(self, data):
                body.append(data)

            def finish(self):
                finish_count.append(1)

            def on_connection_close(self):
                close_count.append(1)

        yield conn.read_response(Delegate())
        self.assertEqual(b"".join(body), b"hello")
        self.assertEqual(len(finish_count), 1)
        # The delegate finished normally, so it must not also be told the
        # connection closed on it.
        self.assertEqual(len(close_count), 0)

    @gen_test
    def test_http10_no_content_length(self):
        # Regression test for a bug in which can_keep_alive would crash
        # for an HTTP/1.0 (not 1.1) response with no content-length.
        conn = HTTP1Connection(self.client_stream, True)
        self.server_stream.write(b"HTTP/1.0 200 Not Modified\r\n\r\nhello")
        self.server_stream.close()

        event = Event()
        test = self
        body = []

        class Delegate(HTTPMessageDelegate):
            def headers_received(self, start_line, headers):
                test.code = start_line.code

            def data_received(self, data):
                body.append(data)

            def finish(self):
                event.set()

        yield conn.read_response(Delegate())
        yield event.wait()
        self.assertEqual(self.code, 200)
        self.assertEqual(b"".join(body), b"hello")

    def check_delegate_error(self, method):
        # If a delegate method raises, the exception is logged, the delegate is
        # told that the connection is closed, and read_response returns False
        # (rather than raising) with the connection closed.
        conn = HTTP1Connection(self.client_stream, True)
        self.server_stream.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello")
        close_count = []

        class Delegate(HTTPMessageDelegate):
            def headers_received(self, start_line, headers):
                if method == "headers_received":
                    raise ValueError("error in headers_received")

            def data_received(self, chunk):
                if method == "data_received":
                    raise ValueError("error in data_received")

            def finish(self):
                if method == "finish":
                    raise ValueError("error in finish")

            def on_connection_close(self):
                close_count.append(1)

        with ExpectLog(app_log, "Uncaught exception"):
            result = yield conn.read_response(Delegate())
        self.assertIs(result, False)
        self.assertEqual(len(close_count), 1)
        self.assertTrue(self.client_stream.closed())

    @gen_test
    def test_error_in_headers_received(self):
        yield from self.check_delegate_error("headers_received")

    @gen_test
    def test_error_in_data_received(self):
        yield from self.check_delegate_error("data_received")

    @gen_test
    def test_error_in_finish(self):
        yield from self.check_delegate_error("finish")
