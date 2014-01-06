from __future__ import absolute_import, division, print_function, with_statement

import signal
import socket
from subprocess import Popen
import sys
import time

from tornado.netutil import BlockingResolver, ThreadedResolver, is_valid_ip
from tornado.stack_context import ExceptionStackContext
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
    def skipOnCares(self):
        # Some DNS-hijacking ISPs (e.g. Time Warner) return non-empty results
        # with an NXDOMAIN status code.  Most resolvers treat this as an error;
        # C-ares returns the results, making the "bad_host" tests unreliable.
        # C-ares will try to resolve even malformed names, such as the
        # name with spaces used in this test.
        if self.resolver.__class__.__name__ == 'CaresResolver':
            self.skipTest("CaresResolver doesn't recognize fake NXDOMAIN")

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

    def test_bad_host(self):
        self.skipOnCares()
        def handler(exc_typ, exc_val, exc_tb):
            self.stop(exc_val)
            return True  # Halt propagation.

        with ExceptionStackContext(handler):
            self.resolver.resolve('an invalid domain', 80, callback=self.stop)

        result = self.wait()
        self.assertIsInstance(result, Exception)

    @gen_test
    def test_future_interface_bad_host(self):
        self.skipOnCares()
        with self.assertRaises(Exception):
            yield self.resolver.resolve('an invalid domain', 80,
                                        socket.AF_UNSPEC)


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


@unittest.skipIf(futures is None, "futures module not present")
class ThreadedResolverImportTest(unittest.TestCase):
    def test_import(self):
        TIMEOUT = 5

        # Test for a deadlock when importing a module that runs the
        # ThreadedResolver at import-time. See resolve_test.py for
        # full explanation.
        command = [
            sys.executable,
            '-c',
            'import tornado.test.resolve_test_helper']

        start = time.time()
        popen = Popen(command, preexec_fn=lambda: signal.alarm(TIMEOUT))
        while time.time() - start < TIMEOUT:
            return_code = popen.poll()
            if return_code is not None:
                self.assertEqual(0, return_code)
                return  # Success.
            time.sleep(0.05)

        self.fail("import timed out")


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
        self.assertTrue(not is_valid_ip(''))
        self.assertTrue(not is_valid_ip(' '))
        self.assertTrue(not is_valid_ip('\n'))
        self.assertTrue(not is_valid_ip('\x00'))
