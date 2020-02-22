"""Bridges between the `asyncio` module and Tornado IOLoop.

.. versionadded:: 3.2

This module integrates Tornado with the ``asyncio`` module introduced
in Python 3.4. This makes it possible to combine the two libraries on
the same event loop.

.. deprecated:: 5.0

   While the code in this module is still used, it is now enabled
   automatically when `asyncio` is available, so applications should
   no longer need to refer to this module directly.

.. note::

   Tornado requires the `~asyncio.AbstractEventLoop.add_reader` family of
   methods, so it is not compatible with the `~asyncio.ProactorEventLoop` on
   Windows. Use the `~asyncio.SelectorEventLoop` instead.
"""

import asyncio
import atexit
import concurrent.futures
import functools
import itertools
import sys
import threading
import typing
from tornado.gen import convert_yielded
from tornado.ioloop import IOLoop, _Selectable

from typing import Any, TypeVar, Awaitable, Callable, Union, Optional

if typing.TYPE_CHECKING:
    from typing import Set, Dict, Tuple  # noqa: F401

_T = TypeVar("_T")


class _HasFileno(typing.Protocol):
    def fileno(self) -> int:
        pass


_FileDescriptorLike = Union[int, _HasFileno]


_seq_gen = itertools.count()

_atexit_run = False


def _atexit_callback() -> None:
    global _atexit_run
    _atexit_run = True


atexit.register(_atexit_callback)


class BaseAsyncIOLoop(IOLoop):
    def initialize(  # type: ignore
        self, asyncio_loop: asyncio.AbstractEventLoop, **kwargs: Any
    ) -> None:
        # asyncio_loop is always the real underlying IOLoop. This is used in
        # ioloop.py to maintain the asyncio-to-ioloop mappings.
        self.asyncio_loop = asyncio_loop
        # selector_loop is an event loop that implements the add_reader family of
        # methods. Usually the same as asyncio_loop but differs on platforms such
        # as windows where the default event loop does not implement these methods.
        self.selector_loop = asyncio_loop
        if hasattr(asyncio, "ProactorEventLoop") and isinstance(
            asyncio_loop, asyncio.ProactorEventLoop
        ):
            # Ignore this line for mypy because the abstract method checker
            # doesn't understand dynamic proxies.
            self.selector_loop = AddThreadSelectorEventLoop(asyncio_loop)  # type: ignore
        # Maps fd to (fileobj, handler function) pair (as in IOLoop.add_handler)
        self.handlers = {}  # type: Dict[int, Tuple[Union[int, _Selectable], Callable]]
        # Set of fds listening for reads/writes
        self.readers = set()  # type: Set[int]
        self.writers = set()  # type: Set[int]
        self.closing = False
        # If an asyncio loop was closed through an asyncio interface
        # instead of IOLoop.close(), we'd never hear about it and may
        # have left a dangling reference in our map. In case an
        # application (or, more likely, a test suite) creates and
        # destroys a lot of event loops in this way, check here to
        # ensure that we don't have a lot of dead loops building up in
        # the map.
        #
        # TODO(bdarnell): consider making self.asyncio_loop a weakref
        # for AsyncIOMainLoop and make _ioloop_for_asyncio a
        # WeakKeyDictionary.
        for loop in list(IOLoop._ioloop_for_asyncio):
            if loop.is_closed():
                del IOLoop._ioloop_for_asyncio[loop]
        IOLoop._ioloop_for_asyncio[asyncio_loop] = self

        self._thread_identity = 0

        super(BaseAsyncIOLoop, self).initialize(**kwargs)

        def assign_thread_identity() -> None:
            self._thread_identity = threading.get_ident()

        self.add_callback(assign_thread_identity)

    def close(self, all_fds: bool = False) -> None:
        self.closing = True
        for fd in list(self.handlers):
            fileobj, handler_func = self.handlers[fd]
            self.remove_handler(fd)
            if all_fds:
                self.close_fd(fileobj)
        # Remove the mapping before closing the asyncio loop. If this
        # happened in the other order, we could race against another
        # initialize() call which would see the closed asyncio loop,
        # assume it was closed from the asyncio side, and do this
        # cleanup for us, leading to a KeyError.
        del IOLoop._ioloop_for_asyncio[self.asyncio_loop]
        if self.selector_loop is not self.asyncio_loop:
            self.selector_loop.close()
        self.asyncio_loop.close()

    def add_handler(
        self, fd: Union[int, _Selectable], handler: Callable[..., None], events: int
    ) -> None:
        fd, fileobj = self.split_fd(fd)
        if fd in self.handlers:
            raise ValueError("fd %s added twice" % fd)
        self.handlers[fd] = (fileobj, handler)
        if events & IOLoop.READ:
            self.selector_loop.add_reader(fd, self._handle_events, fd, IOLoop.READ)
            self.readers.add(fd)
        if events & IOLoop.WRITE:
            self.selector_loop.add_writer(fd, self._handle_events, fd, IOLoop.WRITE)
            self.writers.add(fd)

    def update_handler(self, fd: Union[int, _Selectable], events: int) -> None:
        fd, fileobj = self.split_fd(fd)
        if events & IOLoop.READ:
            if fd not in self.readers:
                self.selector_loop.add_reader(fd, self._handle_events, fd, IOLoop.READ)
                self.readers.add(fd)
        else:
            if fd in self.readers:
                self.selector_loop.remove_reader(fd)
                self.readers.remove(fd)
        if events & IOLoop.WRITE:
            if fd not in self.writers:
                self.selector_loop.add_writer(fd, self._handle_events, fd, IOLoop.WRITE)
                self.writers.add(fd)
        else:
            if fd in self.writers:
                self.selector_loop.remove_writer(fd)
                self.writers.remove(fd)

    def remove_handler(self, fd: Union[int, _Selectable]) -> None:
        fd, fileobj = self.split_fd(fd)
        if fd not in self.handlers:
            return
        if fd in self.readers:
            self.selector_loop.remove_reader(fd)
            self.readers.remove(fd)
        if fd in self.writers:
            self.selector_loop.remove_writer(fd)
            self.writers.remove(fd)
        del self.handlers[fd]

    def _handle_events(self, fd: int, events: int) -> None:
        fileobj, handler_func = self.handlers[fd]
        handler_func(fileobj, events)

    def start(self) -> None:
        try:
            old_loop = asyncio.get_event_loop()
        except (RuntimeError, AssertionError):
            old_loop = None  # type: ignore
        try:
            self._setup_logging()
            asyncio.set_event_loop(self.asyncio_loop)
            self.asyncio_loop.run_forever()
        finally:
            asyncio.set_event_loop(old_loop)

    def stop(self) -> None:
        self.asyncio_loop.stop()

    def call_at(
        self, when: float, callback: Callable[..., None], *args: Any, **kwargs: Any
    ) -> object:
        # asyncio.call_at supports *args but not **kwargs, so bind them here.
        # We do not synchronize self.time and asyncio_loop.time, so
        # convert from absolute to relative.
        return self.asyncio_loop.call_later(
            max(0, when - self.time()),
            self._run_callback,
            functools.partial(callback, *args, **kwargs),
        )

    def remove_timeout(self, timeout: object) -> None:
        timeout.cancel()  # type: ignore

    def add_callback(self, callback: Callable, *args: Any, **kwargs: Any) -> None:
        if threading.get_ident() == self._thread_identity:
            call_soon = self.asyncio_loop.call_soon
        else:
            call_soon = self.asyncio_loop.call_soon_threadsafe
        try:
            call_soon(self._run_callback, functools.partial(callback, *args, **kwargs))
        except RuntimeError:
            # "Event loop is closed". Swallow the exception for
            # consistency with PollIOLoop (and logical consistency
            # with the fact that we can't guarantee that an
            # add_callback that completes without error will
            # eventually execute).
            pass
        except AttributeError:
            # ProactorEventLoop may raise this instead of RuntimeError
            # if call_soon_threadsafe races with a call to close().
            # Swallow it too for consistency.
            pass

    def add_callback_from_signal(
        self, callback: Callable, *args: Any, **kwargs: Any
    ) -> None:
        try:
            self.asyncio_loop.call_soon_threadsafe(
                self._run_callback, functools.partial(callback, *args, **kwargs)
            )
        except RuntimeError:
            pass

    def run_in_executor(
        self,
        executor: Optional[concurrent.futures.Executor],
        func: Callable[..., _T],
        *args: Any,
    ) -> Awaitable[_T]:
        return self.asyncio_loop.run_in_executor(executor, func, *args)

    def set_default_executor(self, executor: concurrent.futures.Executor) -> None:
        return self.asyncio_loop.set_default_executor(executor)


class AsyncIOMainLoop(BaseAsyncIOLoop):
    """``AsyncIOMainLoop`` creates an `.IOLoop` that corresponds to the
    current ``asyncio`` event loop (i.e. the one returned by
    ``asyncio.get_event_loop()``).

    .. deprecated:: 5.0

       Now used automatically when appropriate; it is no longer necessary
       to refer to this class directly.

    .. versionchanged:: 5.0

       Closing an `AsyncIOMainLoop` now closes the underlying asyncio loop.
    """

    def initialize(self, **kwargs: Any) -> None:  # type: ignore
        super(AsyncIOMainLoop, self).initialize(asyncio.get_event_loop(), **kwargs)

    def make_current(self) -> None:
        # AsyncIOMainLoop already refers to the current asyncio loop so
        # nothing to do here.
        pass


class AsyncIOLoop(BaseAsyncIOLoop):
    """``AsyncIOLoop`` is an `.IOLoop` that runs on an ``asyncio`` event loop.
    This class follows the usual Tornado semantics for creating new
    ``IOLoops``; these loops are not necessarily related to the
    ``asyncio`` default event loop.

    Each ``AsyncIOLoop`` creates a new ``asyncio.EventLoop``; this object
    can be accessed with the ``asyncio_loop`` attribute.

    .. versionchanged:: 5.0

       When an ``AsyncIOLoop`` becomes the current `.IOLoop`, it also sets
       the current `asyncio` event loop.

    .. deprecated:: 5.0

       Now used automatically when appropriate; it is no longer necessary
       to refer to this class directly.
    """

    def initialize(self, **kwargs: Any) -> None:  # type: ignore
        self.is_current = False
        loop = asyncio.new_event_loop()
        try:
            super(AsyncIOLoop, self).initialize(loop, **kwargs)
        except Exception:
            # If initialize() does not succeed (taking ownership of the loop),
            # we have to close it.
            loop.close()
            raise

    def close(self, all_fds: bool = False) -> None:
        if self.is_current:
            self.clear_current()
        super(AsyncIOLoop, self).close(all_fds=all_fds)

    def make_current(self) -> None:
        if not self.is_current:
            try:
                self.old_asyncio = asyncio.get_event_loop()
            except (RuntimeError, AssertionError):
                self.old_asyncio = None  # type: ignore
            self.is_current = True
        asyncio.set_event_loop(self.asyncio_loop)

    def _clear_current_hook(self) -> None:
        if self.is_current:
            asyncio.set_event_loop(self.old_asyncio)
            self.is_current = False


def to_tornado_future(asyncio_future: asyncio.Future) -> asyncio.Future:
    """Convert an `asyncio.Future` to a `tornado.concurrent.Future`.

    .. versionadded:: 4.1

    .. deprecated:: 5.0
       Tornado ``Futures`` have been merged with `asyncio.Future`,
       so this method is now a no-op.
    """
    return asyncio_future


def to_asyncio_future(tornado_future: asyncio.Future) -> asyncio.Future:
    """Convert a Tornado yieldable object to an `asyncio.Future`.

    .. versionadded:: 4.1

    .. versionchanged:: 4.3
       Now accepts any yieldable object, not just
       `tornado.concurrent.Future`.

    .. deprecated:: 5.0
       Tornado ``Futures`` have been merged with `asyncio.Future`,
       so this method is now equivalent to `tornado.gen.convert_yielded`.
    """
    return convert_yielded(tornado_future)


if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    # "Any thread" and "selector" should be orthogonal, but there's not a clean
    # interface for composing policies so pick the right base.
    _BasePolicy = asyncio.WindowsSelectorEventLoopPolicy  # type: ignore
else:
    _BasePolicy = asyncio.DefaultEventLoopPolicy


class AnyThreadEventLoopPolicy(_BasePolicy):  # type: ignore
    """Event loop policy that allows loop creation on any thread.

    The default `asyncio` event loop policy only automatically creates
    event loops in the main threads. Other threads must create event
    loops explicitly or `asyncio.get_event_loop` (and therefore
    `.IOLoop.current`) will fail. Installing this policy allows event
    loops to be created automatically on any thread, matching the
    behavior of Tornado versions prior to 5.0 (or 5.0 on Python 2).

    Usage::

        asyncio.set_event_loop_policy(AnyThreadEventLoopPolicy())

    .. versionadded:: 5.0

    """

    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        try:
            return super().get_event_loop()
        except (RuntimeError, AssertionError):
            # This was an AssertionError in Python 3.4.2 (which ships with Debian Jessie)
            # and changed to a RuntimeError in 3.4.3.
            # "There is no current event loop in thread %r"
            loop = self.new_event_loop()
            self.set_event_loop(loop)
            return loop


class AddThreadSelectorEventLoop(asyncio.AbstractEventLoop):
    """Wrap an event loop to add implementations of the ``add_reader`` method family.

    Instances of this class start a second thread to run a selector-based event loop.
    This thread is completely hidden from the user; all callbacks are run on the
    wrapped event loop's thread.

    This class is used automatically by Tornado; applications should not need
    to refer to it directly.

    It is safe to wrap any event loop with this class, although it only makes sense
    for event loops that do not implement the ``add_reader`` family of methods
    themselves (i.e. ``WindowsProactorEventLoop``)

    Closing the ``AddThreadSelectorEventLoop`` does not close the wrapped event loop.
    """

    # This class is a __getattribute__-based proxy. All attributes other than those
    # in this set are proxied through to the underlying loop.
    MY_ATTRIBUTES = {
        "add_reader",
        "add_writer",
        "remove_reader",
        "remove_writer",
        "close",
        "_real_loop",
        "_selector_loop",
        "_selector_thread",
        "_run_on_selector",
        "_handle_event_from_selector",
        "_reader_seq",
        "_writer_seq",
    }

    def __init__(self, real_loop: asyncio.AbstractEventLoop) -> None:
        self._real_loop = real_loop

        # Sequence numbers allow us to detect races between the selector thread
        # and the main thread, such as when a handler for a file descriptor has
        # been removed and re-added. These maps go from file descriptor to a
        # sequence number.
        self._reader_seq = {}  # type: Dict[_FileDescriptorLike, int]
        self._writer_seq = {}  # type: Dict[_FileDescriptorLike, int]

        fut = (
            concurrent.futures.Future()
        )  # type: concurrent.futures.Future[asyncio.AbstractEventLoop]

        def f() -> None:
            loop = asyncio.SelectorEventLoop()
            fut.set_result(loop)
            loop.run_forever()
            loop.close()

        self._selector_thread = threading.Thread(target=f)
        # Must be a daemon in case this event loop is not explicitly closed
        # (often the case for the main loop).
        self._selector_thread.daemon = True
        self._selector_thread.start()
        self._selector_loop = fut.result()

    def close(self) -> None:
        self._selector_loop.call_soon_threadsafe(self._selector_loop.stop)
        if not _atexit_run:
            # Shutdown is tricky: Our thread must be set as a daemon so that it
            # doesn't prevent shutdown in the common case of an unclosed main
            # loop. But daemon threads are halted relatively early in the
            # interpreter shutdown process; once this happens attempts to join
            # them will block forever.
            #
            # I can't find formal documentation of this, but as of cpython 3.8
            # the shutdown order is
            # 1. atexit functions
            # 2. daemon threads halt
            # 3. global destructors run
            #
            # If we're running after atexit functions, we're probably in a
            # global destructor. But in any case, we know that the process is
            # about to exit and it's no longer necessary to join our daemon
            # thread. (Is it ever necessary to join it? Probably not but it
            # feels dirty not to)
            self._selector_thread.join()
        self._real_loop.close()

    def __getattribute__(self, name: str) -> Any:
        if name in AddThreadSelectorEventLoop.MY_ATTRIBUTES:
            return super().__getattribute__(name)
        return getattr(self._real_loop, name)

    def _run_on_selector(self, method: Callable[..., _T], *args: Any) -> _T:
        """Synchronously run the given method on the selector thread.
        """
        fut = concurrent.futures.Future()  # type: concurrent.futures.Future[_T]

        def wrapper() -> None:
            try:
                result = method(*args)
            except Exception as e:
                fut.set_exception(e)
            else:
                fut.set_result(result)

        self._selector_loop.call_soon_threadsafe(wrapper)
        return fut.result()

    def add_reader(
        self, fd: _FileDescriptorLike, callback: Callable[..., None], *args: Any
    ) -> None:
        seq = next(_seq_gen)
        self._reader_seq[fd] = seq

        def wrapper() -> None:
            if self._reader_seq.get(fd, None) != seq:
                return
            callback(*args)

        return self._run_on_selector(
            self._selector_loop.add_reader,
            fd,
            self._real_loop.call_soon_threadsafe,
            wrapper,
        )

    def add_writer(
        self, fd: _FileDescriptorLike, callback: Callable[..., None], *args: Any
    ) -> None:
        seq = next(_seq_gen)
        self._writer_seq[fd] = seq

        def wrapper() -> None:
            if self._writer_seq.get(fd, None) != seq:
                return
            callback(*args)

        return self._run_on_selector(
            self._selector_loop.add_writer,
            fd,
            self._real_loop.call_soon_threadsafe,
            wrapper,
        )

    def remove_reader(self, fd: _FileDescriptorLike) -> None:
        del self._reader_seq[fd]
        return self._run_on_selector(self._selector_loop.remove_reader, fd)

    def remove_writer(self, fd: _FileDescriptorLike) -> None:
        del self._writer_seq[fd]
        return self._run_on_selector(self._selector_loop.remove_writer, fd)
