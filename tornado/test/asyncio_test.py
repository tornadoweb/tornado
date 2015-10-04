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

from __future__ import absolute_import, division, print_function, with_statement

from tornado import gen
from tornado.testing import AsyncTestCase, gen_test
from tornado.test.util import unittest, skipBefore33, exec_test

try:
    from tornado.platform.asyncio import asyncio, AsyncIOLoop
except ImportError:
    asyncio = None

skipIfNoSingleDispatch = unittest.skipIf(
    gen.singledispatch is None, "singledispatch module not present")


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

    @skipIfNoSingleDispatch
    @gen_test
    def test_asyncio_future(self):
        # Test that we can yield an asyncio future from a tornado coroutine.
        # Without 'yield from', we must wrap coroutines in asyncio.async.
        x = yield asyncio.async(
            asyncio.get_event_loop().run_in_executor(None, lambda: 42))
        self.assertEqual(x, 42)

    @skipBefore33
    @skipIfNoSingleDispatch
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
