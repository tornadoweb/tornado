# Copyright 2015 The Tornado Authors
#
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

__all__ = ['Condition', 'Event', 'Semaphore']

import collections

from tornado import gen, ioloop
from tornado.concurrent import Future


class Condition(object):
    """A condition allows one or more coroutines to wait until notified.

    Like a standard `threading.Condition`, but does not need an underlying lock
    that is acquired and released.
    """

    def __init__(self):
        self.io_loop = ioloop.IOLoop.current()
        self._waiters = collections.deque()  # Futures.
        self._timeouts = 0

    def __str__(self):
        result = '<%s' % (self.__class__.__name__, )
        if self._waiters:
            result += ' waiters[%s]' % len(self._waiters)
        return result + '>'

    def wait(self, timeout=None):
        """Wait for `.notify`.

        Returns a `.Future` that resolves ``True`` if the condition is notified,
        or ``False`` after a timeout.
        """
        waiter = Future()
        self._waiters.append(waiter)
        if timeout:
            def on_timeout():
                waiter.set_result(False)
                self._garbage_collect()
            self.io_loop.add_timeout(timeout, on_timeout)
        return waiter

    def notify(self, n=1):
        """Wake ``n`` waiters."""
        waiters = []  # Waiters we plan to run right now.
        while n and self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():  # Might have timed out.
                n -= 1
                waiters.append(waiter)

        for waiter in waiters:
            waiter.set_result(True)

    def notify_all(self):
        """Wake all waiters."""
        self.notify(len(self._waiters))

    def _garbage_collect(self):
        # Occasionally clear timed-out waiters, if many coroutines wait with a
        # timeout but notify is called rarely.
        self._timeouts += 1
        if self._timeouts > 100:
            self._timeouts = 0
            self._waiters = collections.deque(
                w for w in self._waiters if not w.done())


class Event(object):
    """An event blocks coroutines until its internal flag is set to True.

    Similar to `threading.Event`.
    """
    def __init__(self):
        self._future = Future()

    def __str__(self):
        return '<%s %s>' % (
            self.__class__.__name__, 'set' if self.is_set() else 'clear')

    def is_set(self):
        """Return ``True`` if the internal flag is true."""
        return self._future.done()

    def set(self):
        """Set the internal flag to ``True``. All waiters are awakened.

        Calling `.wait` once the flag is set will not block.
        """
        if not self._future.done():
            self._future.set_result(None)

    def clear(self):
        """Reset the internal flag to ``False``.
        
        Calls to `.wait` will block until `.set` is called.
        """
        if self._future.done():
            self._future = Future()

    def wait(self, timeout=None):
        """Block until the internal flag is true.

        Returns a Future, which raises :exc:`~tornado.gen.TimeoutError` after a
        timeout.
        """
        if timeout is None:
            return self._future
        else:
            return gen.with_timeout(timeout, self._future)


class _ReleasingContextManager(object):
    """Releases a Lock or Semaphore at the end of a "with" statement.

        with (yield semaphore.acquire()):
            pass

        # Now semaphore.release() has been called.
    """
    def __init__(self, obj):
        self._obj = obj

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._obj.release()


class Semaphore(object):
    """A lock that can be acquired a fixed number of times before blocking.

    A Semaphore manages a counter representing the number of `.release` calls
    minus the number of `.acquire` calls, plus an initial value. The `.acquire`
    method blocks if necessary until it can return without making the counter
    negative.

    `.acquire` supports the context manager protocol:

    >>> from tornado import gen, locks
    >>> semaphore = locks.Semaphore()
    >>> @gen.coroutine
    ... def f():
    ...    with (yield semaphore.acquire()):
    ...        assert semaphore.locked()
    ...
    ...    assert not semaphore.locked()

    .. note:: Unlike the standard `threading.Semaphore`, a Tornado `.Semaphore`
      can tell you the current value of its `.counter`, because code in a
      single-threaded Tornado application can check this value and act upon
      it without fear of interruption from another thread.
    """
    def __init__(self, value=1):
        if value < 0:
            raise ValueError('semaphore initial value must be >= 0')

        self.io_loop = ioloop.IOLoop.current()
        self._value = value
        self._waiters = collections.deque()

    def __repr__(self):
        res = super(Semaphore, self).__repr__()
        extra = 'locked' if self.locked() else 'unlocked,value:{0}'.format(
            self._value)
        if self._waiters:
            extra = '{0},waiters:{1}'.format(extra, len(self._waiters))
        return '<{0} [{1}]>'.format(res[1:-1], extra)

    @property
    def counter(self):
        """An integer, the current semaphore value."""
        return self._value

    def locked(self):
        """True if the semaphore cannot be acquired immediately."""
        return self._value == 0

    def release(self):
        """Increment `.counter` and wake one waiter."""
        self._value += 1
        for waiter in self._waiters:
            if not waiter.done():
                self._value -= 1

                # If the waiter is a coroutine paused at
                #
                #     with (yield semaphore.acquire()):
                #
                # then the context manager's __exit__ calls release() at the end
                # of the "with" block.
                waiter.set_result(_ReleasingContextManager(self))
                break

    def acquire(self, timeout=None):
        """Decrement `.counter`. Returns a Future.

        Block if the counter is zero and wait for a `.release`. The Future
        raises `.TimeoutError` after the deadline.
        """
        if self._value > 0:
            self._value -= 1
            future = Future()
            future.set_result(_ReleasingContextManager(self))
        else:
            waiter = Future()
            self._waiters.append(waiter)
            if timeout:
                future = gen.with_timeout(timeout, waiter, self.io_loop,
                                          quiet_exceptions=gen.TimeoutError)

                # Set waiter's exception after the deadline.
                gen.chain_future(future, waiter)
            else:
                future = waiter
        return future

    def __enter__(self):
        raise RuntimeError(
            "Use Semaphore like 'with (yield semaphore.acquire())', not like"
            " 'with semaphore'")

    __exit__ = __enter__
