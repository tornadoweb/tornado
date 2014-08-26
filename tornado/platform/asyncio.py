"""This module integrates Tornado with the ``asyncio`` module introduced
in Python 3.4 (and available `as a separate download
<https://pypi.python.org/pypi/asyncio>`_ for Python 3.3).  This makes
it possible to combine the two libraries on the same event loop.

Most applications should use `AsyncIOMainLoop` to run Tornado on the
default ``asyncio`` event loop.  Applications that need to run event
loops on multiple threads may use `AsyncIOLoop` to create multiple
loops.

This is a work in progress and interfaces are subject to change.
"""

#To test:
#python3.4 -m tornado.test.runtests --ioloop=tornado.platform.asyncio.AsyncIOLoop
#python3.4 -m tornado.test.runtests --ioloop=tornado.platform.asyncio.AsyncIOMainLoop
#(the tests log a few warnings with AsyncIOMainLoop because they leave some
#unfinished callbacks on the event loop that fail when it resumes)

from __future__ import absolute_import, division, print_function, with_statement
import datetime
import functools

from tornado.ioloop import IOLoop
from tornado import stack_context, concurrent
from tornado.util import timedelta_to_seconds

try:
    # Import the real asyncio module for py33+ first.  Older versions of the
    # trollius backport also use this name.
    import asyncio
except ImportError as e:
    # Asyncio itself isn't available; see if trollius is (backport to py26+).
    try:
        import trollius as asyncio
    except ImportError:
        # Re-raise the original asyncio error, not the trollius one.
        raise e

class BaseAsyncIOLoop(IOLoop):
    """Serves as a base for `.AsyncIOMainLoop` and `.AsyncIOLoop`."""
    def initialize(self, asyncio_loop, close_loop=False):
        self.asyncio_loop = asyncio_loop
        self.close_loop = close_loop
        self.asyncio_loop.call_soon(self.make_current)
        # Maps fd to (fileobj, handler function) pair (as in IOLoop.add_handler)
        self.handlers = {}
        # Set of fds listening for reads/writes
        self.readers = set()
        self.writers = set()
        self.closing = False

    def close(self, all_fds=False):
        self.closing = True
        for fd in list(self.handlers):
            fileobj, handler_func = self.handlers[fd]
            self.remove_handler(fd)
            if all_fds:
                self.close_fd(fileobj)
        if self.close_loop:
            self.asyncio_loop.close()

    def add_handler(self, fd, handler, events):
        fd, fileobj = self.split_fd(fd)
        if fd in self.handlers:
            raise ValueError("fd %s added twice" % fd)
        self.handlers[fd] = (fileobj, stack_context.wrap(handler))
        if events & IOLoop.READ:
            self.asyncio_loop.add_reader(
                fd, self._handle_events, fd, IOLoop.READ)
            self.readers.add(fd)
        if events & IOLoop.WRITE:
            self.asyncio_loop.add_writer(
                fd, self._handle_events, fd, IOLoop.WRITE)
            self.writers.add(fd)

    def update_handler(self, fd, events):
        fd, fileobj = self.split_fd(fd)
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
        fd, fileobj = self.split_fd(fd)
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
        fileobj, handler_func = self.handlers[fd]
        handler_func(fileobj, events)

    def start(self):
        self._setup_logging()
        self.asyncio_loop.run_forever()

    def stop(self):
        self.asyncio_loop.stop()

    def call_at(self, when, callback, *args, **kwargs):
        # asyncio.call_at supports *args but not **kwargs, so bind them here.
        # We do not synchronize self.time and asyncio_loop.time, so
        # convert from absolute to relative.
        return self.asyncio_loop.call_later(
            max(0, when - self.time()), self._run_callback,
            functools.partial(stack_context.wrap(callback), *args, **kwargs))

    def remove_timeout(self, timeout):
        timeout.cancel()

    def add_callback(self, callback, *args, **kwargs):
        if self.closing:
            raise RuntimeError("IOLoop is closing")
        self.asyncio_loop.call_soon_threadsafe(
            self._run_callback,
            functools.partial(stack_context.wrap(callback), *args, **kwargs))

    add_callback_from_signal = add_callback

    def get_asyncio_loop(self):
        """Returns the ``asyncio`` event loop used for this `.BaseAsyncIOLoop` object."""
        return self.asyncio_loop


class AsyncIOMainLoop(BaseAsyncIOLoop):
    """``AsyncIOMainLoop`` creates an `.IOLoop` that corresponds to the
    current ``asyncio`` event loop (i.e. the one returned by
    ``asyncio.get_event_loop()``).

    Recommended usage::

        from tornado.platform.asyncio import AsyncIOMainLoop
        import asyncio
        AsyncIOMainLoop().install()
        asyncio.get_event_loop().run_forever()
    """
    def initialize(self):
        super(AsyncIOMainLoop, self).initialize(asyncio.get_event_loop(),
                                                close_loop=False)


class AsyncIOLoop(BaseAsyncIOLoop):
    """``AsyncIOLoop`` is an `.IOLoop` that runs on an ``asyncio`` event loop.

    This class follows the usual Tornado semantics for creating new
    ``IOLoops``; these loops are not necessarily related to the
    ``asyncio`` default event loop.  Recommended usage::

        from tornado.ioloop import IOLoop
        IOLoop.configure('tornado.platform.asyncio.AsyncIOLoop')
        IOLoop.instance().start()
    """
    def initialize(self):
        super(AsyncIOLoop, self).initialize(asyncio.new_event_loop(),
                                            close_loop=True)

class AsyncIOFuture(asyncio.Future, concurrent.Future):
    """A Tornado-compatible ``asyncio.Future``.

    Tornado can be instructed to use this class internally in place of the standard
    `tornado.concurrent.Future`, making it possible to use ``Futures`` returned by
    Tornado in coroutines running on an ``asyncio.Task`` without having to call
    `wrap_tornado_future`. Recommended usage::

        from tornado.concurrent import Future
        from tornado.platform.asyncio import AsyncIOMainLoop
        import asyncio
        AsyncIOMainLoop().install()
        Future.configure('tornado.platform.asyncio.AsyncIOFuture')
        asyncio.get_event_loop().run_forever()
    """

    def __init__(self, loop=None):
        asyncio.Future.__init__(self, loop=loop)

    def exc_info(self):
        try:
            exc = self.exception()
            return type(exc), exc, exc.__traceback__
        except (AttributeError, asyncio.InvalidStateError):
            return None

    def set_exc_info(self, exc_info):
        self.set_exception(exc_info[1])

    def add_done_callback(self, fn):
        asyncio.Future.add_done_callback(self, stack_context.wrap(fn))


def wrap_tornado_future(future, loop=None):
    """Wraps a `.tornado.concurrent.Future` in an ``asyncio.Future``.

    If ``loop`` is not supplied, an event loop will be retrieved
    using ``asyncio.get_event_loop()`` for use with the returned Future.
    """
    new_future = asyncio.Future(loop=(loop or asyncio.get_event_loop()))
    concurrent.chain_future(future, new_future)

    # attempt to intercept cancellation, similar to what asyncio.futures.wrap_future does.
    # probably won't work as expected; best to avoid trying to cancel futures.
    def _check_cancelled(_):
        if new_future.cancelled():
            future.set_exception(asyncio.CancelledError())

    new_future.add_done_callback(_check_cancelled)
    return new_future
