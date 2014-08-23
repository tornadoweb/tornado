from __future__ import absolute_import, division, print_function, with_statement

try:
    import asyncio
except ImportError:
    pass

import time
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest


class AsyncIoTest(AsyncTestCase):
    """Test yielding asyncio.Future from gen.coroutine"""

    def setUp(self):
        if asyncio is None:
            raise unittest.SkipTest('AsyncIoTest requires asyncio.')
        super(AsyncIoTest, self).setUp()

    def get_new_ioloop(self):
        from tornado.platform.asyncio import AsyncIOLoop
        return AsyncIOLoop()

    @gen_test
    def test_asyncio_sleep(self):
        """yield asyncio.sleep(0.01) from gen.coroutine"""
        t = time.time()
        yield asyncio.Task(asyncio.sleep(0.01))
        delta = time.time() - t
        self.assertLess(delta, 0.1)


if __name__ == '__main__':
    unittest.main()
