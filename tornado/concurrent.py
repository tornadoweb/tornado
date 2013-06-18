#!/usr/bin/env python
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
"""Utilities for working with threads and ``Futures``.

``Futures`` are a pattern for concurrent programming introduced in
Python 3.2 in the `concurrent.futures` package (this package has also
been backported to older versions of Python and can be installed with
``pip install futures``).  Tornado will use `concurrent.futures.Future` if
it is available; otherwise it will use a compatible class defined in this
module.
"""
from __future__ import absolute_import, division, print_function, with_statement

import functools
import sys

from tornado.stack_context import ExceptionStackContext, wrap
from tornado.util import raise_exc_info, ArgReplacer

try:
    from concurrent import futures
except ImportError:
    futures = None


class ReturnValueIgnoredError(Exception):
    pass


class _DummyFuture(object):
    def __init__(self):
        self._done = False
        self._result = None
        self._exception = None
        self._callbacks = []

    def cancel(self):
        return False

    def cancelled(self):
        return False

    def running(self):
        return not self._done

    def done(self):
        return self._done

    def result(self, timeout=None):
        self._check_done()
        if self._exception:
            raise self._exception
        return self._result

    def exception(self, timeout=None):
        self._check_done()
        if self._exception:
            return self._exception
        else:
            return None

    def add_done_callback(self, fn):
        if self._done:
            fn(self)
        else:
            self._callbacks.append(fn)

    def set_result(self, result):
        self._result = result
        self._set_done()

    def set_exception(self, exception):
        self._exception = exception
        self._set_done()

    def _check_done(self):
        if not self._done:
            raise Exception("DummyFuture does not support blocking for results")

    def _set_done(self):
        self._done = True
        for cb in self._callbacks:
            # TODO: error handling
            cb(self)
        self._callbacks = None

if futures is None:
    Future = _DummyFuture
else:
    Future = futures.Future


class TracebackFuture(Future):
    """Subclass of `Future` which can store a traceback with
    exceptions.

    The traceback is automatically available in Python 3, but in the
    Python 2 futures backport this information is discarded.
    """
    def __init__(self):
        super(TracebackFuture, self).__init__()
        self.__exc_info = None

    def exc_info(self):
        return self.__exc_info

    def set_exc_info(self, exc_info):
        """Traceback-aware replacement for
        `~concurrent.futures.Future.set_exception`.
        """
        self.__exc_info = exc_info
        self.set_exception(exc_info[1])

    def result(self):
        if self.__exc_info is not None:
            raise_exc_info(self.__exc_info)
        else:
            return super(TracebackFuture, self).result()


class DummyExecutor(object):
    def submit(self, fn, *args, **kwargs):
        future = TracebackFuture()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception:
            future.set_exc_info(sys.exc_info())
        return future

    def shutdown(self, wait=True):
        pass

dummy_executor = DummyExecutor()


def run_on_executor(fn):
    """Decorator to run a synchronous method asynchronously on an executor.

    The decorated method may be called with a ``callback`` keyword
    argument and returns a future.
    """
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        callback = kwargs.pop("callback", None)
        future = self.executor.submit(fn, self, *args, **kwargs)
        if callback:
            self.io_loop.add_future(future,
                                    lambda future: callback(future.result()))
        return future
    return wrapper


_NO_RESULT = object()


def return_future(f):
    """Decorator to make a function that returns via callback return a
    `Future`.

    The wrapped function should take a ``callback`` keyword argument
    and invoke it with one argument when it has finished.  To signal failure,
    the function can simply raise an exception (which will be
    captured by the `.StackContext` and passed along to the ``Future``).

    From the caller's perspective, the callback argument is optional.
    If one is given, it will be invoked when the function is complete
    with `Future.result()` as an argument.  If the function fails, the
    callback will not be run and an exception will be raised into the
    surrounding `.StackContext`.

    If no callback is given, the caller should use the ``Future`` to
    wait for the function to complete (perhaps by yielding it in a
    `.gen.engine` function, or passing it to `.IOLoop.add_future`).

    Usage::

        @return_future
        def future_func(arg1, arg2, callback):
            # Do stuff (possibly asynchronous)
            callback(result)

        @gen.engine
        def caller(callback):
            yield future_func(arg1, arg2)
            callback()

    Note that ``@return_future`` and ``@gen.engine`` can be applied to the
    same function, provided ``@return_future`` appears first.  However,
    consider using ``@gen.coroutine`` instead of this combination.
    """
    replacer = ArgReplacer(f, 'callback')

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        future = TracebackFuture()
        callback, args, kwargs = replacer.replace(
            lambda value=_NO_RESULT: future.set_result(value),
            args, kwargs)

        def handle_error(typ, value, tb):
            future.set_exc_info((typ, value, tb))
            return True
        exc_info = None
        with ExceptionStackContext(handle_error):
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
            raise_exc_info(exc_info)

        # If the caller passed in a callback, schedule it to be called
        # when the future resolves.  It is important that this happens
        # just before we return the future, or else we risk confusing
        # stack contexts with multiple exceptions (one here with the
        # immediate exception, and again when the future resolves and
        # the callback triggers its exception by calling future.result()).
        if callback is not None:
            def run_callback(future):
                result = future.result()
                if result is _NO_RESULT:
                    callback()
                else:
                    callback(future.result())
            future.add_done_callback(wrap(run_callback))
        return future
    return wrapper


def chain_future(a, b):
    """Chain two futures together so that when one completes, so does the other.

    The result (success or failure) of ``a`` will be copied to ``b``.
    """
    def copy(future):
        assert future is a
        if (isinstance(a, TracebackFuture) and isinstance(b, TracebackFuture)
                and a.exc_info() is not None):
            b.set_exc_info(a.exc_info())
        elif a.exception() is not None:
            b.set_exception(a.exception())
        else:
            b.set_result(a.result())
    a.add_done_callback(copy)
