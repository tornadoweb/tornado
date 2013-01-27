#!/usr/bin/env python

from __future__ import absolute_import, division, print_function, with_statement

from tornado import gen
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest


class AsyncTestCaseTest(AsyncTestCase):
    def test_exception_in_callback(self):
        self.io_loop.add_callback(lambda: 1 / 0)
        try:
            self.wait()
            self.fail("did not get expected exception")
        except ZeroDivisionError:
            pass

    def test_subsequent_wait_calls(self):
        """
        This test makes sure that a second call to wait()
        clears the first timeout.
        """
        self.io_loop.add_timeout(self.io_loop.time() + 0.01, self.stop)
        self.wait(timeout=0.02)
        self.io_loop.add_timeout(self.io_loop.time() + 0.03, self.stop)
        self.wait(timeout=0.15)


class SetUpTearDownTest(unittest.TestCase):
    def test_set_up_tear_down(self):
        """
        This test makes sure that AsyncTestCase calls super methods for
        setUp and tearDown.

        InheritBoth is a subclass of both AsyncTestCase and
        SetUpTearDown, with the ordering so that the super of
        AsyncTestCase will be SetUpTearDown.
        """
        events = []
        result = unittest.TestResult()

        class SetUpTearDown(unittest.TestCase):
            def setUp(self):
                events.append('setUp')

            def tearDown(self):
                events.append('tearDown')

        class InheritBoth(AsyncTestCase, SetUpTearDown):
            def test(self):
                events.append('test')

        InheritBoth('test').run(result)
        expected = ['setUp', 'test', 'tearDown']
        self.assertEqual(expected, events)


class GenTest(AsyncTestCase):
    def setUp(self):
        super(GenTest, self).setUp()
        self.finished = False

    def tearDown(self):
        self.assertTrue(self.finished)
        super(GenTest, self).tearDown()

    @gen_test
    def test_sync(self):
        self.finished = True

    @gen_test
    def test_async(self):
        yield gen.Task(self.io_loop.add_callback)
        self.finished = True

if __name__ == '__main__':
    unittest.main()
