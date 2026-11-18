# The parsers in tornado.httputil, each fuzzed directly by its own
# fuzz_httputil_<name>.py, which is much faster than going through a server.
# Each parser may reject its input with HTTPInputError (parse_cookie never
# rejects); any other exception is a crash.
#
# Each parser is a separate fuzzer so that crash minimization can't wander
# from one parser to another, which changes the crash's stack and makes
# OSS-Fuzz discard the result.

from collections.abc import Callable

import atheris
import common

with atheris.instrument_imports(include=["tornado"]):
    from tornado import httputil
    from tornado.httputil import HTTPInputError


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


def seeds() -> dict[Callable[[bytes], None], list[bytes]]:
    """Seed inputs for each parser, from tornado's regression corpus."""
    # Only needed for seeds, so it's imported here (and not instrumented)
    # to keep it out of every fuzzer process's startup.
    from tornado.test import security_corpus_test

    result: dict[Callable[[bytes], None], list[bytes]] = {
        t: []
        for t in [
            headers,
            start_line,
            response_start_line,
            cookie,
            header_params,
            multipart,
            body,
        ]
    }
    requests = [c.request for c in security_corpus_test.CASES] + [
        s.build(n) for s in security_corpus_test.SCALING for n in (1, 10)
    ]
    for request in requests:
        head, _, rest = request.partition(b"\r\n\r\n")
        line, _, header_block = head.partition(b"\r\n")
        result[start_line].append(line)
        result[headers].append(header_block + b"\r\n")
        h = httputil.HTTPHeaders.parse(header_block.decode("latin1") + "\r\n")
        for value in h.get_list("Cookie"):
            result[cookie].append(value.encode("latin1"))
        if "Content-Type" in h:
            content_type = h["Content-Type"].encode("latin1")
            result[header_params].append(content_type)
            result[body].append(content_type + b"\n" + rest)
            if content_type.startswith(b"multipart/"):
                result[multipart].append(rest)
    result[response_start_line].append(b"HTTP/1.1 200 OK")
    return result


ERRORS = common.ErrorLog()
ERRORS.install()


def main(target: Callable[[bytes], None]) -> None:
    """Runs the fuzzer for one parser (see common.main)."""
    name = "httputil_" + target.__name__

    def test_one_input(data: bytes) -> None:
        try:
            target(data)
        except HTTPInputError:
            pass

    common.main(name, test_one_input, lambda: seeds()[target])
