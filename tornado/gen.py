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

`Task` works with any function that takes a ``callback`` keyword argument
(and runs that callback with zero or one arguments).  For more complicated
interfaces, `Task` can be split into two parts: `Callback` and `Wait`::

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
asynchronous operations to proceed in parallel: yield several
callbacks with different keys, then wait for them once all the async
operations have started.
"""

import functools
import types

class KeyReuseError(Exception): pass
class UnknownKeyError(Exception): pass
class LeakedCallbackError(Exception): pass
class BadYieldError(Exception): pass

def engine(func):
    """Decorator for asynchronous generators.

    Any generator that yields objects from this module must be wrapped
    in this decorator.  The decorator only works on functions that are
    already asynchronous.  For `~tornado.web.RequestHandler`
    ``get``/``post``/etc methods, this means that both the `tornado.gen.engine`
    and `tornado.web.asynchronous` decorators must be used (in either order).
    In most other cases, it means that it doesn't make sense to use
    ``gen.engine`` on functions that don't already take a callback argument.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        gen = func(*args, **kwargs)
        if isinstance(gen, types.GeneratorType):
            Runner(gen).run()
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

        May be called repeatedly until it returns True.
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
        return self.callback

    def callback(self, arg=None):
        self.runner.set_result(self.key, arg)

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
    """
    def __init__(self, keys):
        assert isinstance(keys, list)
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
        kwargs["callback"] = self.callback
        self.func = functools.partial(func, *args, **kwargs)

    def start(self, runner):
        self.runner = runner
        self.key = object()
        runner.register_callback(self.key)
        self.func()
    
    def is_ready(self):
        return self.runner.is_ready(self.key)

    def get_result(self):
        return self.runner.pop_result(self.key)

    def callback(self, arg=None):
        self.runner.set_result(self.key, arg)

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
        self.waiting = None
        self.running = False

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
        if self.running:
            return
        try:
            self.running = True
            while True:
                if not self.yield_point.is_ready():
                    return
                next = self.yield_point.get_result()
                try:
                    yielded = self.gen.send(next)
                except StopIteration:
                    if self.pending_callbacks:
                        raise LeakedCallbackError(
                            "finished without waiting for callbacks %r" %
                            self.pending_callbacks)
                    return
                if not isinstance(yielded, YieldPoint):
                    raise BadYieldError("yielded unknown object %r" % yielded)
                self.yield_point = yielded
                self.yield_point.start(self)
        finally:
            self.running = False

