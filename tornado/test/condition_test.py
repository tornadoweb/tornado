from __future__ import absolute_import, division, print_function, with_statement

from datetime import timedelta
import time
import unittest

from tornado import gen, locks
from tornado.testing import gen_test, AsyncTestCase


class TestCondition(AsyncTestCase):
    def setUp(self):
        super(TestCondition, self).setUp()
        self.history = []

    def record_done(self, future, key):
        def callback(_):
            exc = future.exception()
            if exc:
                self.history.append(exc.__class__.__name__)
            else:
                self.history.append(key)
        future.add_done_callback(callback)

    def test_str(self):
        c = locks.Condition()
        self.assertIn('Condition', str(c))
        self.assertNotIn('waiters', str(c))
        c.wait()
        self.assertIn('waiters', str(c))

    @gen_test
    def test_notify(self):
        c = locks.Condition()
        self.io_loop.call_later(0.01, c.notify)
        yield c.wait()

    def test_notify_1(self):
        c = locks.Condition()
        self.record_done(c.wait(), 'wait1')
        self.record_done(c.wait(), 'wait2')
        c.notify(1)
        self.history.append('notify1')
        c.notify(1)
        self.history.append('notify2')
        self.assertEqual(['wait1', 'notify1', 'wait2', 'notify2'],
                         self.history)

    def test_notify_n(self):
        c = locks.Condition()
        for i in range(6):
            self.record_done(c.wait(), i)

        c.notify(3)

        # Callbacks execute in the order they were registered.
        self.assertEqual(list(range(3)), self.history)
        c.notify(1)
        self.assertEqual(list(range(4)), self.history)
        c.notify(2)
        self.assertEqual(list(range(6)), self.history)

    def test_notify_all(self):
        c = locks.Condition()
        for i in range(4):
            self.record_done(c.wait(), i)

        c.notify_all()
        self.history.append('notify_all')

        # Callbacks execute in the order they were registered.
        self.assertEqual(
            list(range(4)) + ['notify_all'],
            self.history)

    @gen_test
    def test_wait_timeout(self):
        c = locks.Condition()
        with self.assertRaises(gen.TimeoutError):
            yield c.wait(deadline=timedelta(seconds=0.01))

    @gen_test
    def test_wait_timeout_preempted(self):
        c = locks.Condition()

        # This fires before the wait times out.
        self.io_loop.call_later(0.01, c.notify)
        yield c.wait(deadline=timedelta(seconds=1))

    @gen_test
    def test_notify_n_with_timeout(self):
        # Register callbacks 0, 1, 2, and 3. Callback 1 has a timeout.
        # Wait for that timeout to expire, then do notify(2) and make
        # sure everyone runs. Verifies that a timed-out callback does
        # not count against the 'n' argument to notify().
        c = locks.Condition()
        self.record_done(c.wait(), 0)
        self.record_done(c.wait(deadline=timedelta(seconds=0.01)), 1)

        self.record_done(c.wait(), 2)
        self.record_done(c.wait(), 3)

        # Wait for callback 1 to time out.
        yield gen.sleep(0.2)
        self.assertEqual(['TimeoutError'], self.history)

        c.notify(2)
        yield gen.sleep(0.1)
        self.assertEqual(['TimeoutError', 0, 2], self.history)
        self.assertEqual(['TimeoutError', 0, 2], self.history)
        c.notify()
        self.assertEqual(['TimeoutError', 0, 2, 3], self.history)

    @gen_test
    def test_notify_all_with_timeout(self):
        c = locks.Condition()
        st = time.time()
        self.record_done(c.wait(), 0)
        self.record_done(c.wait(deadline=timedelta(seconds=.1)), 1)

        self.record_done(c.wait(), 2)

        # Wait for callback 1 to time out.
        yield gen.Task(self.io_loop.add_timeout, st + 0.2)
        self.assertEqual(['TimeoutError'], self.history)

        c.notify_all()
        self.assertEqual(['TimeoutError', 0, 2], self.history)

if __name__ == '__main__':
    unittest.main()
