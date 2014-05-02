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

# _Timeout is used for its timedelta_to_seconds method for py26 compatibility.
from tornado.ioloop import IOLoop, _Timeout
from tornado import stack_context, concurrent


class BaseAsyncIOLoop(IOLoop):
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

    def _run_callback(self, callback, *args, **kwargs):
        try:
            callback(*args, **kwargs)
        except Exception:
            self.handle_callback_exception(callback)

    def add_timeout(self, deadline, callback):
        if isinstance(deadline, (int, float)):
            delay = max(deadline - self.time(), 0)
        elif isinstance(deadline, datetime.timedelta):
            delay = _Timeout.timedelta_to_seconds(deadline)
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

    def get_asyncio_loop(self):
        """Returns the ``asyncio`` event loop used for this `.BaseAsyncIOLoop` object."""
        return self.asyncio_loop


class AsyncIOMainLoop(BaseAsyncIOLoop):
    def initialize(self):
        super(AsyncIOMainLoop, self).initialize(asyncio.get_event_loop(),
                                                close_loop=False)


class AsyncIOLoop(BaseAsyncIOLoop):
    def initialize(self):
        super(AsyncIOLoop, self).initialize(asyncio.new_event_loop(),
                                            close_loop=True)


def _copy_future_state(finished_future, other_future):
    assert finished_future.done()
    if other_future.cancelled():
        return # disregard callback after setting exception in _check_cancelled

    try:
        other_future.set_result(finished_future.result())
    except Exception as e:
        other_future.set_exception(e)

def wrap_asyncio_future(future):
    """Wraps an ``asyncio.Future`` in a `.tornado.concurrent.Future`."""
    new_future = concurrent.Future()
    future.add_done_callback(lambda _: _copy_future_state(future, new_future))
    return new_future

def wrap_tornado_future(future, *, loop=None):
    """Wraps a `.tornado.concurrent.Future` in an ``asyncio.Future``.

    If ``loop`` is not supplied, an event loop will be retrieved
    using ``asyncio.get_event_loop()`` for use with the returned Future.
    """
    new_future = asyncio.Future(loop=(loop or asyncio.get_event_loop()))
    future.add_done_callback(lambda _: _copy_future_state(future, new_future))

    # attempt to intercept cancellation, similar to what asyncio.futures.wrap_future does.
    # probably won't work as expected; best to avoid trying to cancel futures.
    def _check_cancelled(_):
        if new_future.cancelled():
            future.set_exception(asyncio.CancelledError())

    new_future.add_done_callback(_check_cancelled)
    return new_future

def task(func):
    """Decorator for wrapping an ``asyncio`` coroutine object in a `.tornado.concurrent.Future`.

    When a function decorated by ``@platform.asyncio.task`` is called, an ``asyncio.Task``
    object running on the event loop returned by ``asyncio.get_event_loop()`` will be
    constructed and subsequently wrapped in a `.tornado.concurrent.Future` and returned.

    A function decorated with ``@platform.asyncio.task`` does not need to be explicitly
    decorated with ``@asyncio.coroutine``.

    In ``asyncio`` coroutines, ``yield from`` can be used with Tornado's `.Future`, in which
    case the `.Future` will be automatically wrapped in an ``asyncio.Future``.

    Example usage::

        class AsyncIORequestHandler(RequestHandler):
            @platform.asyncio.task
            def get(self):
                response = yield from AsyncHTTPClient().fetch("http://google.com")
                print("Got response:", response)

                proc = yield from asyncio.create_subprocess_exec(
                    'ls', '-l', stdout=asyncio.subprocess.PIPE)
                stdout, _ = yield from proc.communicate()
                self.write(stdout.replace(b'\\n', b'<br>'))
    """
    func = asyncio.coroutine(func)
    def wrapper(*args, **kwargs):
        return wrap_asyncio_future(asyncio.Task(func(*args, **kwargs)))
    return wrapper
