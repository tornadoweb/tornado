from tornado.iostream import IOStream
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, get_unused_port
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
        self.stream.write("GET / HTTP/1.0\r\n\r\n")

        # normal read
        self.stream.read_bytes(9, self.stop)
        data = self.wait()
        self.assertEqual(data, "HTTP/1.0 ")

        # zero bytes
        self.stream.read_bytes(0, self.stop)
        data = self.wait()
        self.assertEqual(data, "")

        # another normal read
        self.stream.read_bytes(3, self.stop)
        data = self.wait()
        self.assertEqual(data, "200")

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

