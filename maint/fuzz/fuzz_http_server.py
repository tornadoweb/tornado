#!/usr/bin/env python
# Fuzzes the HTTP/1 server: each input is sent as the bytes of one
# connection to an HTTPServer, whose application reads every part of the
# request (arguments, files, cookies), checks its origin, and has a websocket
# endpoint with compression, so that the input can continue with websocket
# frames.
# Malformed input should get an error response or a closed connection;
# anything Tornado logs as an error (usually an unexpected exception) is a
# crash.
#
# Usage (from the root of the repo; see README.md):
#   PYTHONPATH=. python maint/fuzz/fuzz_http_server.py -max_total_time=600

import asyncio
import base64
import os
import socket
import struct
import zlib

import atheris
import common

with atheris.instrument_imports(include=["tornado"]):
    from tornado.httpserver import HTTPServer
    from tornado.iostream import IOStream
    from tornado.test import security_corpus_test
    from tornado.web import Application, RequestHandler
    from tornado.websocket import WebSocketClosedError, WebSocketHandler


class EchoHandler(RequestHandler):
    def get(self) -> None:
        self.post()

    def post(self) -> None:
        self.write(
            {
                "cookies": len(self.cookies),
                "arguments": len(self.request.arguments),
                "files": len(self.request.files),
                "host": self.request.host_name,
            }
        )

    put = patch = delete = options = post


class EchoWebSocket(WebSocketHandler):
    def get_compression_options(self) -> dict[str, object]:
        return {}

    def on_message(self, message: str | bytes) -> None:
        try:
            self.write_message(message, binary=isinstance(message, bytes))
        except WebSocketClosedError:
            # The input ended or closed the connection first.
            pass


async def handle(data: bytes) -> None:
    client, server = socket.socketpair()
    server_stream = IOStream(server)
    client_stream = IOStream(client)
    try:
        SERVER.handle_stream(server_stream, ("127.0.0.1", 1234))
        await client_stream.write(data)
        # Half-close so that the server sees the end of the input.
        client.shutdown(socket.SHUT_WR)
        await asyncio.wait_for(client_stream.read_until_close(), 5)
    finally:
        client_stream.close()
        server_stream.close()
    # Let the server finish with the connection.
    await asyncio.sleep(0)


def test_one_input(data: bytes) -> None:
    LOOP.run_until_complete(handle(data))
    ERRORS.check()


def seeds() -> list[bytes]:
    cases = [c.request for c in security_corpus_test.CASES if c.app == "default"]
    cases += [
        s.build(n)
        for s in security_corpus_test.SCALING
        if s.app == "default"
        for n in (1, 10)
    ]
    # Two requests on one connection, and a request with a chunked body.
    get = b"GET /echo?a=b HTTP/1.1\r\nHost: example.com\r\nCookie: a=b\r\n\r\n"
    cases.append(get + get)
    cases.append(
        b"POST /echo HTTP/1.1\r\nHost: example.com\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/x-www-form-urlencoded\r\n\r\n"
        b"3\r\na=b\r\n0\r\n\r\n"
    )
    # Origin checks (cross_origin_protection is on).
    cases.append(
        b"POST /echo HTTP/1.1\r\nHost: example.com\r\n"
        b"Origin: http://example.com\r\nContent-Length: 3\r\n\r\na=b"
    )
    cases += [ws_handshake(ext) + frames for ext, frames in ws_seeds()]
    cases.append(ws_handshake("", origin="https://trusted.example.com"))
    return cases


def ws_handshake(extensions: str, origin: str = "") -> bytes:
    key = base64.b64encode(os.urandom(16)).decode()
    return (
        "GET /ws HTTP/1.1\r\nHost: example.com\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        + (f"Sec-WebSocket-Extensions: {extensions}\r\n" if extensions else "")
        + (f"Origin: {origin}\r\n" if origin else "")
        + "\r\n"
    ).encode()


def ws_frame(
    opcode: int, payload: bytes, fin: bool = True, rsv1: bool = False
) -> bytes:
    # Client frames are masked; a zero mask keeps the payload readable.
    head = bytes([(0x80 if fin else 0) | (0x40 if rsv1 else 0) | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack("!Q", n)
    return head + b"\0\0\0\0" + payload


def deflate(data: bytes) -> bytes:
    c = zlib.compressobj(wbits=-15)
    return (c.compress(data) + c.flush(zlib.Z_SYNC_FLUSH))[:-4]


def ws_seeds() -> list[tuple[str, bytes]]:
    text = ws_frame(1, b"hello")
    fragments = ws_frame(1, b"hel", fin=False) + ws_frame(0, b"lo")
    ping = ws_frame(9, b"p")
    close = ws_frame(8, struct.pack("!H", 1000))
    big = ws_frame(2, b"x" * 300)
    pmd = "permessage-deflate"
    return [
        ("", text + fragments + ping + close),
        ("", big + close),
        (pmd, ws_frame(1, deflate(b"hello" * 10), rsv1=True) + close),
        (
            pmd + "; client_max_window_bits; server_no_context_takeover",
            ws_frame(1, deflate(b"hello"), rsv1=True) + text + close,
        ),
        (pmd + "; server_max_window_bits=10, " + pmd, text + close),
    ]


ERRORS = common.ErrorLog()
ERRORS.install()
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)
SERVER = HTTPServer(
    Application(
        [("/echo", EchoHandler), ("/ws", EchoWebSocket)],
        websocket_max_message_size=1 << 20,
        cross_origin_protection=True,
        trusted_origins=["https://trusted.example.com"],
    )
)

if __name__ == "__main__":
    common.main("http_server", test_one_input, seeds())
