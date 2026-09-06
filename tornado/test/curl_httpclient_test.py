import base64
import functools
from hashlib import md5
import os
import ssl
import tracemalloc
import unittest
from unittest import mock
import zlib

from tornado import gen
from tornado.escape import utf8
from tornado.httpclient import HTTPError
from tornado.log import app_log
from tornado.netutil import ssl_options_to_context
from tornado.test import httpclient_test
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
    from tornado.curl_httpclient import CurlAsyncHTTPClient, _CurlStreamingBuffer


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client


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
        self.http_client = self.create_client()

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

    def create_client(self, **kwargs):
        return CurlAsyncHTTPClient(
            force_instance=True, defaults=dict(allow_ipv6=False), **kwargs
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


# Size of the decompressed response used by CurlHTTPClientStreamingTestCase.
# Large enough that buffering all of it would be obvious, small enough that
# the test stays fast.
BOMB_SIZE = 256 * 1024 * 1024


@functools.lru_cache(maxsize=None)
def gzip_bomb() -> bytes:
    """Returns a small gzip stream that expands to `BOMB_SIZE` bytes."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    block = b"\0" * (1024 * 1024)
    pieces = [compressor.compress(block) for _ in range(BOMB_SIZE // len(block))]
    pieces.append(compressor.flush())
    return b"".join(pieces)


@functools.lru_cache(maxsize=None)
def large_body() -> bytes:
    """Returns a body whose contents are non-repeating.

    This makes it possible to detect chunks that were dropped or delivered
    twice.
    """
    return b"".join(b"%09d\n" % i for i in range(100000))


class GzipBombHandler(RequestHandler):
    """Sends a tiny response that decompresses to a very large one."""

    def get(self):
        self.set_header("Content-Encoding", "gzip")
        self.write(gzip_bomb())


class LargeHandler(RequestHandler):
    def get(self):
        self.write(large_body())


# A 421-byte brotli stream that expands to BROTLI_BOMB_SIZE bytes of zeros,
# a ratio of ~637000:1 (deflate cannot exceed ~1032:1). Embedded as a
# constant so that the test suite does not need a brotli module for Python.
# Regenerate with:
#     import base64, brotli
#     base64.b64encode(brotli.compress(b"\0" * BROTLI_BOMB_SIZE, quality=11))
BROTLI_BOMB_SIZE = 256 * 1024 * 1024
BROTLI_BOMB = base64.b64decode(
    "y///P/gnAOKxQCD3/o///3/wTwDEYRGA7v0f////4J8AiMMCAN37P/7//8E/ARCHBQC6"
    "93/8//+DfwIgDgsAdO//+P//B/8EQBwWAOje//H//w/+CYA4LADQvf/j//8f/BMAcVgA"
    "oHv/x///P/gnAOKwAED3/o///3/wTwDEYQGA7v0f////4J8AiMMCAN37P/7//8E/ARCH"
    "BQC693/8//+DfwIgDgsAdO//+P//B/8EQBwWAOje//H//w/+CYA4LADQvf/j//8f/BMA"
    "cVgAoHv/x///P/gnAOKwAED3/o///3/wTwDEYQGA7v0f////4J8AiMMCAN37P/7//8E/"
    "ARCHBQC693/8//+DfwIgDgsAdO//+P//B/8EQBwWAOje//H//w/+CYA4LADQvf/j//8f"
    "/BMAcVgAoHv/x///P/gnAOKwAED3/o///3/wTwDEYQGA7v0f////4J8AiMMCAN37P/7/"
    "/8E/ARCHBQC693/8//+DfwIgDgsAdO//+P//B/8EQBwWAOje//H//w/+CYA4LADQvf/j"
    "//8f/BMAcVgAoHv/Nw=="
)


class BrotliBombHandler(RequestHandler):
    """Sends a brotli-encoded bomb that the client never asked for.

    ``curl_httpclient`` requests ``Accept-Encoding: gzip,deflate``, but
    libcurl builds its decoder from the ``Content-Encoding`` of the response
    and does not check it against what was requested, so a server can reach
    any codec the libcurl build happens to include.
    """

    def get(self):
        self.set_header("Content-Encoding", "br")
        self.write(BROTLI_BOMB)


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientStreamingTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return Application(
            [
                ("/bomb", GzipBombHandler),
                ("/brotli_bomb", BrotliBombHandler),
                ("/large", LargeHandler),
            ]
        )

    def get_http_client(self):
        return CurlAsyncHTTPClient(force_instance=True, defaults=dict(allow_ipv6=False))

    def test_streaming_decompression_bomb(self):
        # A malicious server can turn a small compressed response into an
        # arbitrarily large decompressed one. A streaming_callback must be
        # able to consume the whole thing without the client buffering more
        # than a bounded amount of it at a time.
        gzip_bomb()  # Precompute so it isn't counted in the measurement.
        received = 0

        def streaming_callback(chunk):
            nonlocal received
            received += len(chunk)

        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            response = self.fetch("/bomb", streaming_callback=streaming_callback)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

        self.assertEqual(response.code, 200)
        self.assertEqual(received, BOMB_SIZE)
        self.assertEqual(response.body, b"")
        # The client used to queue every chunk libcurl produced for later
        # delivery, so this used to hold a large fraction of BOMB_SIZE.
        self.assertLess(peak, 16 * 1024 * 1024)

    @unittest.skipIf(
        pycurl is not None and "brotli" not in pycurl.version,
        "libcurl built without brotli support",
    )
    def test_streaming_unsolicited_brotli_bomb(self):
        # Since libcurl decodes whatever Content-Encoding the response names,
        # a server can reach a codec whose expansion ratio is hundreds of
        # times deflate's, even though we only asked for gzip and deflate.
        # The transfer itself may not survive -- libcurl fails it once its
        # own 64MB pause buffer overflows -- but either way the expansion
        # must not be buffered on our side.
        received = 0

        def streaming_callback(chunk):
            nonlocal received
            received += len(chunk)

        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            try:
                code = self.fetch(
                    "/brotli_bomb", streaming_callback=streaming_callback
                ).code
            except HTTPError as e:
                # The usual outcome: libcurl aborts the transfer once its own
                # pause buffer cannot hold the expansion.
                code = e.code
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

        # More than was sent on the wire, i.e. libcurl really did decode an
        # encoding we did not ask for.
        self.assertGreater(received, len(BROTLI_BOMB))
        self.assertIn(code, (200, 599))
        self.assertLess(peak, 16 * 1024 * 1024)
        self.assertLess(received, 16 * 1024 * 1024)

    def test_streaming_pause_and_resume(self):
        # Exercise many pause/resume cycles and verify that the body is
        # delivered exactly once, in order. libcurl re-delivers the chunk
        # that was in flight when the transfer was paused, so it must not be
        # consumed twice.
        chunks: list[bytes] = []
        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 1024):
            response = self.fetch("/large", streaming_callback=chunks.append)
        self.assertEqual(response.code, 200)
        self.assertEqual(b"".join(chunks), large_body())

    def test_streaming_callback_exception(self):
        # An exception in the streaming_callback is logged and does not stop
        # the transfer or leave it paused forever.
        chunks: list[bytes] = []

        def streaming_callback(chunk):
            chunks.append(chunk)
            if len(chunks) == 1:
                raise ZeroDivisionError()

        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 1024):
            with ExpectLog(app_log, "Exception in callback"):
                response = self.fetch("/large", streaming_callback=streaming_callback)
        self.assertEqual(response.code, 200)
        self.assertEqual(b"".join(chunks), large_body())


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlStreamingBufferTest(AsyncTestCase):
    def test_unpause_error_is_ignored(self):
        # When a transfer fails while it is paused, libcurl reports the
        # failure from curl_easy_pause instead of from the write callback.
        # That is not an error in the flush itself, and must not be raised
        # into the IOLoop: _finish will pass the failure to the callback.
        class FakeCurl:
            def pause(self, flags):
                raise pycurl.error(pycurl.E_WRITE_ERROR, "write error")

        chunks: list[bytes] = []
        buf = _CurlStreamingBuffer(
            self.io_loop,
            FakeCurl(),  # type: ignore[arg-type]
            chunks.append,
        )
        with mock.patch.object(_CurlStreamingBuffer, "max_buffer_size", 4):
            self.assertEqual(buf.write(b"hello"), 5)
            # The buffer is full, so this chunk is left with libcurl.
            self.assertEqual(buf.write(b"world"), pycurl.WRITEFUNC_PAUSE)
        self.assertTrue(buf.paused)
        buf.flush()
        self.assertEqual(chunks, [b"hello"])
        self.assertFalse(buf.paused)
