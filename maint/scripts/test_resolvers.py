#!/usr/bin/env python
"""Basic test for Tornado resolvers.

Queries real domain names and prints the results from each resolver.
Requires a working internet connection, which is why it's not in a
unit test.

Will be removed in Tornado 7.0 when the pluggable resolver system is
removed.
"""
import pprint
import socket

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.netutil import Resolver, ThreadedResolver, DefaultExecutorResolver
from tornado.options import parse_command_line, define, options

try:
    import pycares
except ImportError:
    pycares = None

define(
    "family", default="unspec", help="Address family to query: unspec, inet, or inet6"
)


@gen.coroutine
def main():
    args = parse_command_line()

    if not args:
        args = ["localhost", "www.google.com", "www.facebook.com", "www.dropbox.com"]

    resolvers = [Resolver(), ThreadedResolver(), DefaultExecutorResolver()]

    if pycares is not None:
        from tornado.platform.caresresolver import CaresResolver

        resolvers.append(CaresResolver())

    family = {
        "unspec": socket.AF_UNSPEC,
        "inet": socket.AF_INET,
        "inet6": socket.AF_INET6,
    }[options.family]

    for host in args:
        print("Resolving %s" % host)
        for resolver in resolvers:
            try:
                addrinfo = yield resolver.resolve(host, 80, family)
            except Exception as e:
                print("%s: %s: %s" % (resolver.__class__.__name__, type(e), e))
            else:
                print(
                    "%s: %s" % (resolver.__class__.__name__, pprint.pformat(addrinfo))
                )
        print()


if __name__ == "__main__":
    IOLoop.instance().run_sync(main)
