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
from __future__ import absolute_import, division, with_statement

import functools
import sys

from tornado.stack_context import ExceptionStackContext
from tornado.util import raise_exc_info

try:
    from concurrent import futures
except ImportError:
    futures = None


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
        except Exception, e:
            future.set_exception(e)
        return future

dummy_executor = DummyExecutor()

def run_on_executor(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        callback = kwargs.pop("callback")
        future = self.executor.submit(fn, self, *args, **kwargs)
        if callback:
            self.io_loop.add_future(future, callback)
        return future
    return wrapper

# TODO: this needs a better name
def future_wrap(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        future = Future()
        if kwargs.get('callback') is not None:
            future.add_done_callback(kwargs.pop('callback'))
        kwargs['callback'] = future.set_result
        def handle_error(typ, value, tb):
            future.set_exception(value)
            return True
        with ExceptionStackContext(handle_error):
            f(*args, **kwargs)
        return future
    return wrapper
