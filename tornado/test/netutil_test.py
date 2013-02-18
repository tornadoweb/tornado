from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.netutil import BlockingResolver, ThreadedResolver
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest

try:
    from concurrent import futures
except ImportError:
    futures = None


class _ResolverTestMixin(object):
    def test_localhost(self):
        # Note that windows returns IPPROTO_IP unless we specifically
        # ask for IPPROTO_TCP (either will work to create a socket,
        # but this test looks for an exact match)
        self.resolver.getaddrinfo('localhost', 80, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM,
                                  socket.IPPROTO_TCP,
                                  callback=self.stop)
        future = self.wait()
        self.assertIn(
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '',
             ('127.0.0.1', 80)),
            future.result())

    @gen_test
    def test_future_interface(self):
        addrinfo = yield self.resolver.getaddrinfo(
            'localhost', 80, socket.AF_UNSPEC,
            socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.assertIn(
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '',
             ('127.0.0.1', 80)),
            addrinfo)



class BlockingResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(BlockingResolverTest, self).setUp()
        self.resolver = BlockingResolver(io_loop=self.io_loop)


@unittest.skipIf(futures is None, "futures module not present")
class ThreadedResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(ThreadedResolverTest, self).setUp()
        self.resolver = ThreadedResolver(io_loop=self.io_loop)

    def tearDown(self):
        self.resolver.executor.shutdown()
        super(ThreadedResolverTest, self).tearDown()
