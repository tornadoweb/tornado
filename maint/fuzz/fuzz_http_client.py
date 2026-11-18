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
import datetime
import gzip
import socket
import ssl
from typing import Any

import atheris
import common

with atheris.instrument_imports(include=["tornado"]):
    from tornado.httpclient import HTTPClientError
    from tornado.httputil import HTTPInputError
    from tornado.iostream import IOStream, StreamClosedError, UnsatisfiableReadError
    from tornado.simple_httpclient import SimpleAsyncHTTPClient
    from tornado.tcpclient import TCPClient

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


async def serve(stream: IOStream, response: bytes) -> None:
    """The server's side of a connection: read the request, send the input."""
    try:
        await stream.read_until(b"\r\n\r\n")
        await stream.write(response)
    except StreamClosedError:
        pass
    finally:
        stream.close()


class LocalTCPClient(TCPClient):
    """Connects every request to `serve` through a socketpair, so the fuzzer
    needs no network. OSS-Fuzz runs it where even the loopback interface is
    down, so connecting to 127.0.0.1 fails with ENETUNREACH. This also means
    a redirect to another host (or a garbled one) never does a DNS lookup.
    """

    response = b""

    async def connect(
        self,
        host: str,
        port: int,
        af: socket.AddressFamily = socket.AF_UNSPEC,
        ssl_options: dict[str, Any] | ssl.SSLContext | None = None,
        max_buffer_size: int | None = None,
        source_ip: str | None = None,
        source_port: int | None = None,
        timeout: float | datetime.timedelta | None = None,
    ) -> IOStream:
        if ssl_options is not None:
            # An https URL (from a redirect) can't reach the input, which
            # isn't a TLS handshake. With a real server the request would
            # time out; fail it at once as a closed connection instead.
            raise StreamClosedError()
        client, server = socket.socketpair()
        task = LOOP.create_task(serve(IOStream(server), self.response))
        # The loop keeps only weak references to tasks.
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
        return IOStream(client, max_buffer_size=max_buffer_size)


async def fetch(data: bytes) -> None:
    TCP_CLIENT.response = data
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
TASKS: set[asyncio.Task[None]] = set()
# The host and port are never used: LocalTCPClient ignores them.
URL = "http://127.0.0.1:1234/"
CLIENT = SimpleAsyncHTTPClient(max_body_size=1 << 20)
TCP_CLIENT = LocalTCPClient()
CLIENT.tcp_client.close()
CLIENT.tcp_client = TCP_CLIENT

if __name__ == "__main__":
    common.main("http_client", test_one_input, seeds())
