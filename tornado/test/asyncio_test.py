# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import absolute_import, division, print_function

from tornado import gen
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest, skipBefore33, skipBefore35, exec_test

try:
    from tornado.platform.asyncio import asyncio
except ImportError:
    asyncio = None
else:
    from tornado.platform.asyncio import AsyncIOLoop, to_asyncio_future
    # This is used in dynamically-evaluated code, so silence pyflakes.
    to_asyncio_future


@unittest.skipIf(asyncio is None, "asyncio module not present")
class AsyncIOLoopTest(AsyncTestCase):
    def get_new_ioloop(self):
        io_loop = AsyncIOLoop()
        asyncio.set_event_loop(io_loop.asyncio_loop)
        return io_loop

    def test_asyncio_callback(self):
        # Basic test that the asyncio loop is set up correctly.
        asyncio.get_event_loop().call_soon(self.stop)
        self.wait()

    @gen_test
    def test_asyncio_future(self):
        # Test that we can yield an asyncio future from a tornado coroutine.
        # Without 'yield from', we must wrap coroutines in ensure_future,
        # which was introduced during Python 3.4, deprecating the prior "async".
        if hasattr(asyncio, 'ensure_future'):
            ensure_future = asyncio.ensure_future
        else:
            ensure_future = asyncio.async

        x = yield ensure_future(
            asyncio.get_event_loop().run_in_executor(None, lambda: 42))
        self.assertEqual(x, 42)

    @skipBefore33
    @gen_test
    def test_asyncio_yield_from(self):
        # Test that we can use asyncio coroutines with 'yield from'
        # instead of asyncio.async(). This requires python 3.3 syntax.
        namespace = exec_test(globals(), locals(), """
        @gen.coroutine
        def f():
            event_loop = asyncio.get_event_loop()
            x = yield from event_loop.run_in_executor(None, lambda: 42)
            return x
        """)
        result = yield namespace['f']()
        self.assertEqual(result, 42)

    @skipBefore35
    def test_asyncio_adapter(self):
        # This test demonstrates that when using the asyncio coroutine
        # runner (i.e. run_until_complete), the to_asyncio_future
        # adapter is needed. No adapter is needed in the other direction,
        # as demonstrated by other tests in the package.
        @gen.coroutine
        def tornado_coroutine():
            yield gen.Task(self.io_loop.add_callback)
            raise gen.Return(42)
        native_coroutine_without_adapter = exec_test(globals(), locals(), """
        async def native_coroutine_without_adapter():
            return await tornado_coroutine()
        """)["native_coroutine_without_adapter"]

        native_coroutine_with_adapter = exec_test(globals(), locals(), """
        async def native_coroutine_with_adapter():
            return await to_asyncio_future(tornado_coroutine())
        """)["native_coroutine_with_adapter"]

        # Use the adapter, but two degrees from the tornado coroutine.
        native_coroutine_with_adapter2 = exec_test(globals(), locals(), """
        async def native_coroutine_with_adapter2():
            return await to_asyncio_future(native_coroutine_without_adapter())
        """)["native_coroutine_with_adapter2"]

        # Tornado supports native coroutines both with and without adapters
        self.assertEqual(
            self.io_loop.run_sync(native_coroutine_without_adapter),
            42)
        self.assertEqual(
            self.io_loop.run_sync(native_coroutine_with_adapter),
            42)
        self.assertEqual(
            self.io_loop.run_sync(native_coroutine_with_adapter2),
            42)

        # Asyncio only supports coroutines that yield asyncio-compatible
        # Futures.
        with self.assertRaises(RuntimeError):
            asyncio.get_event_loop().run_until_complete(
                native_coroutine_without_adapter())
        self.assertEqual(
            asyncio.get_event_loop().run_until_complete(
                native_coroutine_with_adapter()),
            42)
        self.assertEqual(
            asyncio.get_event_loop().run_until_complete(
                native_coroutine_with_adapter2()),
            42)
