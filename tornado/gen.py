"""``tornado.gen`` is a generator-based interface to make it easier to
work in an asynchronous environment.  Code using the ``gen`` module
is technically asynchronous, but it is written as a single generator
instead of a collection of separate functions.

For example, the following asynchronous handler::

    class AsyncHandler(RequestHandler):
        @asynchronous
        def get(self):
            http_client = AsyncHTTPClient()
            http_client.fetch("http://example.com",
                              callback=self.on_fetch)

        def on_fetch(self, response):
            do_something_with_response(response)
            self.render("template.html")

could be written with ``gen`` as::

    class GenAsyncHandler(RequestHandler):
        @asynchronous
        @gen.engine
        def get(self):
            http_client = AsyncHTTPClient()
            response = yield gen.Task(http_client.fetch, "http://example.com")
            do_something_with_response(response)
            self.render("template.html")

`Task` works with any function that takes a ``callback`` keyword
argument.  You can also yield a list of ``Tasks``, which will be
started at the same time and run in parallel; a list of results will
be returned when they are all finished::

    def get(self):
        http_client = AsyncHTTPClient()
        response1, response2 = yield [gen.Task(http_client.fetch, url1),
                                      gen.Task(http_client.fetch, url2)]

For more complicated interfaces, `Task` can be split into two parts:
`Callback` and `Wait`::

    class GenAsyncHandler2(RequestHandler):
        @asynchronous
        @gen.engine
        def get(self):
            http_client = AsyncHTTPClient()
            http_client.fetch("http://example.com",
                              callback=(yield gen.Callback("key"))
            response = yield gen.Wait("key")
            do_something_with_response(response)
            self.render("template.html")

The ``key`` argument to `Callback` and `Wait` allows for multiple
asynchronous operations to be started at different times and proceed
in parallel: yield several callbacks with different keys, then wait
for them once all the async operations have started.

The result of a `Wait` or `Task` yield expression depends on how the callback
was run.  If it was called with no arguments, the result is ``None``.  If
it was called with one argument, the result is that argument.  If it was
called with more than one argument or any keyword arguments, the result
is an `Arguments` object, which is a named tuple ``(args, kwargs)``.
"""
from __future__ import absolute_import, division, with_statement

import functools
import operator
import sys
import types

from tornado.stack_context import ExceptionStackContext


class KeyReuseError(Exception):
    pass


class UnknownKeyError(Exception):
    pass


class LeakedCallbackError(Exception):
    pass


class BadYieldError(Exception):
    pass


def engine(func):
    """Decorator for asynchronous generators.

    Any generator that yields objects from this module must be wrapped
    in this decorator.  The decorator only works on functions that are
    already asynchronous.  For `~tornado.web.RequestHandler`
    ``get``/``post``/etc methods, this means that both the
    `tornado.web.asynchronous` and `tornado.gen.engine` decorators
    must be used (for proper exception handling, ``asynchronous``
    should come before ``gen.engine``).  In most other cases, it means
    that it doesn't make sense to use ``gen.engine`` on functions that
    don't already take a callback argument.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        runner = None

        def handle_exception(typ, value, tb):
            # if the function throws an exception before its first "yield"
            # (or is not a generator at all), the Runner won't exist yet.
            # However, in that case we haven't reached anything asynchronous
            # yet, so we can just let the exception propagate.
            if runner is not None:
                return runner.handle_exception(typ, value, tb)
            return False
        with ExceptionStackContext(handle_exception):
            gen = func(*args, **kwargs)
            if isinstance(gen, types.GeneratorType):
                runner = Runner(gen)
                runner.run()
                return
            assert gen is None, gen
            # no yield, so we're done
    return wrapper


class YieldPoint(object):
    """Base class for objects that may be yielded from the generator."""
    def start(self, runner):
        """Called by the runner after the generator has yielded.

        No other methods will be called on this object before ``start``.
        """
        raise NotImplementedError()

    def is_ready(self):
        """Called by the runner to determine whether to resume the generator.

        Returns a boolean; may be called more than once.
        """
        raise NotImplementedError()

    def get_result(self):
        """Returns the value to use as the result of the yield expression.

        This method will only be called once, and only after `is_ready`
        has returned true.
        """
        raise NotImplementedError()


class Callback(YieldPoint):
    """Returns a callable object that will allow a matching `Wait` to proceed.

    The key may be any value suitable for use as a dictionary key, and is
    used to match ``Callbacks`` to their corresponding ``Waits``.  The key
    must be unique among outstanding callbacks within a single run of the
    generator function, but may be reused across different runs of the same
    function (so constants generally work fine).

    The callback may be called with zero or one arguments; if an argument
    is given it will be returned by `Wait`.
    """
    def __init__(self, key):
        self.key = key

    def start(self, runner):
        self.runner = runner
        runner.register_callback(self.key)

    def is_ready(self):
        return True

    def get_result(self):
        return self.runner.result_callback(self.key)


class Wait(YieldPoint):
    """Returns the argument passed to the result of a previous `Callback`."""
    def __init__(self, key):
        self.key = key

    def start(self, runner):
        self.runner = runner

    def is_ready(self):
        return self.runner.is_ready(self.key)

    def get_result(self):
        return self.runner.pop_result(self.key)


class WaitAll(YieldPoint):
    """Returns the results of multiple previous `Callbacks`.

    The argument is a sequence of `Callback` keys, and the result is
    a list of results in the same order.

    `WaitAll` is equivalent to yielding a list of `Wait` objects.
    """
    def __init__(self, keys):
        self.keys = keys

    def start(self, runner):
        self.runner = runner

    def is_ready(self):
        return all(self.runner.is_ready(key) for key in self.keys)

    def get_result(self):
        return [self.runner.pop_result(key) for key in self.keys]


class Task(YieldPoint):
    """Runs a single asynchronous operation.

    Takes a function (and optional additional arguments) and runs it with
    those arguments plus a ``callback`` keyword argument.  The argument passed
    to the callback is returned as the result of the yield expression.

    A `Task` is equivalent to a `Callback`/`Wait` pair (with a unique
    key generated automatically)::

        result = yield gen.Task(func, args)

        func(args, callback=(yield gen.Callback(key)))
        result = yield gen.Wait(key)
    """
    def __init__(self, func, *args, **kwargs):
        assert "callback" not in kwargs
        self.args = args
        self.kwargs = kwargs
        self.func = func

    def start(self, runner):
        self.runner = runner
        self.key = object()
        runner.register_callback(self.key)
        self.kwargs["callback"] = runner.result_callback(self.key)
        self.func(*self.args, **self.kwargs)

    def is_ready(self):
        return self.runner.is_ready(self.key)

    def get_result(self):
        return self.runner.pop_result(self.key)


class Multi(YieldPoint):
    """Runs multiple asynchronous operations in parallel.

    Takes a list of ``Tasks`` or other ``YieldPoints`` and returns a list of
    their responses.  It is not necessary to call `Multi` explicitly,
    since the engine will do so automatically when the generator yields
    a list of ``YieldPoints``.
    """
    def __init__(self, children):
        assert all(isinstance(i, YieldPoint) for i in children)
        self.children = children

    def start(self, runner):
        for i in self.children:
            i.start(runner)

    def is_ready(self):
        return all(i.is_ready() for i in self.children)

    def get_result(self):
        return [i.get_result() for i in self.children]


class _NullYieldPoint(YieldPoint):
    def start(self, runner):
        pass

    def is_ready(self):
        return True

    def get_result(self):
        return None


class Runner(object):
    """Internal implementation of `tornado.gen.engine`.

    Maintains information about pending callbacks and their results.
    """
    def __init__(self, gen):
        self.gen = gen
        self.yield_point = _NullYieldPoint()
        self.pending_callbacks = set()
        self.results = {}
        self.running = False
        self.finished = False
        self.exc_info = None
        self.had_exception = False

    def register_callback(self, key):
        """Adds ``key`` to the list of callbacks."""
        if key in self.pending_callbacks:
            raise KeyReuseError("key %r is already pending" % key)
        self.pending_callbacks.add(key)

    def is_ready(self, key):
        """Returns true if a result is available for ``key``."""
        if key not in self.pending_callbacks:
            raise UnknownKeyError("key %r is not pending" % key)
        return key in self.results

    def set_result(self, key, result):
        """Sets the result for ``key`` and attempts to resume the generator."""
        self.results[key] = result
        self.run()

    def pop_result(self, key):
        """Returns the result for ``key`` and unregisters it."""
        self.pending_callbacks.remove(key)
        return self.results.pop(key)

    def run(self):
        """Starts or resumes the generator, running until it reaches a
        yield point that is not ready.
        """
        if self.running or self.finished:
            return
        try:
            self.running = True
            while True:
                if self.exc_info is None:
                    try:
                        if not self.yield_point.is_ready():
                            return
                        next = self.yield_point.get_result()
                    except Exception:
                        self.exc_info = sys.exc_info()
                try:
                    if self.exc_info is not None:
                        self.had_exception = True
                        exc_info = self.exc_info
                        self.exc_info = None
                        yielded = self.gen.throw(*exc_info)
                    else:
                        yielded = self.gen.send(next)
                except StopIteration:
                    self.finished = True
                    if self.pending_callbacks and not self.had_exception:
                        # If we ran cleanly without waiting on all callbacks
                        # raise an error (really more of a warning).  If we
                        # had an exception then some callbacks may have been
                        # orphaned, so skip the check in that case.
                        raise LeakedCallbackError(
                            "finished without waiting for callbacks %r" %
                            self.pending_callbacks)
                    return
                except Exception:
                    self.finished = True
                    raise
                if isinstance(yielded, list):
                    yielded = Multi(yielded)
                if isinstance(yielded, YieldPoint):
                    self.yield_point = yielded
                    try:
                        self.yield_point.start(self)
                    except Exception:
                        self.exc_info = sys.exc_info()
                else:
                    self.exc_info = (BadYieldError("yielded unknown object %r" % yielded),)
        finally:
            self.running = False

    def result_callback(self, key):
        def inner(*args, **kwargs):
            if kwargs or len(args) > 1:
                result = Arguments(args, kwargs)
            elif args:
                result = args[0]
            else:
                result = None
            self.set_result(key, result)
        return inner

    def handle_exception(self, typ, value, tb):
        if not self.running and not self.finished:
            self.exc_info = (typ, value, tb)
            self.run()
            return True
        else:
            return False

# in python 2.6+ this could be a collections.namedtuple


class Arguments(tuple):
    """The result of a yield expression whose callback had more than one
    argument (or keyword arguments).

    The `Arguments` object can be used as a tuple ``(args, kwargs)``
    or an object with attributes ``args`` and ``kwargs``.
    """
    __slots__ = ()

    def __new__(cls, args, kwargs):
        return tuple.__new__(cls, (args, kwargs))

    args = property(operator.itemgetter(0))
    kwargs = property(operator.itemgetter(1))
