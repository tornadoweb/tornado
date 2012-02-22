#!/usr/bin/env python

from __future__ import absolute_import, division, with_statement
import unittest
import time
from tornado.testing import AsyncTestCase, LogTrapTestCase


class AsyncTestCaseTest(AsyncTestCase, LogTrapTestCase):
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
        self.io_loop.add_timeout(time.time() + 0.001, self.stop)
        self.wait(timeout = 0.002)
        self.io_loop.add_timeout(time.time() + 0.003, self.stop)
        self.wait(timeout = 0.01)

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

if __name__ == '__main__':
    unittest.main()
