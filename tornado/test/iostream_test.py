from tornado.iostream import IOStream
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, get_unused_port
from tornado.util import b
from tornado.web import RequestHandler, Application
import socket

class HelloHandler(RequestHandler):
    def get(self):
        self.write("Hello")

class TestIOStream(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/', HelloHandler)])

    def test_read_zero_bytes(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        s.connect(("localhost", self.get_http_port()))
        self.stream = IOStream(s, io_loop=self.io_loop)
        self.stream.write(b("GET / HTTP/1.0\r\n\r\n"))

        # normal read
        self.stream.read_bytes(9, self.stop)
        data = self.wait()
        self.assertEqual(data, b("HTTP/1.0 "))

        # zero bytes
        self.stream.read_bytes(0, self.stop)
        data = self.wait()
        self.assertEqual(data, b(""))

        # another normal read
        self.stream.read_bytes(3, self.stop)
        data = self.wait()
        self.assertEqual(data, b("200"))

    def test_connection_refused(self):
        # When a connection is refused, the connect callback should not
        # be run.  (The kqueue IOLoop used to behave differently from the
        # epoll IOLoop in this respect)
        port = get_unused_port()
        stream = IOStream(socket.socket(), self.io_loop)
        self.connect_called = False
        def connect_callback():
            self.connect_called = True
        stream.set_close_callback(self.stop)
        stream.connect(("localhost", port), connect_callback)
        self.wait()
        self.assertFalse(self.connect_called)

    def test_connection_closed(self):
        # When a server sends a response and then closes the connection,
        # the client must be allowed to read the data before the IOStream
        # closes itself.  Epoll reports closed connections with a separate
        # EPOLLRDHUP event delivered at the same time as the read event,
        # while kqueue reports them as a second read/write event with an EOF
        # flag.
        response = self.fetch("/", headers={"Connection": "close"})
        response.rethrow()
