#!/usr/bin/env python
# Fuzzes the parsers in tornado.httputil directly, which is much faster than
# going through a server. The first byte of each input picks the parser and
# the rest is its input. Each parser may reject its input with
# HTTPInputError (parse_cookie never rejects); any other exception is a
# crash.
#
# Usage (from the root of the repo; see README.md):
#   PYTHONPATH=. python maint/fuzz/fuzz_httputil.py -max_total_time=600

import atheris
import common

with atheris.instrument_imports(include=["tornado"]):
    from tornado import httputil
    from tornado.httputil import HTTPInputError
    from tornado.test import security_corpus_test


def headers(data: bytes) -> None:
    # HTTP1Connection decodes the header block as latin1.
    h = httputil.HTTPHeaders.parse(data.decode("latin1"))
    # Parsing what the headers turn back into gives the same headers.
    again = httputil.HTTPHeaders.parse("".join(f"{k}: {v}\r\n" for k, v in h.get_all()))
    assert list(again.get_all()) == list(h.get_all()), (h, again)


def start_line(data: bytes) -> None:
    httputil.parse_request_start_line(data.decode("latin1"))


def response_start_line(data: bytes) -> None:
    httputil.parse_response_start_line(data.decode("latin1"))


def cookie(data: bytes) -> None:
    httputil.parse_cookie(data.decode("latin1"))


def header_params(data: bytes) -> None:
    value = data.decode("latin1")
    if httputil._FORBIDDEN_HEADER_CHARS_RE.search(value):
        # Not a possible header value.
        return
    try:
        httputil._parse_header(value)
    except ValueError:
        # From an RFC 2231 parameter with a strange charset. Both callers
        # (multipart parsing and websocket extension negotiation) handle
        # ValueError.
        pass


def multipart(data: bytes) -> None:
    args: dict[str, list[bytes]] = {}
    files: dict[str, list[httputil.HTTPFile]] = {}
    try:
        httputil.parse_multipart_form_data(b"1234", data, args, files)
    except UnicodeDecodeError:
        # Part headers that aren't UTF-8. parse_body_arguments turns this
        # (and any other exception) into HTTPInputError.
        pass


def body(data: bytes) -> None:
    # The first line is the Content-Type.
    content_type, _, rest = data.partition(b"\n")
    args: dict[str, list[bytes]] = {}
    files: dict[str, list[httputil.HTTPFile]] = {}
    httputil.parse_body_arguments(content_type.decode("latin1"), rest, args, files)


TARGETS = [
    headers,
    start_line,
    response_start_line,
    cookie,
    header_params,
    multipart,
    body,
]


def test_one_input(data: bytes) -> None:
    if not data:
        return
    target = TARGETS[data[0] % len(TARGETS)]
    try:
        target(data[1:])
    except HTTPInputError:
        pass


def seeds() -> list[bytes]:
    def seed(target: object, data: bytes) -> bytes:
        return bytes([TARGETS.index(target)]) + data  # type: ignore[arg-type]

    result = []
    requests = [c.request for c in security_corpus_test.CASES] + [
        s.build(n) for s in security_corpus_test.SCALING for n in (1, 10)
    ]
    for request in requests:
        head, _, rest = request.partition(b"\r\n\r\n")
        line, _, header_block = head.partition(b"\r\n")
        result.append(seed(start_line, line))
        result.append(seed(headers, header_block + b"\r\n"))
        h = httputil.HTTPHeaders.parse(header_block.decode("latin1") + "\r\n")
        for value in h.get_list("Cookie"):
            result.append(seed(cookie, value.encode("latin1")))
        if "Content-Type" in h:
            content_type = h["Content-Type"].encode("latin1")
            result.append(seed(header_params, content_type))
            result.append(seed(body, content_type + b"\n" + rest))
            if content_type.startswith(b"multipart/"):
                result.append(seed(multipart, rest))
    result.append(seed(response_start_line, b"HTTP/1.1 200 OK"))
    return result


ERRORS = common.ErrorLog()
ERRORS.install()

if __name__ == "__main__":
    common.main("httputil", test_one_input, seeds())
