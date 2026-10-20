"""Regression corpus: the inputs behind past security fixes, sent to a server.

Each fix also has a unit test next to the code it changed, but those call
internal functions that a rewrite may rename or replace. These tests send
the same inputs to a real `.HTTPServer` over a socket and check only what a
client can see (the status code and the response bytes), plus the server's
logs, so that they keep working through any rewrite of the parsers.

When fixing a new vulnerability in request handling, add its trigger here
as well as next to the fix.

Fixes that aren't reachable by sending a request to a server are covered
elsewhere:

* Client-side fixes: header stripping on cross-origin redirects
  (CVE-2026-49853, ``test_strip_headers_on_redirect`` in
  httpclient_test.py), ``max_body_size`` for decompressed and HTTP/1.0
  responses (CVE-2026-49855 and 6.5.9, httpclient_test.py and
  simple_httpclient_test.py), CR and LF in curl request headers (6.4.1,
  curl_httpclient_test.py), and curl handle reset (6.5.7).
* Out-of-bounds read in the websocket masking C extension (CVE-2026-49854,
  ``test_mask`` in websocket_test.py and the mask properties in
  property_test.py).
* `.StaticFileHandler` and symlinks outside the static root (6.5.9,
  web_test.py), which needs files on disk.
* `.OpenIDMixin` response parsing (6.5.6, auth_test.py).
"""

import http.cookies
import logging
import os
import socket
import typing
from collections.abc import Callable

from tornado.httpserver import HTTPServer
from tornado.httputil import HTTPHeaders
from tornado.iostream import IOStream, StreamClosedError
from tornado.testing import bind_unused_port, gen_test
from tornado.test.util import AsyncTestCase, assert_linear_scaling
from tornado.web import (
    Application,
    RequestHandler,
    StaticFileHandler,
    create_signed_value,
)
from tornado.websocket import WebSocketHandler


class Case(typing.NamedTuple):
    # The release with the fix, and the CVE if there is one.
    advisory: str
    name: str
    request: bytes
    # The expected status code, or None if the server should close the
    # connection without a response.
    status: int | None
    # Bytes that must not appear anywhere in the response.
    forbidden: bytes | None = None
    # Which application handles the request (see SecurityCorpusTest.apps).
    app: str = "default"
    # The most log records the request may produce. Every record must also
    # be below ERROR level; an error log means an unhandled exception.
    max_logs: int = 2


def request(
    method: str, target: str, headers: str = "", body: bytes | None = None
) -> bytes:
    head = f"{method} {target} HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n"
    if body is not None and "Transfer-Encoding" not in headers:
        head += f"Content-Length: {len(body)}\r\n"
    return (head + headers + "\r\n").encode("latin1") + (body or b"")


def post(content_type: str, body: bytes) -> bytes:
    return request("POST", "/echo", f"Content-Type: {content_type}\r\n", body)


def multipart(*parts: bytes) -> bytes:
    return post(
        "multipart/form-data; boundary=1234",
        b"".join(b"--1234\r\n" + p + b"\r\n" for p in parts) + b"--1234--\r\n",
    )


PART = b'Content-Disposition: form-data; name="a"\r\n\r\nb'
FILE_PART = b'Content-Disposition: form-data; name="f"; filename="%s"\r\n\r\nb'


COOKIE_SECRET = "secret"
# A signed cookie for the name "a", and the same bytes split so that the
# start of the value moves into the name ("a" + 4 characters). Before 3.2.1
# the signature covered the name and value without a delimiter, so both
# were valid.
_SIGNED = create_signed_value(COOKIE_SECRET, "a", "AAAABBBB").decode()
FORGED_COOKIE = ("a" + _SIGNED[:4], _SIGNED[4:])


def ws_handshake(headers: str) -> bytes:
    return request(
        "GET",
        "/ws",
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" + headers,
    )


def _static_dir_path() -> str:
    # The 6.3.2 open redirect needed the server-side path of the static
    # directory (without the drive letter on Windows).
    return os.path.splitdrive(os.path.dirname(os.path.abspath(__file__)))[1].replace(
        "\\", "/"
    )


CASES: list[Case] = [
    # 1.1.1: requests with X-Requested-With: XMLHttpRequest were exempt from
    # the XSRF check.
    Case(
        "1.1.1",
        "xsrf exemption for XMLHttpRequest",
        request(
            "POST",
            "/xsrf",
            "X-Requested-With: XMLHttpRequest\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n",
            b"a=b",
        ),
        403,
        app="xsrf",
    ),
    # 2.2.1: set_header didn't reject CR and LF, allowing response
    # splitting. (redirect() had its own check.)
    Case(
        "2.2.1",
        "set_header injection",
        request("GET", "/header?value=a%0D%0AX-Injection:%20injected"),
        400,
        forbidden=b"X-Injection",
    ),
    Case(
        "2.2.1",
        "redirect header injection",
        request("GET", "/redirect?url=/a%0D%0AX-Injection:%20injected"),
        400,
        forbidden=b"X-Injection",
    ),
    # 3.2.1: signed cookies could be moved to a different cookie name (see
    # FORGED_COOKIE).
    Case(
        "3.2.1",
        "signed cookie moved to another name",
        request(
            "GET",
            "/signed?name=" + FORGED_COOKIE[0],
            "Cookie: %s=%s\r\n" % FORGED_COOKIE,
        ),
        403,
        app="xsrf",
    ),
    # 4.0.0: websocket connections are refused from other origins by
    # default, since browsers don't apply the same-origin policy to them.
    Case(
        "4.0.0",
        "cross-origin websocket",
        ws_handshake("Origin: http://evil.example.com\r\n"),
        403,
    ),
    # 4.2.1: StaticFileHandler served files whose paths started with the
    # static directory's path without being in it.
    Case(
        "4.2.1",
        "static path prefix traversal",
        request("GET", "/../static_foo.txt"),
        403,
        forbidden=b"should not be served",
        app="static",
    ),
    # 4.4.2: the cookie parser treated characters such as "]" as
    # separators, as browsers don't, so a cookie whose value an attacker
    # could set (Google Analytics cookies, for example) could set _xsrf as
    # well and defeat the XSRF check.
    Case(
        "4.4.2",
        "cookie injected by another cookie's value",
        request(
            "POST",
            "/xsrf",
            "Cookie: a=b]_xsrf=injected\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n",
            b"_xsrf=injected",
        ),
        403,
        app="xsrf",
    ),
    # 6.3.2 (CVE-2023-28370): with static_url_prefix="/" and a
    # default_filename, a path starting with two slashes redirected to
    # another host.
    Case(
        "6.3.2 CVE-2023-28370",
        "static open redirect",
        request("GET", f"//evil.com/../{_static_dir_path()}/static/dir"),
        403,
        forbidden=b"Location",
        app="static",
    ),
    # 6.6.0: browsers treat a backslash like a slash, so /\evil.com is
    # protocol-relative too.
    Case(
        "6.6.0",
        "static open redirect, backslash",
        request("GET", "/\\evil.com/../dir"),
        403,
        forbidden=b"Location",
        app="static",
    ),
    # 6.3.3: Content-Length and chunk sizes accepted signs, underscores and
    # other forms that int() allows, which proxies may read differently.
    Case(
        "6.3.3",
        "content-length plus sign",
        request("POST", "/echo", "Content-Length: +1\r\n", b"") + b"x",
        400,
    ),
    Case(
        "6.3.3",
        "content-length underscore",
        request("POST", "/echo", "Content-Length: 1_0\r\n", b"") + b"x" * 10,
        400,
    ),
    Case(
        "6.3.3",
        "content-length not a number",
        request("POST", "/echo", "Content-Length: foo\r\n", b""),
        400,
    ),
    Case(
        "6.3.3",
        "chunk size underscore",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: chunked\r\n",
            b"1_a\r\n" + b"x" * 26 + b"\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.3.3",
        "chunk size hex prefix",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: chunked\r\n",
            b"0x2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.3.3",
        "chunk size sign",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: chunked\r\n",
            b"+2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    # 6.4.1: unknown transfer codings were ignored (and the body read until
    # close), and non-ASCII whitespace was stripped from header values.
    Case(
        "6.4.1",
        "transfer-encoding gzip, chunked",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: gzip, chunked\r\n",
            b"2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.4.1",
        "transfer-encoding repeated",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n",
            b"2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.4.1",
        "transfer-encoding and content-length",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: chunked\r\nContent-Length: 2\r\n",
            b"2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.4.1",
        "transfer-encoding with no-break space",
        request(
            "POST",
            "/echo",
            "Transfer-Encoding: \xa0chunked\r\n",
            b"2\r\nok\r\n0\r\n\r\n",
        ),
        400,
    ),
    Case(
        "6.4.1",
        "content-length with no-break space",
        request("POST", "/echo", "Content-Length: 2\xa0\r\n", b"") + b"ok",
        400,
    ),
    # 6.5.0 (CVE-2025-47287): each malformed part was logged, so a body of
    # many bad parts filled the logs. Now the first one rejects the body.
    Case(
        "6.5.0 CVE-2025-47287",
        "malformed multipart parts",
        multipart(*[b'Content-Disposition: invalid; name="a"\r\n\r\nb'] * 50),
        400,
    ),
    Case(
        "6.5.0 CVE-2025-47287",
        "multipart part without headers",
        multipart(*[b"b"] * 50),
        400,
    ),
    # 6.5.3 (CVE-2025-67724): the reason phrase was written unescaped into
    # the status line and the error page.
    Case(
        "6.5.3 CVE-2025-67724",
        "reason header injection",
        request("GET", "/status?code=200&reason=OK%0D%0AX-Injection:injected"),
        200,
        forbidden=b"X-Injection",
    ),
    Case(
        "6.5.3 CVE-2025-67724",
        "reason xss",
        request("GET", "/status?code=400&reason=<script>alert(1)</script>"),
        400,
        forbidden=b"<script>",
    ),
    # 6.5.5: multipart bodies have a limit of 100 parts; cookie attributes
    # are checked for characters that would add other attributes; CR is not
    # allowed in multipart part headers.
    Case(
        "6.5.5",
        "too many multipart parts",
        multipart(*[PART] * 150),
        400,
    ),
    Case(
        "6.5.5",
        "cookie domain injection",
        request("GET", "/cookie?domain=example.com;%20HttpOnly"),
        400,
        forbidden=b"HttpOnly",
    ),
    Case(
        "6.5.5",
        "cookie path injection",
        request("GET", "/cookie?path=/;Secure"),
        400,
        forbidden=b"Secure",
    ),
    Case(
        "6.5.5",
        "cookie samesite injection",
        request("GET", "/cookie?samesite=Lax;Partitioned"),
        400,
        forbidden=b"Partitioned",
    ),
    Case(
        "6.5.5",
        "multipart header with bare CR",
        multipart(FILE_PART % b"a\rb.txt"),
        400,
    ),
    # 6.5.8 and 6.5.9: urlencoded bodies and query strings have a limit of
    # 1000 arguments.
    Case(
        "6.5.8",
        "too many urlencoded arguments",
        post("application/x-www-form-urlencoded", b"&".join([b"a=b"] * 1001)),
        400,
    ),
    Case(
        "6.5.9",
        "too many query arguments",
        request("GET", "/echo?" + "&".join(["a=b"] * 1001)),
        400,
    ),
]


class Scaling(typing.NamedTuple):
    advisory: str
    name: str
    build: Callable[[int], bytes]
    n1: int
    n2: int
    app: str = "default"


# Fixes for quadratic parsing. Each input is valid (or rejected only after
# it is parsed), so these check the time taken, not the response.
SCALING: list[Scaling] = [
    # 6.4.2 (CVE-2024-7592): unquoting backslash escapes in a cookie value.
    Scaling(
        "6.4.2 CVE-2024-7592",
        "cookie backslashes",
        lambda n: request("GET", "/echo", 'Cookie: a="b=' + "\\\\" * n + '"\r\n'),
        1_000,
        10_000,
    ),
    # 6.5.3 (CVE-2025-67725): repeated header lines. The default 64KB
    # header limit hides most of the problem, so this uses a server with a
    # larger limit.
    Scaling(
        "6.5.3 CVE-2025-67725",
        "repeated header",
        lambda n: request("GET", "/echo", "X: a\r\n" * n),
        10_000,
        100_000,
        app="large_headers",
    ),
    # 6.5.3 (CVE-2025-67726): semicolons in a quoted Content-Disposition
    # parameter. Part headers are limited to 10KB by default.
    Scaling(
        "6.5.3 CVE-2025-67726",
        "content-disposition semicolons",
        lambda n: multipart(
            b'Content-Disposition: form-data; x="' + b";" * n + b'"; name="a"\r\n\r\nb'
        ),
        1_000,
        10_000,
    ),
]


class EchoHandler(RequestHandler):
    def get(self) -> None:
        self.post()

    def post(self) -> None:
        # Cookies are parsed on first use.
        self.write(
            {
                "cookies": len(self.cookies),
                "arguments": len(self.request.arguments),
                "files": len(self.request.files),
            }
        )


class StatusHandler(RequestHandler):
    def get(self) -> None:
        self.set_status(int(self.get_argument("code")), self.get_argument("reason"))
        if self.get_status() >= 400:
            self.send_error(self.get_status(), reason=self.get_argument("reason"))
        else:
            self.write("ok")


class CookieHandler(RequestHandler):
    def get(self) -> None:
        try:
            self.set_cookie(
                "a",
                "b",
                domain=self.get_argument("domain", None),
                path=self.get_argument("path", "/"),
                samesite=self.get_argument("samesite", None),
            )
        except (ValueError, http.cookies.CookieError):
            self.send_error(400)


class HeaderHandler(RequestHandler):
    def get(self) -> None:
        try:
            self.set_header("X-Test", self.get_argument("value"))
        except ValueError:
            self.send_error(400)


class RedirectHandler(RequestHandler):
    def get(self) -> None:
        try:
            self.redirect(self.get_argument("url"))
        except ValueError:
            self.send_error(400)


class XSRFHandler(RequestHandler):
    def get(self) -> None:
        self.write(self.xsrf_token)

    def post(self) -> None:
        self.write("ok")


class SignedCookieHandler(RequestHandler):
    def get(self) -> None:
        if self.get_signed_cookie(self.get_argument("name")) is None:
            self.send_error(403)
        else:
            self.write("ok")


class EchoWebSocket(WebSocketHandler):
    def on_message(self, message: str | bytes) -> None:
        self.write_message(message, binary=isinstance(message, bytes))


class LogCapture(logging.Handler):
    """Collects the records of the ``tornado`` loggers, keeping them out of
    the test runner's output and its count of unexpected logs."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def __enter__(self) -> "LogCapture":
        logger = logging.getLogger("tornado")
        self.saved = logger.propagate, logger.level
        logger.addHandler(self)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        return self

    def __exit__(self, *exc_info: object) -> None:
        logger = logging.getLogger("tornado")
        logger.removeHandler(self)
        logger.propagate, level = self.saved
        logger.setLevel(level)


class SecurityCorpusTest(AsyncTestCase):
    def setUp(self) -> None:
        super().setUp()
        static_path = os.path.join(os.path.dirname(__file__), "static")
        handlers = [
            ("/echo", EchoHandler),
            ("/status", StatusHandler),
            ("/cookie", CookieHandler),
            ("/header", HeaderHandler),
            ("/redirect", RedirectHandler),
            ("/ws", EchoWebSocket),
        ]
        apps = {
            "default": (Application(handlers), {}),
            "xsrf": (
                Application(
                    [("/xsrf", XSRFHandler), ("/signed", SignedCookieHandler)],
                    xsrf_cookies=True,
                    cookie_secret=COOKIE_SECRET,
                ),
                {},
            ),
            "large_headers": (Application(handlers), {"max_header_size": 1 << 20}),
            "static": (
                Application(
                    static_path=static_path,
                    static_url_prefix="/",
                    static_handler_args=dict(default_filename="index.html"),
                    static_handler_class=StaticFileHandler,
                ),
                {},
            ),
        }
        self.ports: dict[str, int] = {}
        self.servers: list[HTTPServer] = []
        for name, (app, kwargs) in apps.items():
            sock, port = bind_unused_port()
            server = HTTPServer(app, **kwargs)
            server.add_sockets([sock])
            self.servers.append(server)
            self.ports[name] = port

    def tearDown(self) -> None:
        for server in self.servers:
            server.stop()
            self.io_loop.run_sync(server.close_all_connections)
        super().tearDown()

    async def send(self, app: str, data: bytes) -> bytes:
        stream = IOStream(socket.socket())
        try:
            await stream.connect(("127.0.0.1", self.ports[app]))
            await stream.write(data)
            # Most responses end with the connection, but some (such as a
            # refused websocket handshake) keep it open.
            head = await stream.read_until(b"\r\n\r\n")
            headers = HTTPHeaders.parse(head.decode("latin1").partition("\r\n")[2])
            if "Content-Length" in headers:
                body = await stream.read_bytes(int(headers["Content-Length"]))
            else:
                body = await stream.read_until_close()
            return head + body
        except StreamClosedError:
            # Closed without a response.
            return b""
        finally:
            stream.close()

    def check_logs(self, logs: LogCapture, max_logs: int) -> None:
        errors = [r for r in logs.records if r.levelno >= logging.ERROR]
        self.assertEqual(errors, [], "server logged an error")
        # The access log has one line per response.
        others = [r for r in logs.records if r.name != "tornado.access"]
        self.assertLessEqual(len(others), max_logs, [r.getMessage() for r in others])

    @gen_test
    async def test_cases(self) -> None:
        for case in CASES:
            with self.subTest(f"{case.advisory}: {case.name}"):
                with LogCapture() as logs:
                    response = await self.send(case.app, case.request)
                if case.status is None:
                    self.assertEqual(response, b"")
                else:
                    status_line = response.split(b"\r\n", 1)[0]
                    self.assertEqual(
                        status_line.split(b" ")[:2],
                        [b"HTTP/1.1", str(case.status).encode()],
                        response[:200],
                    )
                if case.forbidden is not None:
                    self.assertNotIn(case.forbidden, response)
                self.check_logs(logs, case.max_logs)

    @gen_test
    async def test_xsrf_token_masked(self) -> None:
        # 3.2.2: the XSRF token in a page is masked differently on each
        # request, so that it can't be recovered from compressed responses
        # (BREACH).
        cookie = "_xsrf=0123456789abcdef0123456789abcdef"
        tokens = []
        for _ in range(2):
            response = await self.send(
                "xsrf", request("GET", "/xsrf", f"Cookie: {cookie}\r\n")
            )
            head, _, body = response.partition(b"\r\n\r\n")
            self.assertTrue(head.startswith(b"HTTP/1.1 200 "), head)
            self.assertNotIn(b"0123456789abcdef", body)
            tokens.append(body)
        self.assertNotEqual(tokens[0], tokens[1])

    def test_scaling(self) -> None:
        for case in SCALING:
            with self.subTest(f"{case.advisory}: {case.name}"):
                responses = []

                def f(n: int) -> None:
                    data = case.build(n)
                    responses.append(
                        self.io_loop.run_sync(lambda: self.send(case.app, data))
                    )

                with LogCapture() as logs:
                    assert_linear_scaling(
                        f,
                        case.n1,
                        case.n2,
                        max_ratio=20,
                        msg=f"{case.name} does not scale linearly",
                    )
                # Every request must have been answered.
                self.assertTrue(all(r.startswith(b"HTTP/1.1 ") for r in responses))
                errors = [r for r in logs.records if r.levelno >= logging.ERROR]
                self.assertEqual(errors, [], "server logged an error")
