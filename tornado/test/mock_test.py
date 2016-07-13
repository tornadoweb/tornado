from __future__ import absolute_import

try:
    # py33+
    from unittest import mock  # type: ignore
except ImportError:
    try:
        import mock  # type: ignore
    except ImportError:
        mock = None

from tornado.test.util import unittest
from tornado.mock import AsyncMock
from tornado import gen


class AsyncMockTest(unittest.TestCase):
    @unittest.skipIf(mock is None, 'mock package not present')
    def test_callback_called(self):
        callback = mock.Mock()
        async_mock = AsyncMock(return_value=42)
        async_mock(callback=callback)
        callback.assert_called_once_with(42)

    @unittest.skipIf(mock is None, 'mock package not present')
    def test_returns_future(self):
        async_mock = AsyncMock(return_value=42)
        result = async_mock()
        self.assertIsInstance(result, gen.Future)
        self.assertEqual(result.result(), 42)

    @unittest.skipIf(mock is None, 'mock package not present')
    def test_side_effect(self):
        async_mock = AsyncMock(side_effect=[1, 2])
        self._test_side_effect(async_mock, 1)
        self._test_side_effect(async_mock, 2)

    def _test_side_effect(self, async_mock, number):
        callback = mock.Mock()
        result = async_mock(callback=callback)
        self.assertEqual(result.result(), number)
        callback.assert_called_once_with(number)
