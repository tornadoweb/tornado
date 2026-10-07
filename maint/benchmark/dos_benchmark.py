#!/usr/bin/env python
#
# Measures the cost of processing adversarial-but-valid input: how much CPU
# the server spends per byte received, how long it blocks the event loop,
# and how much memory it uses. This is the baseline used to evaluate
# denial-of-service reports (see SECURITY.md).
#
# Each scenario runs a server on the main thread and a client in a
# background thread that sends a pre-built byte stream as fast as possible
# on a single connection. CPU time is measured for the main (server) thread
# only. "max stall" is the longest gap seen by a coroutine on the server's
# event loop that wakes up every millisecond.
#
# Usage (from the root of the repo):
#   PYTHONPATH=. python maint/benchmark/dos_benchmark.py          # all scenarios
#   PYTHONPATH=. python maint/benchmark/dos_benchmark.py --scenario=http_chunked --n=1000000
#   PYTHONPATH=. python maint/benchmark/dos_benchmark.py --tracemalloc  # reports peak memory
#
# --tracemalloc slows everything down substantially, so CPU numbers from
# runs using it are not comparable to those without.
#
# The default sizes take about a second per scenario; the per-byte costs are
# what matter. Results vary with hardware and Python version, and with
# whether the tornado.speedups extension is built (it is used for websocket
# masking).

import asyncio
import base64
import socket
import struct
import sys
import threading
import time
import tracemalloc
import typing
import zlib
from collections.abc import Callable

from tornado import httpserver, netutil, web, websocket
from tornado.options import define, options, parse_command_line

define("scenario", type=str, multiple=True, help="scenarios to run (default all)")
define("n", type=int, default=0, help="number of units (default per scenario)")
define("size", type=int, default=-1, help="unit payload size (default per scenario)")
define("tracemalloc", type=bool, default=False, help="report peak traced memory")


class Scenario(typing.NamedTuple):
    # Returns (handlers, request bytes). The request is sent on a fresh
    # connection; the client then reads until the server closes it.
    build: Callable[[int, int], tuple[list, bytes]]
    n: int
    size: int
    unit: str
    server_kwargs: dict[str, typing.Any] = {}


# Set by handlers when the server has processed the whole request.
done = asyncio.Event()
# Peak size of the server's write buffer, for scenarios that check it.
peak_write_buffer = 0


class HTTPHandler(web.RequestHandler):
    def get(self):
        pass

    def post(self):
        self.write(str(len(self.request.body)))


@web.stream_request_body
class StreamingHTTPHandler(web.RequestHandler):
    def data_received(self, chunk):
        pass

    def post(self):
        pass


class LastRequestHandler(web.RequestHandler):
    def get(self):
        done.set()


def http_finish(handler_class):
    class Wrapper(handler_class):  # type: ignore
        def on_finish(self):
            done.set()

    return Wrapper


def http_pipelined(n: int, size: int) -> tuple[list, bytes]:
    req = b"GET / HTTP/1.1\r\nHost: x\r\n\r\n"
    last = b"GET /last HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n"
    return [("/", HTTPHandler), ("/last", LastRequestHandler)], req * n + last


def chunked_request(n: int, size: int) -> bytes:
    hdr = b"POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n"
    hdr += b"Connection: close\r\n\r\n"
    chunk = b"%x\r\n" % size + b"x" * size + b"\r\n"
    return hdr + chunk * n + b"0\r\n\r\n"


def http_chunked(n: int, size: int) -> tuple[list, bytes]:
    return [("/", http_finish(HTTPHandler))], chunked_request(n, size)


def http_chunked_streaming(n: int, size: int) -> tuple[list, bytes]:
    return [("/", http_finish(StreamingHTTPHandler))], chunked_request(n, size)


def http_fixed(n: int, size: int) -> tuple[list, bytes]:
    body = b"x" * (n * size)
    hdr = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n" % len(body)
    hdr += b"Connection: close\r\n\r\n"
    return [("/", http_finish(StreamingHTTPHandler))], hdr + body


class WSHandler(websocket.WebSocketHandler):
    compress = False

    def get_compression_options(self):
        return {} if self.compress else None

    def open(self):
        self.stream = self.ws_connection.stream  # type: ignore

    def on_message(self, message):
        pass

    def on_close(self):
        done.set()


class WSDeflateHandler(WSHandler):
    compress = True


class WSPingHandler(WSHandler):
    def on_ping(self, data):
        global peak_write_buffer
        peak_write_buffer = max(peak_write_buffer, len(self.stream._write_buffer))


def ws_handshake(deflate: bool = False) -> bytes:
    key = base64.b64encode(b"0123456789abcdef")
    req = (
        b"GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " + key + b"\r\n"
    )
    if deflate:
        req += b"Sec-WebSocket-Extensions: permessage-deflate\r\n"
    return req + b"\r\n"


def ws_frame(
    opcode: int, payload: bytes, fin: bool = True, rsv1: bool = False
) -> bytes:
    # Client frames must be masked; an all-zero mask leaves the payload
    # unchanged but the server still does the work of unmasking it.
    b0 = (0x80 if fin else 0) | (0x40 if rsv1 else 0) | opcode
    n = len(payload)
    if n < 126:
        hdr = struct.pack("BB", b0, 0x80 | n)
    elif n < 65536:
        hdr = struct.pack("!BBH", b0, 0x80 | 126, n)
    else:
        hdr = struct.pack("!BBQ", b0, 0x80 | 127, n)
    return hdr + b"\0\0\0\0" + payload


WS_CLOSE = ws_frame(0x8, struct.pack("!H", 1000))


def ws_messages(n: int, size: int) -> tuple[list, bytes]:
    return [("/", WSHandler)], ws_handshake() + ws_frame(
        0x2, b"x" * size
    ) * n + WS_CLOSE


def ws_fragments(n: int, size: int) -> tuple[list, bytes]:
    # One message made of n continuation frames. Empty fragments never
    # approach max_message_size.
    frag = ws_frame(0x0, b"x" * size, fin=False)
    msg = ws_frame(0x2, b"", fin=False) + frag * n + ws_frame(0x0, b"")
    return [("/", WSHandler)], ws_handshake() + msg + WS_CLOSE


def ws_deflate(n: int, size: int) -> tuple[list, bytes]:
    c = zlib.compressobj(wbits=-15)
    payload = c.compress(b"x" * size) + c.flush(zlib.Z_SYNC_FLUSH)
    assert payload.endswith(b"\x00\x00\xff\xff")
    # Each message is compressed with a fresh context, so it doesn't refer
    # back to earlier data and is also valid for a decompressor that keeps
    # its context between messages.
    frame = ws_frame(0x2, payload[:-4], rsv1=True)
    return [("/", WSDeflateHandler)], ws_handshake(deflate=True) + frame * n + WS_CLOSE


def ws_pings(n: int, size: int) -> tuple[list, bytes]:
    # Each ping causes the server to write a pong. The client does not read
    # until it has sent everything, so pongs accumulate in the server's
    # write buffer once the socket buffers are full.
    return [("/", WSPingHandler)], ws_handshake() + ws_frame(
        0x9, b"x" * size
    ) * n + WS_CLOSE


SCENARIOS = {
    "http_pipelined": Scenario(http_pipelined, 30000, 0, "request"),
    "http_chunked": Scenario(
        http_chunked, 200000, 1, "chunk", dict(max_body_size=1 << 30)
    ),
    "http_chunked_streaming": Scenario(
        http_chunked_streaming, 200000, 1, "chunk", dict(max_body_size=1 << 30)
    ),
    "http_fixed": Scenario(
        http_fixed, 1000, 100000, "100KB", dict(max_body_size=1 << 30)
    ),
    "ws_messages": Scenario(ws_messages, 200000, 1, "message"),
    "ws_fragments": Scenario(ws_fragments, 200000, 0, "fragment"),
    "ws_deflate": Scenario(ws_deflate, 100000, 1, "message"),
    "ws_large": Scenario(ws_messages, 50, 1000000, "message"),
    "ws_pings": Scenario(ws_pings, 100000, 125, "ping"),
}


def client(port: int, data: bytes) -> None:
    s = socket.create_connection(("127.0.0.1", port))
    try:
        s.sendall(data)
        while s.recv(1 << 20):
            pass
    except OSError:
        pass
    finally:
        s.close()


async def run(name: str, sc: Scenario) -> None:
    global done, peak_write_buffer
    done = asyncio.Event()
    peak_write_buffer = 0
    n = options.n or sc.n
    size = sc.size if options.size < 0 else options.size
    handlers, data = sc.build(n, size)
    app = web.Application(handlers)
    sockets = netutil.bind_sockets(0, "127.0.0.1")
    port = sockets[0].getsockname()[1]
    server = httpserver.HTTPServer(app, **sc.server_kwargs)
    server.add_sockets(sockets)

    max_stall = 0.0
    stop = False

    async def ticker() -> None:
        nonlocal max_stall
        last = time.perf_counter()
        while not stop:
            await asyncio.sleep(0.001)
            now = time.perf_counter()
            max_stall = max(max_stall, now - last)
            last = now

    ticker_task = asyncio.create_task(ticker())
    await asyncio.sleep(0.01)
    max_stall = 0.0
    if options.tracemalloc:
        tracemalloc.start()
    cpu0 = time.thread_time()
    wall0 = time.perf_counter()
    thread = threading.Thread(target=client, args=(port, data))
    thread.start()
    await done.wait()
    cpu = time.thread_time() - cpu0
    wall = time.perf_counter() - wall0
    mem = ""
    if options.tracemalloc:
        mem = " peak_mem=%.1fMB" % (tracemalloc.get_traced_memory()[1] / 1e6)
        tracemalloc.stop()
    stop = True
    await ticker_task
    server.stop()
    await server.close_all_connections()
    thread.join()
    wbuf = (
        " peak_write_buffer=%.1fMB" % (peak_write_buffer / 1e6)
        if peak_write_buffer
        else ""
    )
    print(
        f"{name:24s} n={n} size={size} wire={len(data) / 1e6:.1f}MB "
        f"cpu={cpu:.2f}s wall={wall:.2f}s "
        f"us/{sc.unit}={cpu / n * 1e6:.2f} us/byte={cpu / len(data) * 1e6:.3f} "
        f"max_stall={max_stall * 1000:.0f}ms{mem}{wbuf}"
    )
    sys.stdout.flush()


async def main() -> None:
    options.logging = "warning"  # access logs would dominate some scenarios
    parse_command_line()
    names = options.scenario or list(SCENARIOS)
    for name in names:
        await run(name, SCENARIOS[name])


if __name__ == "__main__":
    asyncio.run(main())
