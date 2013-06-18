from __future__ import absolute_import, division, print_function, with_statement
from tornado import netutil
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream, SSLIOStream, PipeIOStream
from tornado.log import gen_log, app_log
from tornado.netutil import ssl_wrap_socket
from tornado.stack_context import NullContext
from tornado.testing import AsyncHTTPTestCase, AsyncHTTPSTestCase, AsyncTestCase, bind_unused_port, ExpectLog
from tornado.test.util import unittest, skipIfNonUnix
from tornado.web import RequestHandler, Application
import errno
import logging
import os
import platform
import socket
import ssl
import sys


class HelloHandler(RequestHandler):
    def get(self):
        self.write("Hello")


class TestIOStreamWebMixin(object):
    def _make_client_iostream(self):
        raise NotImplementedError()

    def get_app(self):
        return Application([('/', HelloHandler)])

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
        stream = self._make_client_iostream()
        stream.connect(('localhost', self.get_http_port()), callback=self.stop)
        self.wait()
        stream.write(b"GET / HTTP/1.0\r\n\r\n")

        stream.read_until_close(self.stop)
        data = self.wait()
        self.assertTrue(data.startswith(b"HTTP/1.0 200"))
        self.assertTrue(data.endswith(b"Hello"))

    def test_read_zero_bytes(self):
        self.stream = self._make_client_iostream()
        self.stream.connect(("localhost", self.get_http_port()),
                            callback=self.stop)
        self.wait()
        self.stream.write(b"GET / HTTP/1.0\r\n\r\n")

        # normal read
        self.stream.read_bytes(9, self.stop)
        data = self.wait()
        self.assertEqual(data, b"HTTP/1.0 ")

        # zero bytes
        self.stream.read_bytes(0, self.stop)
        data = self.wait()
        self.assertEqual(data, b"")

        # another normal read
        self.stream.read_bytes(3, self.stop)
        data = self.wait()
        self.assertEqual(data, b"200")

        self.stream.close()

    def test_write_while_connecting(self):
        stream = self._make_client_iostream()
        connected = [False]

        def connected_callback():
            connected[0] = True
            self.stop()
        stream.connect(("localhost", self.get_http_port()),
                       callback=connected_callback)
        # unlike the previous tests, try to write before the connection
        # is complete.
        written = [False]

        def write_callback():
            written[0] = True
            self.stop()
        stream.write(b"GET / HTTP/1.0\r\nConnection: close\r\n\r\n",
                     callback=write_callback)
        self.assertTrue(not connected[0])
        # by the time the write has flushed, the connection callback has
        # also run
        try:
            self.wait(lambda: connected[0] and written[0])
        finally:
            logging.debug((connected, written))

        stream.read_until_close(self.stop)
        data = self.wait()
        self.assertTrue(data.endswith(b"Hello"))

        stream.close()


class TestIOStreamMixin(object):
    def _make_server_iostream(self, connection, **kwargs):
        raise NotImplementedError()

    def _make_client_iostream(self, connection, **kwargs):
        raise NotImplementedError()

    def make_iostream_pair(self, **kwargs):
        listener, port = bind_unused_port()
        streams = [None, None]

        def accept_callback(connection, address):
            streams[0] = self._make_server_iostream(connection, **kwargs)
            if isinstance(streams[0], SSLIOStream):
                # HACK: The SSL handshake won't complete (and
                # therefore the client connect callback won't be
                # run)until the server side has tried to do something
                # with the connection.  For these tests we want both
                # sides to connect before we do anything else with the
                # connection, so we must cause some dummy activity on the
                # server.  If this turns out to be useful for real apps
                # it should have a cleaner interface.
                streams[0]._add_io_state(IOLoop.READ)
            self.stop()

        def connect_callback():
            streams[1] = client_stream
            self.stop()
        netutil.add_accept_handler(listener, accept_callback,
                                   io_loop=self.io_loop)
        client_stream = self._make_client_iostream(socket.socket(), **kwargs)
        client_stream.connect(('127.0.0.1', port),
                              callback=connect_callback)
        self.wait(condition=lambda: all(streams))
        self.io_loop.remove_handler(listener.fileno())
        listener.close()
        return streams

    def test_streaming_callback_with_data_in_buffer(self):
        server, client = self.make_iostream_pair()
        client.write(b"abcd\r\nefgh")
        server.read_until(b"\r\n", self.stop)
        data = self.wait()
        self.assertEqual(data, b"abcd\r\n")

        def closed_callback(chunk):
            self.fail()
        server.read_until_close(callback=closed_callback,
                                streaming_callback=self.stop)
        # self.io_loop.add_timeout(self.io_loop.time() + 0.01, self.stop)
        data = self.wait()
        self.assertEqual(data, b"efgh")
        server.close()
        client.close()

    def test_write_zero_bytes(self):
        # Attempting to write zero bytes should run the callback without
        # going into an infinite loop.
        server, client = self.make_iostream_pair()
        server.write(b'', callback=self.stop)
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
        server_socket, port = bind_unused_port()
        server_socket.close()
        stream = IOStream(socket.socket(), self.io_loop)
        self.connect_called = False

        def connect_callback():
            self.connect_called = True
        stream.set_close_callback(self.stop)
        # log messages vary by platform and ioloop implementation
        with ExpectLog(gen_log, ".*", required=False):
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
        # To reliably generate a gaierror we use a malformed domain name
        # instead of a name that's simply unlikely to exist (since
        # opendns and some ISPs return bogus addresses for nonexistent
        # domains instead of the proper error codes).
        with ExpectLog(gen_log, "Connect error"):
            stream.connect(('an invalid domain', 54321))
            self.assertTrue(isinstance(stream.error, socket.gaierror), stream.error)

    def test_read_callback_error(self):
        # Test that IOStream sets its exc_info when a read callback throws
        server, client = self.make_iostream_pair()
        try:
            server.set_close_callback(self.stop)
            with ExpectLog(
                app_log, "(Uncaught exception|Exception in callback)"
            ):
                # Clear ExceptionStackContext so IOStream catches error
                with NullContext():
                    server.read_bytes(1, callback=lambda data: 1 / 0)
                client.write(b"1")
                self.wait()
            self.assertTrue(isinstance(server.error, ZeroDivisionError))
        finally:
            server.close()
            client.close()

    def test_streaming_callback(self):
        server, client = self.make_iostream_pair()
        try:
            chunks = []
            final_called = []

            def streaming_callback(data):
                chunks.append(data)
                self.stop()

            def final_callback(data):
                self.assertFalse(data)
                final_called.append(True)
                self.stop()
            server.read_bytes(6, callback=final_callback,
                              streaming_callback=streaming_callback)
            client.write(b"1234")
            self.wait(condition=lambda: chunks)
            client.write(b"5678")
            self.wait(condition=lambda: final_called)
            self.assertEqual(chunks, [b"1234", b"56"])

            # the rest of the last chunk is still in the buffer
            server.read_bytes(2, callback=self.stop)
            data = self.wait()
            self.assertEqual(data, b"78")
        finally:
            server.close()
            client.close()

    def test_streaming_until_close(self):
        server, client = self.make_iostream_pair()
        try:
            chunks = []
            closed = [False]

            def streaming_callback(data):
                chunks.append(data)
                self.stop()
            def close_callback(data):
                assert not data, data
                closed[0] = True
                self.stop()
            client.read_until_close(callback=close_callback,
                                    streaming_callback=streaming_callback)
            server.write(b"1234")
            self.wait(condition=lambda: len(chunks) == 1)
            server.write(b"5678", self.stop)
            self.wait()
            server.close()
            self.wait(condition=lambda: closed[0])
            self.assertEqual(chunks, [b"1234", b"5678"])
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
            server.write(b"12")
            chunks = []

            def callback1(data):
                chunks.append(data)
                client.read_bytes(1, callback2)
                server.close()

            def callback2(data):
                chunks.append(data)
            client.read_bytes(1, callback1)
            self.wait()  # stopped by close_callback
            self.assertEqual(chunks, [b"1", b"2"])
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
            server.write(b"A" * 512)
            client.read_bytes(256, self.stop)
            data = self.wait()
            self.assertEqual(b"A" * 256, data)
            server.close()
            # Allow the close to propagate to the client side of the
            # connection.  Using add_callback instead of add_timeout
            # doesn't seem to work, even with multiple iterations
            self.io_loop.add_timeout(self.io_loop.time() + 0.01, self.stop)
            self.wait()
            client.read_bytes(256, self.stop)
            data = self.wait()
            self.assertEqual(b"A" * 256, data)
        finally:
            server.close()
            client.close()

    def test_read_until_close_after_close(self):
        # Similar to test_delayed_close_callback, but read_until_close takes
        # a separate code path so test it separately.
        server, client = self.make_iostream_pair()
        client.set_close_callback(self.stop)
        try:
            server.write(b"1234")
            server.close()
            self.wait()
            client.read_until_close(self.stop)
            data = self.wait()
            self.assertEqual(data, b"1234")
        finally:
            server.close()
            client.close()

    def test_streaming_read_until_close_after_close(self):
        # Same as the preceding test but with a streaming_callback.
        # All data should go through the streaming callback,
        # and the final read callback just gets an empty string.
        server, client = self.make_iostream_pair()
        client.set_close_callback(self.stop)
        try:
            server.write(b"1234")
            server.close()
            self.wait()
            streaming_data = []
            client.read_until_close(self.stop,
                                    streaming_callback=streaming_data.append)
            data = self.wait()
            self.assertEqual(b'', data)
            self.assertEqual(b''.join(streaming_data), b"1234")
        finally:
            server.close()
            client.close()

    def test_large_read_until(self):
        # Performance test: read_until used to have a quadratic component
        # so a read_until of 4MB would take 8 seconds; now it takes 0.25
        # seconds.
        server, client = self.make_iostream_pair()
        try:
            # This test fails on pypy with ssl.  I think it's because
            # pypy's gc defeats moves objects, breaking the
            # "frozen write buffer" assumption.
            if (isinstance(server, SSLIOStream) and
                    platform.python_implementation() == 'PyPy'):
                raise unittest.SkipTest(
                    "pypy gc causes problems with openssl")
            NUM_KB = 4096
            for i in range(NUM_KB):
                client.write(b"A" * 1024)
            client.write(b"\r\n")
            server.read_until(b"\r\n", self.stop)
            data = self.wait()
            self.assertEqual(len(data), NUM_KB * 1024 + 2)
        finally:
            server.close()
            client.close()

    def test_close_callback_with_pending_read(self):
        # Regression test for a bug that was introduced in 2.3
        # where the IOStream._close_callback would never be called
        # if there were pending reads.
        OK = b"OK\r\n"
        server, client = self.make_iostream_pair()
        client.set_close_callback(self.stop)
        try:
            server.write(OK)
            client.read_until(b"\r\n", self.stop)
            res = self.wait()
            self.assertEqual(res, OK)

            server.close()
            client.read_until(b"\r\n", lambda x: x)
            # If _close_callback (self.stop) is not called,
            # an AssertionError: Async operation timed out after 5 seconds
            # will be raised.
            res = self.wait()
            self.assertTrue(res is None)
        finally:
            server.close()
            client.close()

    @skipIfNonUnix
    def test_inline_read_error(self):
        # An error on an inline read is raised without logging (on the
        # assumption that it will eventually be noticed or logged further
        # up the stack).
        #
        # This test is posix-only because windows os.close() doesn't work
        # on socket FDs, but we can't close the socket object normally
        # because we won't get the error we want if the socket knows
        # it's closed.
        server, client = self.make_iostream_pair()
        try:
            os.close(server.socket.fileno())
            with self.assertRaises(socket.error):
                server.read_bytes(1, lambda data: None)
        finally:
            server.close()
            client.close()

    def test_async_read_error_logging(self):
        # Socket errors on asynchronous reads should be logged (but only
        # once).
        server, client = self.make_iostream_pair()
        server.set_close_callback(self.stop)
        try:
            # Start a read that will be fullfilled asynchronously.
            server.read_bytes(1, lambda data: None)
            client.write(b'a')
            # Stub out read_from_fd to make it fail.

            def fake_read_from_fd():
                os.close(server.socket.fileno())
                server.__class__.read_from_fd(server)
            server.read_from_fd = fake_read_from_fd
            # This log message is from _handle_read (not read_from_fd).
            with ExpectLog(gen_log, "error on read"):
                self.wait()
        finally:
            server.close()
            client.close()


class TestIOStreamWebHTTP(TestIOStreamWebMixin, AsyncHTTPTestCase):
    def _make_client_iostream(self):
        return IOStream(socket.socket(), io_loop=self.io_loop)


class TestIOStreamWebHTTPS(TestIOStreamWebMixin, AsyncHTTPSTestCase):
    def _make_client_iostream(self):
        return SSLIOStream(socket.socket(), io_loop=self.io_loop)


class TestIOStream(TestIOStreamMixin, AsyncTestCase):
    def _make_server_iostream(self, connection, **kwargs):
        return IOStream(connection, **kwargs)

    def _make_client_iostream(self, connection, **kwargs):
        return IOStream(connection, **kwargs)


class TestIOStreamSSL(TestIOStreamMixin, AsyncTestCase):
    def _make_server_iostream(self, connection, **kwargs):
        ssl_options = dict(
            certfile=os.path.join(os.path.dirname(__file__), 'test.crt'),
            keyfile=os.path.join(os.path.dirname(__file__), 'test.key'),
        )
        connection = ssl.wrap_socket(connection,
                                     server_side=True,
                                     do_handshake_on_connect=False,
                                     **ssl_options)
        return SSLIOStream(connection, io_loop=self.io_loop, **kwargs)

    def _make_client_iostream(self, connection, **kwargs):
        return SSLIOStream(connection, io_loop=self.io_loop, **kwargs)


# This will run some tests that are basically redundant but it's the
# simplest way to make sure that it works to pass an SSLContext
# instead of an ssl_options dict to the SSLIOStream constructor.
@unittest.skipIf(not hasattr(ssl, 'SSLContext'), 'ssl.SSLContext not present')
class TestIOStreamSSLContext(TestIOStreamMixin, AsyncTestCase):
    def _make_server_iostream(self, connection, **kwargs):
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        context.load_cert_chain(
            os.path.join(os.path.dirname(__file__), 'test.crt'),
            os.path.join(os.path.dirname(__file__), 'test.key'))
        connection = ssl_wrap_socket(connection, context,
                                     server_side=True,
                                     do_handshake_on_connect=False)
        return SSLIOStream(connection, io_loop=self.io_loop, **kwargs)

    def _make_client_iostream(self, connection, **kwargs):
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        return SSLIOStream(connection, io_loop=self.io_loop,
                           ssl_options=context, **kwargs)


@skipIfNonUnix
class TestPipeIOStream(AsyncTestCase):
    def test_pipe_iostream(self):
        r, w = os.pipe()

        rs = PipeIOStream(r, io_loop=self.io_loop)
        ws = PipeIOStream(w, io_loop=self.io_loop)

        ws.write(b"hel")
        ws.write(b"lo world")

        rs.read_until(b' ', callback=self.stop)
        data = self.wait()
        self.assertEqual(data, b"hello ")

        rs.read_bytes(3, self.stop)
        data = self.wait()
        self.assertEqual(data, b"wor")

        ws.close()

        rs.read_until_close(self.stop)
        data = self.wait()
        self.assertEqual(data, b"ld")

        rs.close()
