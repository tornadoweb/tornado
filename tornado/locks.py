__all__ = ['Condition']

import collections

from tornado import gen, ioloop
from tornado.concurrent import Future


class Condition(object):
    """A condition allows one or more coroutines to wait until notified.

    Like a standard Condition_, but does not need an underlying lock that
    is acquired and released.

    .. _Condition: http://docs.python.org/library/threading.html#threading.Condition
    """

    def __init__(self, io_loop=None):
        self.io_loop = io_loop or ioloop.IOLoop.current()
        self.waiters = collections.deque()  # Futures.

    def __str__(self):
        result = '<%s' % (self.__class__.__name__, )
        if self.waiters:
            result += ' waiters[%s]' % len(self.waiters)
        return result + '>'

    def wait(self, deadline=None):
        """Wait for `.notify`. Returns a `.Future`.

        Raises `.TimeoutError` if the condition is not notified before
        ``timeout``, which may be specified in any form allowed by
        `.IOLoop.add_timeout` (i.e. a `datetime.timedelta` or an absolute time
        relative to `.IOLoop.time`)
        """
        waiter = Future()
        self.waiters.append(waiter)
        if deadline:
            timed = gen.with_timeout(deadline, waiter, self.io_loop,
                                     quiet_exceptions=gen.TimeoutError)

            # Set waiter's exception after the deadline so notify(n) skips it.
            gen.chain_future(timed, waiter)
            return timed
        else:
            return waiter

    def notify(self, n=1):
        """Wake ``n`` waiters."""
        waiters = []  # Waiters we plan to run right now.
        while n and self.waiters:
            waiter = self.waiters.popleft()
            if not waiter.done():  # Might have timed out.
                n -= 1
                waiters.append(waiter)

        for waiter in waiters:
            waiter.set_result(None)

    def notify_all(self):
        """Wake all waiters."""
        self.notify(len(self.waiters))
