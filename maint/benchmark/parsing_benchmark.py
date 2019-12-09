#!/usr/bin/env python
import re
import timeit
from enum import Enum
from typing import Callable

from tornado.httputil import HTTPHeaders
from tornado.options import define, options, parse_command_line


define("benchmark", type=str)
define("num_runs", type=int, default=1)


_CRLF_RE = re.compile(r"\r?\n")
_TEST_HEADERS = (
    "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,"
    "image/apng,*/*;q=0.8,application/signed-exchange;v=b3\r\n"
    "Accept-Encoding: gzip, deflate, br\r\n"
    "Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7\r\n"
    "Cache-Control: max-age=0\r\n"
    "Connection: keep-alive\r\n"
    "Host: example.com\r\n"
    "Upgrade-Insecure-Requests: 1\r\n"
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36\r\n"
)


def headers_split_re(headers: str) -> None:
    for line in _CRLF_RE.split(headers):
        pass


def headers_split_simple(headers: str) -> None:
    for line in headers.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]


def headers_parse_re(headers: str) -> HTTPHeaders:
    h = HTTPHeaders()
    for line in _CRLF_RE.split(headers):
        if line:
            h.parse_line(line)
    return h


def headers_parse_simple(headers: str) -> HTTPHeaders:
    h = HTTPHeaders()
    for line in headers.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        if line:
            h.parse_line(line)
    return h


def run_headers_split():
    regex_time = timeit.timeit(lambda: headers_split_re(_TEST_HEADERS), number=100000)
    print("regex", regex_time)

    simple_time = timeit.timeit(
        lambda: headers_split_simple(_TEST_HEADERS), number=100000
    )
    print("str.split", simple_time)

    print("speedup", regex_time / simple_time)


def run_headers_full():
    regex_time = timeit.timeit(lambda: headers_parse_re(_TEST_HEADERS), number=10000)
    print("regex", regex_time)

    simple_time = timeit.timeit(
        lambda: headers_parse_simple(_TEST_HEADERS), number=10000
    )
    print("str.split", simple_time)

    print("speedup", regex_time / simple_time)


class Benchmark(Enum):
    def __new__(cls, arg_value: str, func: Callable[[], None]):
        member = object.__new__(cls)
        member._value_ = arg_value
        member.func = func
        return member

    HEADERS_SPLIT = ("headers-split", run_headers_split)
    HEADERS_FULL = ("headers-full", run_headers_full)


def main():
    parse_command_line()

    try:
        func = Benchmark(options.benchmark).func
    except ValueError:
        known_benchmarks = [benchmark.value for benchmark in Benchmark]
        print(
            "Unknown benchmark: '{}', supported values are: {}"
            .format(options.benchmark, ", ".join(known_benchmarks))
        )
        return

    for _ in range(options.num_runs):
        func()


if __name__ == '__main__':
    main()
