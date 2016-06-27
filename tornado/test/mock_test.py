from __future__ import absolute_import

try:
    from unittest import mock
except ImportError:
    import mock

from tornado.test.util import unittest
from tornado.mock import FutureMock, TaskMock
from tornado import gen


class TaskMockTest(unittest.TestCase):
    def test_called_callback(self):
        callback = mock.Mock()
        task_mock = TaskMock(return_value=42)
        result = task_mock(callback=callback)
        self.assertEqual(result, 42)
        callback.assert_called_once_with(42)


class FutureMockTest(unittest.TestCase):
    def test_returns_future(self):
        future_mock = FutureMock(return_value=42)
        result = future_mock()
        self.assertIsInstance(result, gen.Future)
        self.assertEqual(result.result(), 42)
