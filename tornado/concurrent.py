#
# Copyright 2012 Facebook
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
"""Utilities for working with ``Future`` objects.

``Futures`` are a pattern for concurrent programming introduced in
Python 3.2 in the `concurrent.futures` package, and also adopted (in a
slightly different form) in Python 3.4's `asyncio` package. This
package defines a ``Future`` class that is an alias for `asyncio.Future`
when available, and a compatible implementation for older versions of
Python. It also includes some utility functions for interacting with
``Future`` objects.

While this package is an important part of Tornado's internal
implementation, applications rarely need to interact with it
directly.
"""
from __future__ import absolute_import, division, print_function

import functools
import sys
import warnings

from tornado.stack_context import ExceptionStackContext, wrap
from tornado.util import ArgReplacer

try:
    from concurrent import futures
except ImportError:
    futures = None

try:
    import asyncio
except ImportError:
    asyncio = None

try:
    import typing
except ImportError:
    typing = None


class ReturnValueIgnoredError(Exception):
    pass


Future = asyncio.Future  # noqa

if futures is None:
    FUTURES = Future  # type: typing.Union[type, typing.Tuple[type, ...]]
else:
    FUTURES = (futures.Future, Future)


def is_future(x):
    return isinstance(x, FUTURES)


class DummyExecutor(object):
    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future_set_result_unless_cancelled(future, fn(*args, **kwargs))
        except Exception:
            future_set_exc_info(future, sys.exc_info())
        return future

    def shutdown(self, wait=True):
        pass


dummy_executor = DummyExecutor()


def run_on_executor(*args, **kwargs):
    """Decorator to run a synchronous method asynchronously on an executor.

    The decorated method may be called with a ``callback`` keyword
    argument and returns a future.

    The executor to be used is determined by the ``executor``
    attributes of ``self``. To use a different attribute name, pass a
    keyword argument to the decorator::

        @run_on_executor(executor='_thread_pool')
        def foo(self):
            pass

    This decorator should not be confused with the similarly-named
    `.IOLoop.run_in_executor`. In general, using ``run_in_executor``
    when *calling* a blocking method is recommended instead of using
    this decorator when *defining* a method. If compatibility with older
    versions of Tornado is required, consider defining an executor
    and using ``executor.submit()`` at the call site.

    .. versionchanged:: 4.2
       Added keyword arguments to use alternative attributes.

    .. versionchanged:: 5.0
       Always uses the current IOLoop instead of ``self.io_loop``.

    .. versionchanged:: 5.1
       Returns a `.Future` compatible with ``await`` instead of a
       `concurrent.futures.Future`.

    .. deprecated:: 5.1

       The ``callback`` argument is deprecated and will be removed in
       6.0. The decorator itself is discouraged in new code but will
       not be removed in 6.0.
    """
    def run_on_executor_decorator(fn):
        executor = kwargs.get("executor", "executor")

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            callback = kwargs.pop("callback", None)
            async_future = Future()
            conc_future = getattr(self, executor).submit(fn, self, *args, **kwargs)
            chain_future(conc_future, async_future)
            if callback:
                warnings.warn("callback arguments are deprecated, use the returned Future instead",
                              DeprecationWarning)
                from tornado.ioloop import IOLoop
                IOLoop.current().add_future(
                    async_future, lambda future: callback(future.result()))
            return async_future
        return wrapper
    if args and kwargs:
        raise ValueError("cannot combine positional and keyword args")
    if len(args) == 1:
        return run_on_executor_decorator(args[0])
    elif len(args) != 0:
        raise ValueError("expected 1 argument, got %d", len(args))
    return run_on_executor_decorator


_NO_RESULT = object()


def return_future(f):
    """Decorator to make a function that returns via callback return a
    `Future`.

    This decorator was provided to ease the transition from
    callback-oriented code to coroutines. It is not recommended for
    new code.

    The wrapped function should take a ``callback`` keyword argument
    and invoke it with one argument when it has finished.  To signal failure,
    the function can simply raise an exception (which will be
    captured by the `.StackContext` and passed along to the ``Future``).

    From the caller's perspective, the callback argument is optional.
    If one is given, it will be invoked when the function is complete
    with ``Future.result()`` as an argument.  If the function fails, the
    callback will not be run and an exception will be raised into the
    surrounding `.StackContext`.

    If no callback is given, the caller should use the ``Future`` to
    wait for the function to complete (perhaps by yielding it in a
    coroutine, or passing it to `.IOLoop.add_future`).

    Usage:

    .. testcode::

        @return_future
        def future_func(arg1, arg2, callback):
            # Do stuff (possibly asynchronous)
            callback(result)

        async def caller():
            await future_func(arg1, arg2)

    ..

    Note that ``@return_future`` and ``@gen.engine`` can be applied to the
    same function, provided ``@return_future`` appears first.  However,
    consider using ``@gen.coroutine`` instead of this combination.

    .. versionchanged:: 5.1

       Now raises a `.DeprecationWarning` if a callback argument is passed to
       the decorated function and deprecation warnings are enabled.

    .. deprecated:: 5.1

       This decorator will be removed in Tornado 6.0. New code should
       use coroutines directly instead of wrapping callback-based code
       with this decorator. Interactions with non-Tornado
       callback-based code should be managed explicitly to avoid
       relying on the `.ExceptionStackContext` built into this
       decorator.
    """
    warnings.warn("@return_future is deprecated, use coroutines instead",
                  DeprecationWarning)
    return _non_deprecated_return_future(f)


def _non_deprecated_return_future(f):
    # Allow auth.py to use this decorator without triggering
    # deprecation warnings. This will go away once auth.py has removed
    # its legacy interfaces in 6.0.
    replacer = ArgReplacer(f, 'callback')

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        future = Future()
        callback, args, kwargs = replacer.replace(
            lambda value=_NO_RESULT: future_set_result_unless_cancelled(future, value),
            args, kwargs)

        def handle_error(typ, value, tb):
            future_set_exc_info(future, (typ, value, tb))
            return True
        exc_info = None
        with ExceptionStackContext(handle_error, delay_warning=True):
            try:
                result = f(*args, **kwargs)
                if result is not None:
                    raise ReturnValueIgnoredError(
                        "@return_future should not be used with functions "
                        "that return values")
            except:
                exc_info = sys.exc_info()
                raise
        if exc_info is not None:
            # If the initial synchronous part of f() raised an exception,
            # go ahead and raise it to the caller directly without waiting
            # for them to inspect the Future.
            future.result()

        # If the caller passed in a callback, schedule it to be called
        # when the future resolves.  It is important that this happens
        # just before we return the future, or else we risk confusing
        # stack contexts with multiple exceptions (one here with the
        # immediate exception, and again when the future resolves and
        # the callback triggers its exception by calling future.result()).
        if callback is not None:
            warnings.warn("callback arguments are deprecated, use the returned Future instead",
                          DeprecationWarning)

            def run_callback(future):
                result = future.result()
                if result is _NO_RESULT:
                    callback()
                else:
                    callback(future.result())
            future_add_done_callback(future, wrap(run_callback))
        return future
    return wrapper


def chain_future(a, b):
    """Chain two futures together so that when one completes, so does the other.

    The result (success or failure) of ``a`` will be copied to ``b``, unless
    ``b`` has already been completed or cancelled by the time ``a`` finishes.

    .. versionchanged:: 5.0

       Now accepts both Tornado/asyncio `Future` objects and
       `concurrent.futures.Future`.

    """
    def copy(future):
        assert future is a
        if b.done():
            return
        if (hasattr(a, 'exc_info') and
                a.exc_info() is not None):
            future_set_exc_info(b, a.exc_info())
        elif a.exception() is not None:
            b.set_exception(a.exception())
        else:
            b.set_result(a.result())
    if isinstance(a, Future):
        future_add_done_callback(a, copy)
    else:
        # concurrent.futures.Future
        from tornado.ioloop import IOLoop
        IOLoop.current().add_future(a, copy)


def future_set_result_unless_cancelled(future, value):
    """Set the given ``value`` as the `Future`'s result, if not cancelled.

    Avoids asyncio.InvalidStateError when calling set_result() on
    a cancelled `asyncio.Future`.

    .. versionadded:: 5.0
    """
    if not future.cancelled():
        future.set_result(value)


def future_set_exc_info(future, exc_info):
    """Set the given ``exc_info`` as the `Future`'s exception.

    Understands both `asyncio.Future` and Tornado's extensions to
    enable better tracebacks on Python 2.

    .. versionadded:: 5.0
    """
    if hasattr(future, 'set_exc_info'):
        # Tornado's Future
        future.set_exc_info(exc_info)
    else:
        # asyncio.Future
        future.set_exception(exc_info[1])


def future_add_done_callback(future, callback):
    """Arrange to call ``callback`` when ``future`` is complete.

    ``callback`` is invoked with one argument, the ``future``.

    If ``future`` is already done, ``callback`` is invoked immediately.
    This may differ from the behavior of ``Future.add_done_callback``,
    which makes no such guarantee.

    .. versionadded:: 5.0
    """
    if future.done():
        callback(future)
    else:
        future.add_done_callback(callback)
