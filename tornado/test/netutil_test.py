from __future__ import absolute_import, division, with_statement

import socket

from tornado.netutil import Resolver, CachedResolver
from tornado.testing import AsyncTestCase
from tornado.test.util import unittest

try:
    from concurrent import futures
except ImportError:
    futures = None

class _ResolverTestMixin(object):
    def test_localhost(self):
        self.resolver.getaddrinfo('localhost', 80, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM,
                                  callback=self.stop)
        future = self.wait()
        self.assertIn(
            (socket.AF_INET, socket.SOCK_STREAM, system_getaddr_proto, '',
             ('127.0.0.1', 80)),
            future.result())


class _CachedTestMixin(object):
    def test_cached_localhost(self):
        # Fill the cache with a regular lookup
        self.resolver.getaddrinfo('localhost', 80, socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            callback=self.stop)
        future = self.wait()
        self.assertIn(
            (socket.AF_INET, socket.SOCK_STREAM, system_getaddr_proto, '',
             ('127.0.0.1', 80)),
            future.result())

        # Entry should now be in the cache
        self.assertIn('localhost', self.resolver.resolve_cache.keys())
        self.assertIn(
            (socket.AF_INET, socket.SOCK_STREAM, system_getaddr_proto, '',
            ('127.0.0.1', 80)), self.resolver.resolve_cache.get('localhost'))


class SyncResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(SyncResolverTest, self).setUp()
        self.resolver = Resolver(self.io_loop)


class SyncCachedResolvedTest(AsyncTestCase, _CachedTestMixin):
    def setUp(self):
        super(SyncCachedResolvedTest, self).setUp()
        self.resolver = CachedResolver(self.io_loop)


class ThreadedResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(ThreadedResolverTest, self).setUp()
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(2)
        self.resolver = Resolver(self.io_loop, self.executor)

    def tearDown(self):
        self.executor.shutdown()
        super(ThreadedResolverTest, self).tearDown()


# socket.getaddrinfo returns IPPROTO_IP on Windows and IPPROTO_TCP on linux
system_getaddr_proto = socket.getaddrinfo('localhost', 80)[0][2]

ThreadedResolverTest = unittest.skipIf(
    futures is None, "futures module not present")(ThreadedResolverTest)
