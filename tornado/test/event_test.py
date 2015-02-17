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
from tornado.gen import TimeoutError
from tornado.testing import gen_test, AsyncTestCase


class TestEvent(AsyncTestCase):
    def test_str(self):
        event = locks.Event()
        self.assertTrue('clear' in str(event))
        self.assertFalse('set' in str(event))
        event.set()
        self.assertFalse('clear' in str(event))
        self.assertTrue('set' in str(event))

    def test_event(self):
        e = locks.Event()
        future_0 = e.wait()
        e.set()
        future_1 = e.wait()
        e.clear()
        future_2 = e.wait()

        self.assertTrue(future_0.done())
        self.assertTrue(future_1.done())
        self.assertFalse(future_2.done())

    @gen_test
    def test_event_timeout(self):
        e = locks.Event()
        with self.assertRaises(TimeoutError):
            yield e.wait(timedelta(seconds=0.01))

        # After a timed-out waiter, normal operation works.
        self.io_loop.add_timeout(timedelta(seconds=0.01), e.set)
        yield e.wait(timedelta(seconds=1))

    def test_event_set_multiple(self):
        e = locks.Event()
        e.set()
        e.set()
        self.assertTrue(e.is_set())


if __name__ == '__main__':
    unittest.main()
