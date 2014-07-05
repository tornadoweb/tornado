from __future__ import absolute_import, division, print_function, with_statement

import traceback

from tornado.concurrent import Future
from tornado.httpclient import HTTPError, HTTPRequest
from tornado.log import gen_log, app_log
from tornado.testing import AsyncHTTPTestCase, gen_test, bind_unused_port, ExpectLog
from tornado.test.util import unittest
from tornado.web import Application, RequestHandler
from tornado.util import u

try:
    import tornado.websocket
    from tornado.util import _websocket_mask_python
except ImportError:
    # The unittest module presents misleading errors on ImportError
    # (it acts as if websocket_test could not be found, hiding the underlying
    # error).  If we get an ImportError here (which could happen due to
    # TORNADO_EXTENSION=1), print some extra information before failing.
    traceback.print_exc()
    raise

from tornado.websocket import WebSocketHandler, websocket_connect, WebSocketError

try:
    from tornado import speedups
except ImportError:
    speedups = None


class TestWebSocketHandler(WebSocketHandler):
    """Base class for testing handlers that exposes the on_close event.

    This allows for deterministic cleanup of the associated socket.
    """
    def initialize(self, close_future):
        self.close_future = close_future

    def on_close(self):
        self.close_future.set_result((self.close_code, self.close_reason))


class EchoHandler(TestWebSocketHandler):
    def on_message(self, message):
        self.write_message(message, isinstance(message, bytes))


class ErrorInOnMessageHandler(TestWebSocketHandler):
    def on_message(self, message):
        1/0


class HeaderHandler(TestWebSocketHandler):
    def open(self):
        try:
            # In a websocket context, many RequestHandler methods
            # raise RuntimeErrors.
            self.set_status(503)
            raise Exception("did not get expected exception")
        except RuntimeError:
            pass
        self.write_message(self.request.headers.get('X-Test', ''))


class NonWebSocketHandler(RequestHandler):
    def get(self):
        self.write('ok')


class CloseReasonHandler(TestWebSocketHandler):
    def open(self):
        self.close(1001, "goodbye")


class WebSocketTest(AsyncHTTPTestCase):
    def get_app(self):
        self.close_future = Future()
        return Application([
            ('/echo', EchoHandler, dict(close_future=self.close_future)),
            ('/non_ws', NonWebSocketHandler),
            ('/header', HeaderHandler, dict(close_future=self.close_future)),
            ('/close_reason', CloseReasonHandler,
             dict(close_future=self.close_future)),
            ('/error_in_on_message', ErrorInOnMessageHandler,
             dict(close_future=self.close_future)),
        ])

    def test_http_request(self):
        # WS server, HTTP client.
        response = self.fetch('/echo')
        self.assertEqual(response.code, 400)

    @gen_test
    def test_websocket_gen(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port(),
            io_loop=self.io_loop)
        ws.write_message('hello')
        response = yield ws.read_message()
        self.assertEqual(response, 'hello')
        ws.close()
        yield self.close_future

    def test_websocket_callbacks(self):
        websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port(),
            io_loop=self.io_loop, callback=self.stop)
        ws = self.wait().result()
        ws.write_message('hello')
        ws.read_message(self.stop)
        response = self.wait().result()
        self.assertEqual(response, 'hello')
        self.close_future.add_done_callback(lambda f: self.stop())
        ws.close()
        self.wait()

    @gen_test
    def test_binary_message(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port())
        ws.write_message(b'hello \xe9', binary=True)
        response = yield ws.read_message()
        self.assertEqual(response, b'hello \xe9')
        ws.close()
        yield self.close_future

    @gen_test
    def test_unicode_message(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port())
        ws.write_message(u('hello \u00e9'))
        response = yield ws.read_message()
        self.assertEqual(response, u('hello \u00e9'))
        ws.close()
        yield self.close_future

    @gen_test
    def test_error_in_on_message(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/error_in_on_message' % self.get_http_port())
        ws.write_message('hello')
        with ExpectLog(app_log, "Uncaught exception"):
            response = yield ws.read_message()
        self.assertIs(response, None)
        ws.close()
        yield self.close_future

    @gen_test
    def test_websocket_http_fail(self):
        with self.assertRaises(HTTPError) as cm:
            yield websocket_connect(
                'ws://localhost:%d/notfound' % self.get_http_port(),
                io_loop=self.io_loop)
        self.assertEqual(cm.exception.code, 404)

    @gen_test
    def test_websocket_http_success(self):
        with self.assertRaises(WebSocketError):
            yield websocket_connect(
                'ws://localhost:%d/non_ws' % self.get_http_port(),
                io_loop=self.io_loop)

    @gen_test
    def test_websocket_network_fail(self):
        sock, port = bind_unused_port()
        sock.close()
        with self.assertRaises(IOError):
            with ExpectLog(gen_log, ".*"):
                yield websocket_connect(
                    'ws://localhost:%d/' % port,
                    io_loop=self.io_loop,
                    connect_timeout=3600)

    @gen_test
    def test_websocket_close_buffered_data(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port())
        ws.write_message('hello')
        ws.write_message('world')
        ws.stream.close()
        yield self.close_future

    @gen_test
    def test_websocket_headers(self):
        # Ensure that arbitrary headers can be passed through websocket_connect.
        ws = yield websocket_connect(
            HTTPRequest('ws://localhost:%d/header' % self.get_http_port(),
                        headers={'X-Test': 'hello'}))
        response = yield ws.read_message()
        self.assertEqual(response, 'hello')
        ws.close()
        yield self.close_future

    @gen_test
    def test_server_close_reason(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/close_reason' % self.get_http_port())
        msg = yield ws.read_message()
        # A message of None means the other side closed the connection.
        self.assertIs(msg, None)
        self.assertEqual(ws.close_code, 1001)
        self.assertEqual(ws.close_reason, "goodbye")

    @gen_test
    def test_client_close_reason(self):
        ws = yield websocket_connect(
            'ws://localhost:%d/echo' % self.get_http_port())
        ws.close(1001, 'goodbye')
        code, reason = yield self.close_future
        self.assertEqual(code, 1001)
        self.assertEqual(reason, 'goodbye')

    @gen_test
    def test_check_origin_valid_no_path(self):
        port = self.get_http_port()

        url = 'ws://localhost:%d/echo' % port
        headers = {'Origin': 'http://localhost:%d' % port}

        ws = yield websocket_connect(HTTPRequest(url, headers=headers),
            io_loop=self.io_loop)
        ws.write_message('hello')
        response = yield ws.read_message()
        self.assertEqual(response, 'hello')
        ws.close()
        yield self.close_future

    @gen_test
    def test_check_origin_valid_with_path(self):
        port = self.get_http_port()

        url = 'ws://localhost:%d/echo' % port
        headers = {'Origin': 'http://localhost:%d/something' % port}

        ws = yield websocket_connect(HTTPRequest(url, headers=headers),
            io_loop=self.io_loop)
        ws.write_message('hello')
        response = yield ws.read_message()
        self.assertEqual(response, 'hello')
        ws.close()
        yield self.close_future

    @gen_test
    def test_check_origin_invalid_partial_url(self):
        port = self.get_http_port()

        url = 'ws://localhost:%d/echo' % port
        headers = {'Origin': 'localhost:%d' % port}

        with self.assertRaises(HTTPError) as cm:
            yield websocket_connect(HTTPRequest(url, headers=headers),
                                    io_loop=self.io_loop)
        self.assertEqual(cm.exception.code, 403)

    @gen_test
    def test_check_origin_invalid(self):
        port = self.get_http_port()

        url = 'ws://localhost:%d/echo' % port
        # Host is localhost, which should not be accessible from some other
        # domain
        headers = {'Origin': 'http://somewhereelse.com'}

        with self.assertRaises(HTTPError) as cm:
            yield websocket_connect(HTTPRequest(url, headers=headers),
                                    io_loop=self.io_loop)

        self.assertEqual(cm.exception.code, 403)

    @gen_test
    def test_check_origin_invalid_subdomains(self):
        port = self.get_http_port()

        url = 'ws://localhost:%d/echo' % port
        # Subdomains should be disallowed by default.  If we could pass a
        # resolver to websocket_connect we could test sibling domains as well.
        headers = {'Origin': 'http://subtenant.localhost'}

        with self.assertRaises(HTTPError) as cm:
            yield websocket_connect(HTTPRequest(url, headers=headers),
                                    io_loop=self.io_loop)

        self.assertEqual(cm.exception.code, 403)


class MaskFunctionMixin(object):
    # Subclasses should define self.mask(mask, data)
    def test_mask(self):
        self.assertEqual(self.mask(b'abcd', b''), b'')
        self.assertEqual(self.mask(b'abcd', b'b'), b'\x03')
        self.assertEqual(self.mask(b'abcd', b'54321'), b'TVPVP')
        self.assertEqual(self.mask(b'ZXCV', b'98765432'), b'c`t`olpd')
        # Include test cases with \x00 bytes (to ensure that the C
        # extension isn't depending on null-terminated strings) and
        # bytes with the high bit set (to smoke out signedness issues).
        self.assertEqual(self.mask(b'\x00\x01\x02\x03',
                                   b'\xff\xfb\xfd\xfc\xfe\xfa'),
                         b'\xff\xfa\xff\xff\xfe\xfb')
        self.assertEqual(self.mask(b'\xff\xfb\xfd\xfc',
                                   b'\x00\x01\x02\x03\x04\x05'),
                         b'\xff\xfa\xff\xff\xfb\xfe')


class PythonMaskFunctionTest(MaskFunctionMixin, unittest.TestCase):
    def mask(self, mask, data):
        return _websocket_mask_python(mask, data)


@unittest.skipIf(speedups is None, "tornado.speedups module not present")
class CythonMaskFunctionTest(MaskFunctionMixin, unittest.TestCase):
    def mask(self, mask, data):
        return speedups.websocket_mask(mask, data)
