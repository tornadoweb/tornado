#!/usr/bin/env python
#
# A set of short benchmarks whose results can be compared between two
# versions of Tornado. Each benchmark reports one number, the CPU time
# per unit of work. compare_benchmarks.py runs this script against two
# checkouts and reports the differences; the CI benchmark job uses that to
# catch performance regressions in PRs.
#
# Usage (from the root of the repo):
#   PYTHONPATH=. python maint/benchmark/ci_benchmark.py
#   PYTHONPATH=. python maint/benchmark/ci_benchmark.py --only headers_many
#
# This prints one measurement of each benchmark as JSON. With --worker it
# instead reads benchmark names from stdin and answers each with one
# measurement on a line of JSON, which lets compare_benchmarks.py
# interleave measurements of two versions.
#
# A parser measurement repeats the call until it has run for a minimum time
# and takes the fastest of several such repetitions; server benchmarks
# reuse the scenarios in dos_benchmark.py, measuring the CPU time of the
# server thread only.
#
# BUDGETS sets absolute ceilings for the adversarial inputs, in
# microseconds per input byte. They are set several times above what a
# 2026 laptop measures, so that any CI runner passes them comfortably. They
# are a backstop for the per-PR comparison: a regression that creeps in a
# little at a time can't exceed them.

import argparse
import asyncio
import json
import sys
import time
import typing
from collections.abc import Callable

import dos_benchmark

from tornado import escape, httputil, util


class Benchmark(typing.NamedTuple):
    # Returns CPU seconds for the given number of units of work.
    run: Callable[[], float]
    units: int
    unit: str


# Minimum CPU time for one parser repetition, in seconds. Short
# measurements are dominated by timer resolution and scheduling noise.
_MIN_TIME = 0.02


def parser(func: Callable[[], object], units: int, unit: str) -> Benchmark:
    def run() -> float:
        func()  # warm up caches
        best = float("inf")
        for _ in range(5):
            count = 0
            start = time.thread_time()
            while True:
                func()
                count += 1
                elapsed = time.thread_time() - start
                if elapsed >= _MIN_TIME:
                    break
            best = min(best, elapsed / count)
        return best

    return Benchmark(run, units, unit)


def server(name: str, n: int, per_byte: bool = True) -> Benchmark:
    sc = dos_benchmark.SCENARIOS[name]
    _, data = sc.build(n, sc.size)
    warmed_up = False

    def run() -> float:
        nonlocal warmed_up
        if not warmed_up:
            # The first run in a process pays for imports and warmup.
            asyncio.run(dos_benchmark.measure(sc, max(1, n // 10), sc.size))
            warmed_up = True
        return asyncio.run(dos_benchmark.measure(sc, n, sc.size)).cpu

    if per_byte:
        return Benchmark(run, len(data), "byte")
    return Benchmark(run, n, sc.unit)


TYPICAL_HEADERS = (
    "Host: example.com\r\n"
    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 "
    "Firefox/140.0\r\n"
    "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    "Accept-Language: en-US,en;q=0.5\r\n"
    "Accept-Encoding: gzip, deflate, br, zstd\r\n"
    "Connection: keep-alive\r\n"
    "Cookie: session=abcdef0123456789; theme=dark; _ga=GA1.1.123456789.1700000000\r\n"
    "Upgrade-Insecure-Requests: 1\r\n"
)

# Default limits bound the adversarial inputs: max_header_size is 64KB and
# the default max_parts for multipart bodies is 100.
MANY_HEADERS = "".join(f"X{i}: b\r\n" for i in range(8_000))
REPEATED_HEADERS = "X: a\r\n" * 10_000
MANY_COOKIES = "".join(f"{i}=;" for i in range(10_000))
MANY_PARAMS = "form-data" + "; a=b" * 10_000
MULTIPART_PART = (
    b"--1234\r\n"
    b'Content-Disposition: form-data; name="a"; filename="b"\r\n'
    b"Content-Type: text/plain\r\n\r\n\r\n"
)
MULTIPART_PARTS = MULTIPART_PART * 99 + b"--1234--\r\n"
MULTIPART_LARGE = (
    b"--1234\r\n"
    b'Content-Disposition: form-data; name="a"; filename="b"\r\n\r\n'
    + b"x" * 1_000_000
    + b"\r\n--1234--\r\n"
)
MASK_DATA = b"x" * 65536
ESCAPE_TEXT = '<p>Tom & Jerry\'s "show"</p> ' * 2_000


def parse_multipart(body: bytes) -> None:
    args: dict[str, list[bytes]] = {}
    files: dict[str, list[httputil.HTTPFile]] = {}
    httputil.parse_multipart_form_data(b"1234", body, args, files)


BENCHMARKS: dict[str, Benchmark] = {
    "headers_typical": parser(
        lambda: httputil.HTTPHeaders.parse(TYPICAL_HEADERS),
        len(TYPICAL_HEADERS),
        "byte",
    ),
    "headers_many": parser(
        lambda: httputil.HTTPHeaders.parse(MANY_HEADERS), len(MANY_HEADERS), "byte"
    ),
    "headers_repeated": parser(
        lambda: httputil.HTTPHeaders.parse(REPEATED_HEADERS),
        len(REPEATED_HEADERS),
        "byte",
    ),
    "start_line": parser(
        lambda: httputil.parse_request_start_line("GET /foo/bar?a=b HTTP/1.1"),
        1,
        "line",
    ),
    "cookies_many": parser(
        lambda: httputil.parse_cookie(MANY_COOKIES), len(MANY_COOKIES), "byte"
    ),
    "header_params": parser(
        lambda: httputil._parse_header(MANY_PARAMS), len(MANY_PARAMS), "byte"
    ),
    "multipart_parts": parser(
        lambda: parse_multipart(MULTIPART_PARTS), len(MULTIPART_PARTS), "byte"
    ),
    "multipart_large": parser(
        lambda: parse_multipart(MULTIPART_LARGE), len(MULTIPART_LARGE), "byte"
    ),
    "websocket_mask": parser(
        lambda: util._websocket_mask(b"abcd", MASK_DATA), len(MASK_DATA), "byte"
    ),
    "xhtml_escape": parser(
        lambda: escape.xhtml_escape(ESCAPE_TEXT), len(ESCAPE_TEXT), "byte"
    ),
    "http_requests": server("http_pipelined", 2_000, per_byte=False),
    "http_chunked": server("http_chunked", 50_000),
    "http_fixed": server("http_fixed", 1_000),
    "ws_messages": server("ws_messages", 50_000),
    "ws_fragments": server("ws_fragments", 50_000),
    "ws_deflate": server("ws_deflate", 30_000),
    "ws_large": server("ws_large", 50),
}

# Ceilings in microseconds per unit (see the comment at the top).
BUDGETS: dict[str, float] = {
    "headers_many": 2.0,
    "headers_repeated": 2.0,
    "cookies_many": 0.5,
    "header_params": 2.0,
    "multipart_parts": 1.0,
    "http_chunked": 8.0,
    "ws_messages": 8.0,
    "ws_fragments": 8.0,
    "ws_deflate": 8.0,
}


def measure(name: str) -> dict[str, typing.Any]:
    bm = BENCHMARKS[name]
    result: dict[str, typing.Any] = {"unit": bm.unit, "budget": BUDGETS.get(name)}
    try:
        result["us_per_unit"] = bm.run() / bm.units * 1e6
    except Exception as e:
        # Probably a benchmark of something the other version under
        # comparison lacks.
        result["error"] = repr(e)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", help="benchmarks to run")
    parser.add_argument(
        "--worker", action="store_true", help="read benchmark names from stdin"
    )
    parser.add_argument("--list", action="store_true", help="print the benchmark names")
    args = parser.parse_args()
    if args.list:
        print("\n".join(BENCHMARKS))
    elif args.worker:
        for line in sys.stdin:
            print(json.dumps(measure(line.strip())), flush=True)
    else:
        results = {name: measure(name) for name in args.only or BENCHMARKS}
        json.dump(results, sys.stdout, indent=1)
        print()


if __name__ == "__main__":
    main()
