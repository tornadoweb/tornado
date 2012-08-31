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

from tornado.util import raise_exc_info

try:
    from concurrent import futures
except ImportError:
    futures = None


class DummyFuture(object):
    def __init__(self, result, exc_info=None):
        self._result = result
        self._exc_info = exc_info

    def cancel(self):
        return False

    def cancelled(self):
        return False

    def running(self):
        return False

    def done(self):
        return True

    def result(self, timeout=None):
        if self._exc_info:
            raise_exc_info(self._exc_info)
        return self._result

    def exception(self, timeout=None):
        if self._exc_info:
            return self._exc_info[1]
        else:
            return None

    def add_done_callback(self, fn):
        fn(self)


class DummyExecutor(object):
    def submit(self, fn, *args, **kwargs):
        try:
            return DummyFuture(fn(*args, **kwargs))
        except Exception:
            return DummyFuture(result=None, exc_info=sys.exc_info())

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
