"""Bridges between the `asyncio` module and Tornado IOLoop.

This is a work in progress and interfaces are subject to change.

To test:
python3.4 -m tornado.test.runtests --ioloop=tornado.platform.asyncio.AsyncIOLoop
python3.4 -m tornado.test.runtests --ioloop=tornado.platform.asyncio.AsyncIOMainLoop
(the tests log a few warnings with AsyncIOMainLoop because they leave some
unfinished callbacks on the event loop that fail when it resumes)
"""

from __future__ import absolute_import, division, print_function, with_statement
import asyncio
import datetime
import functools
import os

from tornado.ioloop import IOLoop
from tornado import stack_context


class BaseAsyncIOLoop(IOLoop):
    def initialize(self, asyncio_loop, close_loop=False):
        self.asyncio_loop = asyncio_loop
        self.close_loop = close_loop
        self.asyncio_loop.call_soon(self.make_current)
        # Maps fd to handler function (as in IOLoop.add_handler)
        self.handlers = {}
        # Set of fds listening for reads/writes
        self.readers = set()
        self.writers = set()
        self.closing = False

    def close(self, all_fds=False):
        self.closing = True
        for fd in list(self.handlers):
            self.remove_handler(fd)
            if all_fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if self.close_loop:
            self.asyncio_loop.close()

    def add_handler(self, fd, handler, events):
        if fd in self.handlers:
            raise ValueError("fd %d added twice" % fd)
        self.handlers[fd] = stack_context.wrap(handler)
        if events & IOLoop.READ:
            self.asyncio_loop.add_reader(
                fd, self._handle_events, fd, IOLoop.READ)
            self.readers.add(fd)
        if events & IOLoop.WRITE:
            self.asyncio_loop.add_writer(
                fd, self._handle_events, fd, IOLoop.WRITE)
            self.writers.add(fd)

    def update_handler(self, fd, events):
        if events & IOLoop.READ:
            if fd not in self.readers:
                self.asyncio_loop.add_reader(
                    fd, self._handle_events, fd, IOLoop.READ)
                self.readers.add(fd)
        else:
            if fd in self.readers:
                self.asyncio_loop.remove_reader(fd)
                self.readers.remove(fd)
        if events & IOLoop.WRITE:
            if fd not in self.writers:
                self.asyncio_loop.add_writer(
                    fd, self._handle_events, fd, IOLoop.WRITE)
                self.writers.add(fd)
        else:
            if fd in self.writers:
                self.asyncio_loop.remove_writer(fd)
                self.writers.remove(fd)

    def remove_handler(self, fd):
        if fd not in self.handlers:
            return
        if fd in self.readers:
            self.asyncio_loop.remove_reader(fd)
            self.readers.remove(fd)
        if fd in self.writers:
            self.asyncio_loop.remove_writer(fd)
            self.writers.remove(fd)
        del self.handlers[fd]

    def _handle_events(self, fd, events):
        self.handlers[fd](fd, events)

    def start(self):
        self._setup_logging()
        self.asyncio_loop.run_forever()

    def stop(self):
        self.asyncio_loop.stop()

    def _run_callback(self, callback, *args, **kwargs):
        try:
            callback(*args, **kwargs)
        except Exception:
            self.handle_callback_exception(callback)

    def add_timeout(self, deadline, callback):
        if isinstance(deadline, (int, float)):
            delay = max(deadline - self.time(), 0)
        elif isinstance(deadline, datetime.timedelta):
            delay = deadline.total_seconds()
        else:
            raise TypeError("Unsupported deadline %r", deadline)
        return self.asyncio_loop.call_later(delay, self._run_callback,
                                            stack_context.wrap(callback))

    def remove_timeout(self, timeout):
        timeout.cancel()

    def add_callback(self, callback, *args, **kwargs):
        if self.closing:
            raise RuntimeError("IOLoop is closing")
        if kwargs:
            self.asyncio_loop.call_soon_threadsafe(functools.partial(
                self._run_callback, stack_context.wrap(callback),
                *args, **kwargs))
        else:
            self.asyncio_loop.call_soon_threadsafe(
                self._run_callback, stack_context.wrap(callback), *args)

    add_callback_from_signal = add_callback


class AsyncIOMainLoop(BaseAsyncIOLoop):
    def initialize(self):
        super(AsyncIOMainLoop, self).initialize(asyncio.get_event_loop(),
                                                close_loop=False)


class AsyncIOLoop(BaseAsyncIOLoop):
    def initialize(self):
        super(AsyncIOLoop, self).initialize(asyncio.new_event_loop(),
                                            close_loop=True)
