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

Example usage:
    @contextlib.contextmanager
    def die_on_error():
        try:
            yield
        except:
            logging.error("exception in asynchronous operation",exc_info=True)
            sys.exit(1)

    with StackContext(die_on_error):
        # Any exception thrown here *or in callback and its desendents*
        # will cause the process to exit instead of spinning endlessly
        # in the ioloop.
        http_client.fetch(url, callback)
    ioloop.start()
'''

from __future__ import with_statement

import contextlib
import functools
import itertools
import logging
import threading

class _State(threading.local):
    def __init__(self):
        self.contexts = ()
_state = _State()

class StackContext(object):
    def __init__(self, context_factory):
        '''Establishes the given context as a StackContext that will be transferred.

        Note that the parameter is a callable that returns a context
        manager, not the context itself.  That is, where for a
        non-transferable context manager you would say
          with my_context():
        StackContext takes the function itself rather than its result:
          with StackContext(my_context):
        '''
        self.context_factory = context_factory

    def __enter__(self):
        self.old_contexts = _state.contexts
        _state.contexts = self.old_contexts + (self.context_factory,)
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

def ExceptionStackContext(exception_handler):
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
    class Context(object):
        def __enter__(self):
            pass
        def __exit__(self, type, value, traceback):
            if type is not None:
                return exception_handler(type, value, traceback)
    return StackContext(Context)

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

def wrap(fn):
    '''Returns a callable object that will resore the current StackContext
    when executed.

    Use this whenever saving a callback to be executed later in a
    different execution context (either in a different thread or
    asynchronously in the same thread).
    '''
    if fn is None:
      return None
    # functools.wraps doesn't appear to work on functools.partial objects
    #@functools.wraps(fn)
    def wrapped(callback, contexts, *args, **kwargs):
        # If we're moving down the stack, _state.contexts is a prefix
        # of contexts.  For each element of contexts not in that prefix,
        # create a new StackContext object.
        # If we're moving up the stack (or to an entirely different stack),
        # _state.contexts will have elements not in contexts.  Use
        # NullContext to clear the state and then recreate from contexts.
        if (len(_state.contexts) > len(contexts) or
            any(a is not b
                for a, b in itertools.izip(_state.contexts, contexts))):
            # contexts have been removed or changed, so start over
            new_contexts = ([NullContext()] +
                            [StackContext(c) for c in contexts])
        else:
            new_contexts = [StackContext(c)
                            for c in contexts[len(_state.contexts):]]
        if len(new_contexts) > 1:
            with contextlib.nested(*new_contexts):
                callback(*args, **kwargs)
        elif new_contexts:
            with new_contexts[0]:
                callback(*args, **kwargs)
        else:
            callback(*args, **kwargs)
    if getattr(fn, 'stack_context_wrapped', False):
        return fn
    contexts = _state.contexts
    result = functools.partial(wrapped, fn, contexts)
    result.stack_context_wrapped = True
    return result

