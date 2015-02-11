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

__all__ = ['Condition']

import collections

from tornado import concurrent, gen, ioloop
from tornado.concurrent import Future


class Condition(object):
    """A condition allows one or more coroutines to wait until notified.

    Like a standard `threading.Condition`, but does not need an underlying lock
    that is acquired and released.
    """

    def __init__(self):
        self.io_loop = ioloop.IOLoop.current()
        self.waiters = collections.deque()  # Futures.

    def __str__(self):
        result = '<%s' % (self.__class__.__name__, )
        if self.waiters:
            result += ' waiters[%s]' % len(self.waiters)
        return result + '>'

    def wait(self, timeout=None):
        """Wait for `.notify`. Returns a `.Future`.

        Raises `.TimeoutError` if the condition is not notified before
        ``timeout``, which may be specified in any form allowed by
        `.IOLoop.add_timeout` (i.e. a `datetime.timedelta` or an absolute time
        relative to `.IOLoop.time`)
        """
        waiter = Future()
        self.waiters.append(waiter)
        if timeout:
            timed = gen.with_timeout(timeout, waiter, self.io_loop,
                                     quiet_exceptions=gen.TimeoutError)

            # Set waiter's exception after the timeout so notify(n) skips it.
            concurrent.chain_future(timed, waiter)
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
