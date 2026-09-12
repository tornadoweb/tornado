import gc
from hashlib import md5
import os
import ssl
import unittest
from unittest import mock
import weakref

from tornado import gen
from tornado.escape import utf8
from tornado.log import app_log
from tornado.netutil import ssl_options_to_context
from tornado.test import httpclient_test
from tornado.test.util import skipNotCPython
from tornado.testing import (
    AsyncHTTPSTestCase,
    AsyncHTTPTestCase,
    AsyncTestCase,
    ExpectLog,
)
from tornado.web import Application, RequestHandler

try:
    import pycurl
except ImportError:
    pycurl = None  # type: ignore

if pycurl is not None:
    from tornado.curl_httpclient import (
        CurlAsyncHTTPClient,
        CurlError,
        _CurlStreamingBuffer,
    )


def create_client(**kwargs):
    return CurlAsyncHTTPClient(
        force_instance=True, defaults=dict(allow_ipv6=False), **kwargs
    )


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    # libcurl decodes the Content-Encoding named by the response whether or
    # not we listed it in Accept-Encoding, so brotli is reachable whenever
    # libcurl was built with it (which is common).
    decompresses_brotli = pycurl is not None and "brotli" in pycurl.version

    def get_http_client(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client

    def test_streaming_pause_and_resume(self):
        # With a small buffer the transfer is paused and resumed many times
        # over one response. libcurl re-delivers the chunk that was in
        # flight when it was paused, so that chunk must not be consumed
        # twice.
        chunks: list[bytes] = []
        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 1024):
            response = self.fetch("/large_body", streaming_callback=chunks.append)
        self.assertEqual(response.code, 200)
        self.assertEqual(b"".join(chunks), httpclient_test.large_body())

    def test_concurrent_paused_streams(self):
        # Several streaming requests in flight at once, each pausing and
        # resuming repeatedly: pausing one transfer must not disturb another.
        client = create_client(max_clients=4)
        buffers = [bytearray() for _ in range(8)]
        try:
            with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 1024):
                self.io_loop.run_sync(
                    lambda: gen.multi(
                        [
                            client.fetch(
                                self.get_url("/large_body"),
                                streaming_callback=buf.extend,
                            )
                            for buf in buffers
                        ]
                    )
                )
        finally:
            client.close()
        for buf in buffers:
            self.assertEqual(bytes(buf), httpclient_test.large_body())

    @skipNotCPython
    def test_client_not_leaked_by_write_callbacks(self):
        # The WRITEFUNCTION callbacks installed for both the buffered and
        # the streaming path hold references to the client and to the curl
        # handle. They must not keep the client alive after close().

        def use_and_close_a_client():
            client = create_client()
            self.io_loop.run_sync(lambda: client.fetch(self.get_url("/hello")))
            self.io_loop.run_sync(
                lambda: client.fetch(
                    self.get_url("/large_body"),
                    streaming_callback=lambda chunk: None,
                )
            )
            client.close()
            return weakref.ref(client)

        ref = use_and_close_a_client()
        gc.collect()
        self.assertIsNone(ref())

    def test_streaming_callback_exception(self):
        # An exception in the streaming_callback is logged, and does not
        # stop the transfer or leave it paused forever.
        chunks: list[bytes] = []

        def streaming_callback(chunk):
            chunks.append(chunk)
            if len(chunks) == 1:
                raise ZeroDivisionError()

        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 1024):
            with ExpectLog(app_log, "Exception in callback"):
                response = self.fetch(
                    "/large_body", streaming_callback=streaming_callback
                )
        self.assertEqual(response.code, 200)
        self.assertEqual(b"".join(chunks), httpclient_test.large_body())


class DigestAuthHandler(RequestHandler):
    def initialize(self, username, password):
        self.username = username
        self.password = password

    def get(self):
        realm = "test"
        opaque = "asdf"
        # Real implementations would use a random nonce.
        nonce = "1234"

        auth_header = self.request.headers.get("Authorization", None)
        if auth_header is not None:
            auth_mode, params = auth_header.split(" ", 1)
            assert auth_mode == "Digest"
            param_dict = {}
            for pair in params.split(","):
                k, v = pair.strip().split("=", 1)
                if v[0] == '"' and v[-1] == '"':
                    v = v[1:-1]
                param_dict[k] = v
            assert param_dict["realm"] == realm
            assert param_dict["opaque"] == opaque
            assert param_dict["nonce"] == nonce
            assert param_dict["username"] == self.username
            assert param_dict["uri"] == self.request.path
            h1 = md5(utf8(f"{self.username}:{realm}:{self.password}")).hexdigest()
            h2 = md5(utf8(f"{self.request.method}:{self.request.path}")).hexdigest()
            digest = md5(utf8(f"{h1}:{nonce}:{h2}")).hexdigest()
            if digest == param_dict["response"]:
                self.write("ok")
            else:
                self.write("fail")
        else:
            self.set_status(401)
            self.set_header(
                "WWW-Authenticate",
                f'Digest realm="{realm}", nonce="{nonce}", opaque="{opaque}"',
            )


class CustomReasonHandler(RequestHandler):
    def get(self):
        self.set_status(200, "Custom reason")


class CustomFailReasonHandler(RequestHandler):
    def get(self):
        self.set_status(400, "Custom reason")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientTestCase(AsyncHTTPTestCase):
    def setUp(self):
        super().setUp()
        self.http_client = create_client()

    def get_app(self):
        return Application(
            [
                ("/digest", DigestAuthHandler, {"username": "foo", "password": "bar"}),
                (
                    "/digest_non_ascii",
                    DigestAuthHandler,
                    {"username": "foo", "password": "barユ£"},
                ),
                ("/custom_reason", CustomReasonHandler),
                ("/custom_fail_reason", CustomFailReasonHandler),
            ]
        )

    def test_digest_auth(self):
        response = self.fetch(
            "/digest", auth_mode="digest", auth_username="foo", auth_password="bar"
        )
        self.assertEqual(response.body, b"ok")

    def test_custom_reason(self):
        response = self.fetch("/custom_reason")
        self.assertEqual(response.reason, "Custom reason")

    def test_fail_custom_reason(self):
        response = self.fetch("/custom_fail_reason")
        self.assertEqual(str(response.error), "HTTP 400: Custom reason")

    def test_digest_auth_non_ascii(self):
        response = self.fetch(
            "/digest_non_ascii",
            auth_mode="digest",
            auth_username="foo",
            auth_password="barユ£",
        )
        self.assertEqual(response.body, b"ok")

    def test_streaming_callback_not_permitted(self):
        @gen.coroutine
        def _recv_chunk(chunk):
            yield gen.moment

        with self.assertRaises(TypeError):
            self.fetch("/digest", streaming_callback=_recv_chunk)

        import asyncio

        async def _async_recv_chunk(chunk):
            await asyncio.sleep(0)

        with self.assertRaises(TypeError):
            self.fetch("/digest", streaming_callback=_async_recv_chunk)


class ProxyAuthEchoHandler(RequestHandler):
    def get(self):
        if self.request.headers.get("Proxy-Authorization", None) is not None:
            self.write(f"proxy auth: {self.request.headers['Proxy-Authorization']}")
        else:
            self.write("no proxy auth")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientReuseProxyAuthTestCase(AsyncHTTPTestCase):
    def get_app(self):
        # Note that we don't properly support proxy-style requests, but it works well enough
        # for this test if we start the url matcher with a wildcard.
        return Application([(".*/proxy_auth", ProxyAuthEchoHandler)])

    def get_http_client(self):
        # max_clients=1 forces us to reuse curl "easy handles". This is a regression test for
        # a bug in which proxy credentials were not cleared between requests.
        return CurlAsyncHTTPClient(
            force_instance=True,
            defaults=dict(
                allow_ipv6=False,
            ),
            max_clients=1,
        )

    def test_reuse_proxy_credentials(self):
        # Proxy credentials used on one request should not be automatically reused
        # by another request.
        response = self.fetch(
            "/proxy_auth",
            proxy_host="127.0.0.1",
            proxy_port=self.get_http_port(),
            proxy_username="foo",
            proxy_password="bar",
        )
        self.assertEqual(response.body, b"proxy auth: Basic Zm9vOmJhcg==")
        response = self.fetch(
            "/proxy_auth",
            proxy_host="127.0.0.1",
            proxy_port=self.get_http_port(),
        )
        self.assertEqual(response.body, b"no proxy auth")


class ClientCertEchoHandler(RequestHandler):
    def get(self):
        cert = self.request.get_ssl_certificate()
        if cert is not None:
            assert isinstance(cert, dict)
            self.write(f"client cert: {cert['subject']}")
        else:
            self.write("no client cert")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientReuseCertsTestCase(AsyncHTTPSTestCase):
    def get_app(self):
        return Application([(".*/client_cert", ClientCertEchoHandler)])

    def get_http_client(self):
        return CurlAsyncHTTPClient(
            force_instance=True,
            defaults=dict(
                allow_ipv6=False,
                validate_cert=False,
            ),
            max_clients=1,
        )

    def get_httpserver_options(self):
        ssl_ctx = ssl_options_to_context(self.get_ssl_options(), server_side=True)
        ssl_ctx.verify_mode = ssl.CERT_OPTIONAL
        return dict(ssl_options=ssl_ctx)

    def get_ssl_options(self):
        opts = super().get_ssl_options()
        opts["ca_certs"] = os.path.join(os.path.dirname(__file__), "test.crt")
        return opts

    def test_reuse_certs(self):
        # Client certs used on one request should not be automatically reused
        # by another request.
        response = self.fetch(
            self.get_url("/client_cert"),
            client_cert=os.path.join(os.path.dirname(__file__), "test.crt"),
            client_key=os.path.join(os.path.dirname(__file__), "test.key"),
        )
        self.assertEqual(
            response.body, b"client cert: ((('commonName', 'foo.example.com'),),)"
        )
        response = self.fetch(self.get_url("/client_cert"))
        self.assertEqual(response.body, b"no client cert")


# Mirrors simple_httpclient_test.MaxBodySizeTest.
CURL_MAX_BODY_SIZE = 1024 * 64


class SmallBodyHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/octet-stream")
        self.write(b"a" * CURL_MAX_BODY_SIZE)


class LargeBodyHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Type", "application/octet-stream")
        self.write(b"a" * (CURL_MAX_BODY_SIZE + 1))


class BombHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Encoding", "gzip")
        self.write(httpclient_test.gzip_bomb())


class BodyBearingRedirectHandler(RequestHandler):
    def prepare(self):
        # A redirect carrying a body of its own, larger than the limit.
        self.write("x" * (CURL_MAX_BODY_SIZE * 2))
        self.redirect("/small")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlMaxBodySizeTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application(
            [
                ("/small", SmallBodyHandler),
                ("/large", LargeBodyHandler),
                ("/bomb", BombHandler),
                ("/body_bearing_redirect", BodyBearingRedirectHandler),
            ]
        )

    def get_http_client(self):
        # max_clients=1 so that each test also reuses the curl handle left
        # behind by the one before it.
        return create_client(max_body_size=CURL_MAX_BODY_SIZE, max_clients=1)

    def test_small_body(self):
        # A body of exactly max_body_size is accepted.
        response = self.fetch("/small")
        response.rethrow()
        self.assertEqual(response.body, b"a" * CURL_MAX_BODY_SIZE)

    def test_large_body(self):
        # One byte more is not.
        with self.assertRaises(CurlError) as cm:
            self.fetch("/large", raise_error=True)
        self.assertIn("max_body_size", str(cm.exception))

    def test_decompressed_body_size(self):
        # The limit is measured against the decompressed size, so a
        # decompression bomb is refused even though almost nothing was sent
        # on the wire. (libcurl's own CURLOPT_MAXFILESIZE counts the
        # compressed size except on very recent versions.)
        with self.assertRaises(CurlError) as cm:
            self.fetch("/bomb", raise_error=True)
        self.assertIn("max_body_size", str(cm.exception))

    def test_streaming_callback_not_limited(self):
        # A streaming_callback never buffers the whole body, so it is not
        # subject to max_body_size: the point of streaming is being able to
        # retrieve a response of any size.
        received = 0

        def streaming_callback(chunk):
            nonlocal received
            received += len(chunk)

        response = self.fetch("/bomb", streaming_callback=streaming_callback)
        response.rethrow()
        self.assertEqual(received, httpclient_test.GZIP_BOMB_SIZE)

    def test_reuse_after_rejection(self):
        # Refusing a body must not leave anything behind on the recycled
        # curl handle that affects the next request.
        with self.assertRaises(CurlError):
            self.fetch("/large", raise_error=True)
        response = self.fetch("/small")
        response.rethrow()
        self.assertEqual(response.body, b"a" * CURL_MAX_BODY_SIZE)

    def test_redirect_body_not_counted(self):
        # libcurl discards the body of a redirect that it follows, so a
        # redirect carrying a large body of its own does not count towards
        # the limit for the response that follows it.
        response = self.fetch("/body_bearing_redirect")
        response.rethrow()
        self.assertEqual(response.body, b"a" * CURL_MAX_BODY_SIZE)


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlStreamingBufferTest(AsyncTestCase):
    """Unit tests for the buffer that feeds a ``streaming_callback``."""

    def setUp(self):
        super().setUp()
        self.timeouts_requested: list[int] = []
        test = self

        class FakeClient:
            io_loop = test.io_loop

            def _set_timeout(self, msecs):
                test.timeouts_requested.append(msecs)

        self.client = FakeClient()

    def make_buffer(self, curl, callback):
        return _CurlStreamingBuffer(
            self.client,  # type: ignore[arg-type]
            curl,
            callback,
        )

    def test_unpause_asks_for_a_socket_action(self):
        # Only libcurl 8.x reports through the timer callback that an
        # unpaused transfer is runnable again; older versions leave it
        # stalled unless we ask for a socket_action ourselves.
        paused = []

        class FakeCurl:
            def pause(self, flags):
                paused.append(flags)

        chunks: list[bytes] = []
        buf = self.make_buffer(FakeCurl(), chunks.append)
        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 4):
            self.assertEqual(buf.write(b"hello"), 5)
            self.assertEqual(buf.write(b"world"), pycurl.WRITEFUNC_PAUSE)
        buf.flush()
        self.assertEqual(chunks, [b"hello"])
        self.assertEqual(paused, [pycurl.PAUSE_CONT])
        self.assertEqual(self.timeouts_requested, [0])

    def test_unpause_error_is_ignored(self):
        # When a transfer fails while it is paused, libcurl reports the
        # failure from curl_easy_pause instead of from the write callback.
        # That is not an error in the flush itself, and must not be raised
        # into the IOLoop: _finish will pass the failure to the callback.
        class FakeCurl:
            def pause(self, flags):
                raise pycurl.error(pycurl.E_WRITE_ERROR, "write error")

        chunks: list[bytes] = []
        buf = self.make_buffer(FakeCurl(), chunks.append)
        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 4):
            self.assertEqual(buf.write(b"hello"), 5)
            # The buffer is full, so this chunk is left with libcurl.
            self.assertEqual(buf.write(b"world"), pycurl.WRITEFUNC_PAUSE)
        self.assertTrue(buf.paused)
        buf.flush()
        self.assertEqual(chunks, [b"hello"])
        self.assertFalse(buf.paused)
        # A failed unpause is not worth a socket_action.
        self.assertEqual(self.timeouts_requested, [])
