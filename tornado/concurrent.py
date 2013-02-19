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
from __future__ import absolute_import, division, print_function, with_statement

import functools
import sys

from tornado.stack_context import ExceptionStackContext
from tornado.util import raise_exc_info, ArgReplacer

try:
    from concurrent import futures
except ImportError:
    futures = None

class ReturnValueIgnoredError(Exception):
    pass

class DummyFuture(object):
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
    Future = DummyFuture
else:
    Future = futures.Future


class DummyExecutor(object):
    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as e:
            future.set_exception(e)
        return future

dummy_executor = DummyExecutor()


def run_on_executor(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        callback = kwargs.pop("callback", None)
        future = self.executor.submit(fn, self, *args, **kwargs)
        if callback:
            self.io_loop.add_future(future, callback)
        return future
    return wrapper


def return_future(f):
    """Decorator to make a function that returns via callback return a `Future`.

    The wrapped function should take a ``callback`` keyword argument
    and invoke it with one argument when it has finished.  To signal failure,
    the function can simply raise an exception (which will be
    captured by the `stack_context` and passed along to the `Future`).

    From the caller's perspective, the callback argument is optional.
    If one is given, it will be invoked when the function is complete
    with the `Future` as an argument.  If no callback is given, the caller
    should use the `Future` to wait for the function to complete
    (perhaps by yielding it in a `gen.engine` function, or passing it
    to `IOLoop.add_future`).

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
    same function, provided ``@return_future`` appears first.
    """
    replacer = ArgReplacer(f, 'callback')
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        future = Future()
        callback, args, kwargs = replacer.replace(future.set_result,
                                                  args, kwargs)
        if callback is not None:
            future.add_done_callback(callback)

        def handle_error(typ, value, tb):
            future.set_exception(value)
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
        return future
    return wrapper

def chain_future(a, b):
    """Chain two futures together so that when one completes, so does the other.

    The result (success or failure) of ``a`` will be copied to ``b``.
    """
    def copy(future):
        assert future is a
        if a.exception() is not None:
            b.set_exception(a.exception())
        else:
            b.set_result(a.result())
    a.add_done_callback(copy)
