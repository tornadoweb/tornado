import socket

from tornado.http1connection import HTTP1Connection
from tornado.httputil import HTTPMessageDelegate
from tornado.iostream import IOStream
from tornado.locks import Event
from tornado.netutil import add_accept_handler
from tornado.testing import AsyncTestCase, bind_unused_port, gen_test


class HTTP1ConnectionTest(AsyncTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        listener, port = bind_unused_port()
        event = Event()

        def accept_callback(conn, addr):
            self.server_stream = IOStream(conn)
            self.addCleanup(self.server_stream.close)
            event.set()

        add_accept_handler(listener, accept_callback)
        self.client_stream = IOStream(socket.socket())
        self.addCleanup(self.client_stream.close)
        await self.client_stream.connect(("127.0.0.1", port))
        await event.wait()
        self.io_loop.remove_handler(listener)
        listener.close()

    @gen_test
    async def test_http10_no_content_length(self):
        # Regression test for a bug in which can_keep_alive would crash
        # for an HTTP/1.0 (not 1.1) response with no content-length.
        conn = HTTP1Connection(self.client_stream, True)
        self.server_stream.write(b"HTTP/1.0 200 Not Modified\r\n\r\nhello")
        self.server_stream.close()

        event = Event()
        code = None
        body = []

        class Delegate(HTTPMessageDelegate):
            def headers_received(self, start_line, headers):
                nonlocal code
                code = start_line.code

            def data_received(self, data):
                body.append(data)

            def finish(self):
                event.set()

        await conn.read_response(Delegate())
        await event.wait()
        self.assertEqual(code, 200)
        self.assertEqual(b"".join(body), b"hello")
