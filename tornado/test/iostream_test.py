from __future__ import absolute_import, division, with_statement
from tornado import netutil
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, get_unused_port
from tornado.util import b
from tornado.web import RequestHandler, Application
import errno
import socket
import sys
import time


class HelloHandler(RequestHandler):
    def get(self):
        self.write("Hello")


class TestIOStream(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/', HelloHandler)])

    def make_iostream_pair(self, **kwargs):
        port = get_unused_port()
        [listener] = netutil.bind_sockets(port, '127.0.0.1',
                                          family=socket.AF_INET)
        streams = [None, None]

        def accept_callback(connection, address):
            streams[0] = IOStream(connection, io_loop=self.io_loop, **kwargs)
            self.stop()

        def connect_callback():
            streams[1] = client_stream
            self.stop()
        netutil.add_accept_handler(listener, accept_callback,
                                   io_loop=self.io_loop)
        client_stream = IOStream(socket.socket(), io_loop=self.io_loop,
                                 **kwargs)
        client_stream.connect(('127.0.0.1', port),
                              callback=connect_callback)
        self.wait(condition=lambda: all(streams))
        self.io_loop.remove_handler(listener.fileno())
        listener.close()
        return streams

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

        s.close()

    def test_write_zero_bytes(self):
        # Attempting to write zero bytes should run the callback without
        # going into an infinite loop.
        server, client = self.make_iostream_pair()
        server.write(b(''), callback=self.stop)
        self.wait()
        # As a side effect, the stream is now listening for connection
        # close (if it wasn't already), but is not listening for writes
        self.assertEqual(server._state, IOLoop.READ | IOLoop.ERROR)
        server.close()
        client.close()

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
        self.assertTrue(isinstance(stream.error, socket.error), stream.error)
        if sys.platform != 'cygwin':
            # cygwin's errnos don't match those used on native windows python
            self.assertEqual(stream.error.args[0], errno.ECONNREFUSED)

    def test_gaierror(self):
        # Test that IOStream sets its exc_info on getaddrinfo error
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        stream = IOStream(s, io_loop=self.io_loop)
        stream.set_close_callback(self.stop)
        stream.connect(('adomainthatdoesntexist.asdf', 54321))
        self.assertTrue(isinstance(stream.error, socket.gaierror), stream.error)

    def test_connection_closed(self):
        # When a server sends a response and then closes the connection,
        # the client must be allowed to read the data before the IOStream
        # closes itself.  Epoll reports closed connections with a separate
        # EPOLLRDHUP event delivered at the same time as the read event,
        # while kqueue reports them as a second read/write event with an EOF
        # flag.
        response = self.fetch("/", headers={"Connection": "close"})
        response.rethrow()

    def test_read_until_close(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        s.connect(("localhost", self.get_http_port()))
        stream = IOStream(s, io_loop=self.io_loop)
        stream.write(b("GET / HTTP/1.0\r\n\r\n"))

        stream.read_until_close(self.stop)
        data = self.wait()
        self.assertTrue(data.startswith(b("HTTP/1.0 200")))
        self.assertTrue(data.endswith(b("Hello")))

    def test_streaming_callback(self):
        server, client = self.make_iostream_pair()
        try:
            chunks = []
            final_called = []

            def streaming_callback(data):
                chunks.append(data)
                self.stop()

            def final_callback(data):
                assert not data
                final_called.append(True)
                self.stop()
            server.read_bytes(6, callback=final_callback,
                              streaming_callback=streaming_callback)
            client.write(b("1234"))
            self.wait(condition=lambda: chunks)
            client.write(b("5678"))
            self.wait(condition=lambda: final_called)
            self.assertEqual(chunks, [b("1234"), b("56")])

            # the rest of the last chunk is still in the buffer
            server.read_bytes(2, callback=self.stop)
            data = self.wait()
            self.assertEqual(data, b("78"))
        finally:
            server.close()
            client.close()

    def test_streaming_until_close(self):
        server, client = self.make_iostream_pair()
        try:
            chunks = []

            def callback(data):
                chunks.append(data)
                self.stop()
            client.read_until_close(callback=callback,
                                    streaming_callback=callback)
            server.write(b("1234"))
            self.wait()
            server.write(b("5678"))
            self.wait()
            server.close()
            self.wait()
            self.assertEqual(chunks, [b("1234"), b("5678"), b("")])
        finally:
            server.close()
            client.close()

    def test_delayed_close_callback(self):
        # The scenario:  Server closes the connection while there is a pending
        # read that can be served out of buffered data.  The client does not
        # run the close_callback as soon as it detects the close, but rather
        # defers it until after the buffered read has finished.
        server, client = self.make_iostream_pair()
        try:
            client.set_close_callback(self.stop)
            server.write(b("12"))
            chunks = []

            def callback1(data):
                chunks.append(data)
                client.read_bytes(1, callback2)
                server.close()

            def callback2(data):
                chunks.append(data)
            client.read_bytes(1, callback1)
            self.wait()  # stopped by close_callback
            self.assertEqual(chunks, [b("1"), b("2")])
        finally:
            server.close()
            client.close()

    def test_close_buffered_data(self):
        # Similar to the previous test, but with data stored in the OS's
        # socket buffers instead of the IOStream's read buffer.  Out-of-band
        # close notifications must be delayed until all data has been
        # drained into the IOStream buffer. (epoll used to use out-of-band
        # close events with EPOLLRDHUP, but no longer)
        #
        # This depends on the read_chunk_size being smaller than the
        # OS socket buffer, so make it small.
        server, client = self.make_iostream_pair(read_chunk_size=256)
        try:
            server.write(b("A") * 512)
            client.read_bytes(256, self.stop)
            data = self.wait()
            self.assertEqual(b("A") * 256, data)
            server.close()
            # Allow the close to propagate to the client side of the
            # connection.  Using add_callback instead of add_timeout
            # doesn't seem to work, even with multiple iterations
            self.io_loop.add_timeout(time.time() + 0.01, self.stop)
            self.wait()
            client.read_bytes(256, self.stop)
            data = self.wait()
            self.assertEqual(b("A") * 256, data)
        finally:
            server.close()
            client.close()

    def test_large_read_until(self):
        # Performance test: read_until used to have a quadratic component
        # so a read_until of 4MB would take 8 seconds; now it takes 0.25
        # seconds.
        server, client = self.make_iostream_pair()
        try:
            NUM_KB = 4096
            for i in xrange(NUM_KB):
                client.write(b("A") * 1024)
            client.write(b("\r\n"))
            server.read_until(b("\r\n"), self.stop)
            data = self.wait()
            self.assertEqual(len(data), NUM_KB * 1024 + 2)
        finally:
            server.close()
            client.close()
