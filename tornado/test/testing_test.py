#!/usr/bin/env python
import unittest
from tornado.testing import AsyncTestCase, LogTrapTestCase

class AsyncTestCaseTest(AsyncTestCase, LogTrapTestCase):
    def test_exception_in_callback(self):
        self.io_loop.add_callback(lambda: 1/0)
        try:
            self.wait()
            self.fail("did not get expected exception")
        except ZeroDivisionError:
            pass

if __name__ == '__main__':
    unittest.main
