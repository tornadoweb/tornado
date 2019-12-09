#!/usr/bin/env python
import pprint
import socket

from tornado import gen
from tornado.ioloop import IOLoop
from tornado.netutil import Resolver, ThreadedResolver
from tornado.options import parse_command_line, define, options

try:
    import twisted
except ImportError:
    twisted = None

try:
    import pycares
except ImportError:
    pycares = None

define('family', default='unspec',
       help='Address family to query: unspec, inet, or inet6')


@gen.coroutine
def main():
    args = parse_command_line()

    if not args:
        args = ['localhost', 'www.google.com',
                'www.facebook.com', 'www.dropbox.com']

    resolvers = [Resolver(), ThreadedResolver()]

    if twisted is not None:
        from tornado.platform.twisted import TwistedResolver
        resolvers.append(TwistedResolver())

    if pycares is not None:
        from tornado.platform.caresresolver import CaresResolver
        resolvers.append(CaresResolver())

    family = {
        'unspec': socket.AF_UNSPEC,
        'inet': socket.AF_INET,
        'inet6': socket.AF_INET6,
    }[options.family]

    for host in args:
        print('Resolving %s' % host)
        for resolver in resolvers:
            addrinfo = yield resolver.resolve(host, 80, family)
            print('%s: %s' % (resolver.__class__.__name__,
                              pprint.pformat(addrinfo)))
        print()


if __name__ == '__main__':
    IOLoop.instance().run_sync(main)
