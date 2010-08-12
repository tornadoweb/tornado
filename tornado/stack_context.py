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
      logging.error("exception in asynchronous operation", exc_info=True)
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

@contextlib.contextmanager
def StackContext(context_factory):
    '''Establishes the given context as a StackContext that will be transferred.

    Note that the parameter is a callable that returns a context
    manager, not the context itself.  That is, where for a
    non-transferable context manager you would say
      with my_context():
    StackContext takes the function itself rather than its result:
      with StackContext(my_context):
    '''
    old_contexts = _state.contexts
    try:
        _state.contexts = old_contexts + (context_factory,)
        with context_factory():
            yield
    finally:
        _state.contexts = old_contexts

@contextlib.contextmanager
def NullContext():
    '''Resets the StackContext.

    Useful when creating a shared resource on demand (e.g. an AsyncHTTPClient)
    where the stack that caused the creating is not relevant to future
    operations.
    '''
    old_contexts = _state.contexts
    try:
        _state.contexts = ()
        yield
    finally:
        _state.contexts = old_contexts

def wrap(fn):
    '''Returns a callable object that will resore the current StackContext
    when executed.

    Use this whenever saving a callback to be executed later in a
    different execution context (either in a different thread or
    asynchronously in the same thread).
    '''
    # functools.wraps doesn't appear to work on functools.partial objects
    #@functools.wraps(fn)
    def wrapped(callback, contexts, *args, **kwargs):
        # _state.contexts and contexts may share a common prefix.
        # For each element of contexts not in that prefix, create a new
        # StackContext object.
        # TODO(bdarnell): do we want to be strict about the order,
        # or is what we really want just set(contexts) - set(_state.contexts)?
        # I think we do want to be strict about using identity comparison,
        # so a set may not be quite right.  Conversely, it's not very stack-like
        # to have new contexts pop up in the middle, so would we want to
        # ensure there are no existing contexts not in the stack being restored?
        # That feels right, but given the difficulty of handling errors at this
        # level I'm not going to check for it now.
        pairs = itertools.izip(itertools.chain(_state.contexts,
                                               itertools.repeat(None)),
                               contexts)
        new_contexts = []
        for old, new in itertools.dropwhile(lambda x: x[0] is x[1], pairs):
            new_contexts.append(StackContext(new))
        if new_contexts:
            with contextlib.nested(*new_contexts):
                callback(*args, **kwargs)
        else:
            callback(*args, **kwargs)
    if getattr(fn, 'stack_context_wrapped', False):
        return fn
    contexts = _state.contexts
    result = functools.partial(wrapped, fn, contexts)
    result.stack_context_wrapped = True
    return result
