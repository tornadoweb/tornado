from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.netutil import BlockingResolver, ThreadedResolver, is_valid_ip
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest

try:
    from concurrent import futures
except ImportError:
    futures = None


class _ResolverTestMixin(object):
    def test_localhost(self):
        self.resolver.resolve('localhost', 80, callback=self.stop)
        future = self.wait()
        self.assertIn((socket.AF_INET, ('127.0.0.1', 80)),
                      future.result())

    @gen_test
    def test_future_interface(self):
        addrinfo = yield self.resolver.resolve('localhost', 80,
                                               socket.AF_UNSPEC)
        self.assertIn((socket.AF_INET, ('127.0.0.1', 80)),
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


class IsValidIPTest(unittest.TestCase):
    def test_is_valid_ip(self):
        self.assertTrue(is_valid_ip('127.0.0.1'))
        self.assertTrue(is_valid_ip('4.4.4.4'))
        self.assertTrue(is_valid_ip('::1'))
        self.assertTrue(is_valid_ip('2620:0:1cfe:face:b00c::3'))
        self.assertTrue(not is_valid_ip('www.google.com'))
        self.assertTrue(not is_valid_ip('localhost'))
        self.assertTrue(not is_valid_ip('4.4.4.4<'))
        self.assertTrue(not is_valid_ip(' 127.0.0.1'))
