from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.netutil import BlockingResolver, ThreadedResolver, is_valid_ip
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest

try:
    from concurrent import futures
except ImportError:
    futures = None

try:
    import pycares
except ImportError:
    pycares = None
else:
    from tornado.platform.caresresolver import CaresResolver

try:
    import twisted
except ImportError:
    twisted = None
else:
    from tornado.platform.twisted import TwistedResolver


class _ResolverTestMixin(object):
    def test_localhost(self):
        self.resolver.resolve('localhost', 80, callback=self.stop)
        result = self.wait()
        self.assertIn((socket.AF_INET, ('127.0.0.1', 80)), result)

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
        self.resolver.close()
        super(ThreadedResolverTest, self).tearDown()


@unittest.skipIf(pycares is None, "pycares module not present")
class CaresResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(CaresResolverTest, self).setUp()
        self.resolver = CaresResolver(io_loop=self.io_loop)


@unittest.skipIf(twisted is None, "twisted module not present")
@unittest.skipIf(getattr(twisted, '__version__', '0.0') < "12.1", "old version of twisted")
class TwistedResolverTest(AsyncTestCase, _ResolverTestMixin):
    def setUp(self):
        super(TwistedResolverTest, self).setUp()
        self.resolver = TwistedResolver(io_loop=self.io_loop)


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
