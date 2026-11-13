#!/usr/bin/env python
# Fuzzes the HTTP/1 client: each input is sent as the server's side of the
# connection in reply to a request from SimpleAsyncHTTPClient (with
# redirects and decompression on). A malformed response should make fetch()
# raise one of the exceptions it documents; any other exception, or an
# error log, is a crash.
#
# Usage (from the root of the repo; see README.md):
#   PYTHONPATH=. python maint/fuzz/fuzz_http_client.py -max_total_time=600

import asyncio
import gzip
import socket

import atheris
import common

with atheris.instrument_imports(include=["tornado"]):
    from tornado.httpclient import HTTPClientError
    from tornado.httputil import HTTPInputError
    from tornado.iostream import IOStream, StreamClosedError, UnsatisfiableReadError
    from tornado.netutil import Resolver, bind_sockets
    from tornado.simple_httpclient import SimpleAsyncHTTPClient
    from tornado.tcpserver import TCPServer

# What fetch() raises for a bad response. UnsatisfiableReadError is for a
# line longer than the client allows, and ValueError for a redirect to a URL
# the client can't fetch (as for fetching that URL directly).
EXPECTED = (
    HTTPClientError,
    HTTPInputError,
    StreamClosedError,
    UnsatisfiableReadError,
    ValueError,
)


class FakeServer(TCPServer):
    response = b""

    async def handle_stream(self, stream: IOStream, address: object) -> None:
        try:
            await stream.read_until(b"\r\n\r\n")
            await stream.write(self.response)
        except StreamClosedError:
            pass
        finally:
            stream.close()


class LocalResolver(Resolver):
    """Resolves every host to the fake server, so a redirect to another
    host (or a garbled one) never does a real DNS lookup."""

    async def resolve(
        self, host: str, port: int, family: socket.AddressFamily = socket.AF_UNSPEC
    ) -> list[tuple[int, tuple[str, int]]]:
        return [(socket.AF_INET, ("127.0.0.1", PORT))]


async def fetch(data: bytes) -> None:
    SERVER.response = data
    try:
        await CLIENT.fetch(
            URL, follow_redirects=True, max_redirects=1, request_timeout=5
        )
    except EXPECTED:
        pass
    # Let the client finish with the connection.
    await asyncio.sleep(0)


def test_one_input(data: bytes) -> None:
    LOOP.run_until_complete(fetch(data))
    ERRORS.check()


def seeds() -> list[bytes]:
    body = b"hello"
    gzipped = gzip.compress(body * 100)
    return [
        b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n" + body,
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: %d\r\n\r\n"
        % len(gzipped)
        + gzipped,
        b"HTTP/1.0 200 OK\r\n\r\n" + body,
        b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n"
        + body,
        b"HTTP/1.1 302 Found\r\nLocation: /b\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 204 No Content\r\n\r\n",
        b"HTTP/1.1 304 Not Modified\r\nContent-Length: 5\r\n\r\n",
    ]


ERRORS = common.ErrorLog()
ERRORS.install()
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)
[_sock] = bind_sockets(0, "127.0.0.1", family=socket.AF_INET)
PORT = _sock.getsockname()[1]
URL = "http://127.0.0.1:%d/" % PORT
SERVER = FakeServer()
SERVER.add_sockets([_sock])
CLIENT = SimpleAsyncHTTPClient(max_body_size=1 << 20, resolver=LocalResolver())

if __name__ == "__main__":
    common.main("http_client", test_one_input, seeds())
