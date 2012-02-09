#!/usr/bin/env python
#
# Copyright 2010 Facebook
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

'''StackContext allows applications to maintain threadlocal-like state
that follows execution as it moves to other execution contexts.

The motivating examples are to eliminate the need for explicit
async_callback wrappers (as in tornado.web.RequestHandler), and to
allow some additional context to be kept for logging.

This is slightly magic, but it's an extension of the idea that an exception
handler is a kind of stack-local state and when that stack is suspended
and resumed in a new context that state needs to be preserved.  StackContext
shifts the burden of restoring that state from each call site (e.g.
wrapping each AsyncHTTPClient callback in async_callback) to the mechanisms
that transfer control from one context to another (e.g. AsyncHTTPClient
itself, IOLoop, thread pools, etc).

Example usage::

    @contextlib.contextmanager
    def die_on_error():
        try:
            yield
        except Exception:
            logging.error("exception in asynchronous operation",exc_info=True)
            sys.exit(1)

    with StackContext(die_on_error):
        # Any exception thrown here *or in callback and its desendents*
        # will cause the process to exit instead of spinning endlessly
        # in the ioloop.
        http_client.fetch(url, callback)
    ioloop.start()

Most applications shouln't have to work with `StackContext` directly.
Here are a few rules of thumb for when it's necessary:

* If you're writing an asynchronous library that doesn't rely on a
  stack_context-aware library like `tornado.ioloop` or `tornado.iostream`
  (for example, if you're writing a thread pool), use
  `stack_context.wrap()` before any asynchronous operations to capture the
  stack context from where the operation was started.

* If you're writing an asynchronous library that has some shared
  resources (such as a connection pool), create those shared resources
  within a ``with stack_context.NullContext():`` block.  This will prevent
  ``StackContexts`` from leaking from one request to another.

* If you want to write something like an exception handler that will
  persist across asynchronous calls, create a new `StackContext` (or
  `ExceptionStackContext`), and make your asynchronous calls in a ``with``
  block that references your `StackContext`.
'''

from __future__ import absolute_import, division, with_statement

import contextlib
import functools
import itertools
import sys
import threading


class _State(threading.local):
    def __init__(self):
        self.contexts = ()
_state = _State()


class StackContext(object):
    '''Establishes the given context as a StackContext that will be transferred.

    Note that the parameter is a callable that returns a context
    manager, not the context itself.  That is, where for a
    non-transferable context manager you would say::

      with my_context():

    StackContext takes the function itself rather than its result::

      with StackContext(my_context):
    '''
    def __init__(self, context_factory):
        self.context_factory = context_factory

    # Note that some of this code is duplicated in ExceptionStackContext
    # below.  ExceptionStackContext is more common and doesn't need
    # the full generality of this class.
    def __enter__(self):
        self.old_contexts = _state.contexts
        # _state.contexts is a tuple of (class, arg) pairs
        _state.contexts = (self.old_contexts +
                           ((StackContext, self.context_factory),))
        try:
            self.context = self.context_factory()
            self.context.__enter__()
        except Exception:
            _state.contexts = self.old_contexts
            raise

    def __exit__(self, type, value, traceback):
        try:
            return self.context.__exit__(type, value, traceback)
        finally:
            _state.contexts = self.old_contexts


class ExceptionStackContext(object):
    '''Specialization of StackContext for exception handling.

    The supplied exception_handler function will be called in the
    event of an uncaught exception in this context.  The semantics are
    similar to a try/finally clause, and intended use cases are to log
    an error, close a socket, or similar cleanup actions.  The
    exc_info triple (type, value, traceback) will be passed to the
    exception_handler function.

    If the exception handler returns true, the exception will be
    consumed and will not be propagated to other exception handlers.
    '''
    def __init__(self, exception_handler):
        self.exception_handler = exception_handler

    def __enter__(self):
        self.old_contexts = _state.contexts
        _state.contexts = (self.old_contexts +
                           ((ExceptionStackContext, self.exception_handler),))

    def __exit__(self, type, value, traceback):
        try:
            if type is not None:
                return self.exception_handler(type, value, traceback)
        finally:
            _state.contexts = self.old_contexts


class NullContext(object):
    '''Resets the StackContext.

    Useful when creating a shared resource on demand (e.g. an AsyncHTTPClient)
    where the stack that caused the creating is not relevant to future
    operations.
    '''
    def __enter__(self):
        self.old_contexts = _state.contexts
        _state.contexts = ()

    def __exit__(self, type, value, traceback):
        _state.contexts = self.old_contexts


class _StackContextWrapper(functools.partial):
    pass


def wrap(fn):
    '''Returns a callable object that will restore the current StackContext
    when executed.

    Use this whenever saving a callback to be executed later in a
    different execution context (either in a different thread or
    asynchronously in the same thread).
    '''
    if fn is None or fn.__class__ is _StackContextWrapper:
        return fn
    # functools.wraps doesn't appear to work on functools.partial objects
    #@functools.wraps(fn)

    def wrapped(callback, contexts, *args, **kwargs):
        if contexts is _state.contexts or not contexts:
            callback(*args, **kwargs)
            return
        if not _state.contexts:
            new_contexts = [cls(arg) for (cls, arg) in contexts]
        # If we're moving down the stack, _state.contexts is a prefix
        # of contexts.  For each element of contexts not in that prefix,
        # create a new StackContext object.
        # If we're moving up the stack (or to an entirely different stack),
        # _state.contexts will have elements not in contexts.  Use
        # NullContext to clear the state and then recreate from contexts.
        elif (len(_state.contexts) > len(contexts) or
            any(a[1] is not b[1]
                for a, b in itertools.izip(_state.contexts, contexts))):
            # contexts have been removed or changed, so start over
            new_contexts = ([NullContext()] +
                            [cls(arg) for (cls, arg) in contexts])
        else:
            new_contexts = [cls(arg)
                            for (cls, arg) in contexts[len(_state.contexts):]]
        if len(new_contexts) > 1:
            with _nested(*new_contexts):
                callback(*args, **kwargs)
        elif new_contexts:
            with new_contexts[0]:
                callback(*args, **kwargs)
        else:
            callback(*args, **kwargs)
    if _state.contexts:
        return _StackContextWrapper(wrapped, fn, _state.contexts)
    else:
        return _StackContextWrapper(fn)


@contextlib.contextmanager
def _nested(*managers):
    """Support multiple context managers in a single with-statement.

    Copied from the python 2.6 standard library.  It's no longer present
    in python 3 because the with statement natively supports multiple
    context managers, but that doesn't help if the list of context
    managers is not known until runtime.
    """
    exits = []
    vars = []
    exc = (None, None, None)
    try:
        for mgr in managers:
            exit = mgr.__exit__
            enter = mgr.__enter__
            vars.append(enter())
            exits.append(exit)
        yield vars
    except:
        exc = sys.exc_info()
    finally:
        while exits:
            exit = exits.pop()
            try:
                if exit(*exc):
                    exc = (None, None, None)
            except:
                exc = sys.exc_info()
        if exc != (None, None, None):
            # Don't rely on sys.exc_info() still containing
            # the right information. Another exception may
            # have been raised and caught by an exit method
            raise exc[0], exc[1], exc[2]
