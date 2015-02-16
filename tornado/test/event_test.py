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

from datetime import timedelta
import unittest

from tornado import gen, locks
from tornado.testing import gen_test, AsyncTestCase


class TestEvent(AsyncTestCase):
    def test_str(self):
        event = locks.Event()
        self.assertTrue('clear' in str(event))
        self.assertFalse('set' in str(event))
        event.set()
        self.assertFalse('clear' in str(event))
        self.assertTrue('set' in str(event))

    @gen.coroutine
    def _test_event(self, n):
        e = locks.Event()
        futures = [e.wait() for _ in range(n)]
        e.set()
        e.clear()
        results = yield futures
        self.assertTrue(all(results))

    @gen_test
    def test_event_1(self):
        yield self._test_event(1)

    @gen_test
    def test_event_200(self):
        yield self._test_event(200)

    @gen_test
    def test_event_timeout(self):
        e = locks.Event()
        result = yield e.wait(deadline=timedelta(seconds=0.01))
        self.assertEqual(False, result)

        # After a timed-out waiter, normal operation works.
        self.io_loop.add_timeout(timedelta(seconds=0.01), e.set)
        result = yield e.wait(deadline=timedelta(seconds=1))
        self.assertTrue(result)

    @gen_test
    def test_event_nowait(self):
        e = locks.Event()
        e.set()
        self.assertEqual(True, e.is_set())
        self.assertTrue(e.wait().result())


if __name__ == '__main__':
    unittest.main()
