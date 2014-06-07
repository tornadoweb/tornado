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
        @gen.coroutine
        def get(self):
            http_client = AsyncHTTPClient()
            response = yield http_client.fetch("http://example.com")
            do_something_with_response(response)
            self.render("template.html")

Most asynchronous functions in Tornado return a `.Future`;
yielding this object returns its `~.Future.result`.

For functions that do not return ``Futures``, `Task` works with any
function that takes a ``callback`` keyword argument (most Tornado functions
can be used in either style, although the ``Future`` style is preferred
since it is both shorter and provides better exception handling)::

    @gen.coroutine
    def get(self):
        yield gen.Task(AsyncHTTPClient().fetch, "http://example.com")

You can also yield a list or dict of ``Futures`` and/or ``Tasks``, which will be
started at the same time and run in parallel; a list or dict of results will
be returned when they are all finished::

    @gen.coroutine
    def get(self):
        http_client = AsyncHTTPClient()
        response1, response2 = yield [http_client.fetch(url1),
                                      http_client.fetch(url2)]
        response_dict = yield dict(response3=http_client.fetch(url3),
                                   response4=http_client.fetch(url4))
        response3 = response_dict['response3']
        response4 = response_dict['response4']

.. versionchanged:: 3.2
   Dict support added.

For more complicated interfaces, `Task` can be split into two parts:
`Callback` and `Wait`::

    class GenAsyncHandler2(RequestHandler):
        @gen.coroutine
        def get(self):
            http_client = AsyncHTTPClient()
            http_client.fetch("http://example.com",
                              callback=(yield gen.Callback("key")))
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
from __future__ import absolute_import, division, print_function, with_statement

import collections
import functools
import itertools
import sys
import types

from tornado.concurrent import Future, TracebackFuture, is_future, chain_future
from tornado.ioloop import IOLoop
from tornado import stack_context


class KeyReuseError(Exception):
    pass


class UnknownKeyError(Exception):
    pass


class LeakedCallbackError(Exception):
    pass


class BadYieldError(Exception):
    pass


class ReturnValueIgnoredError(Exception):
    pass


class TimeoutError(Exception):
    """Exception raised by ``with_timeout``."""


def engine(func):
    """Callback-oriented decorator for asynchronous generators.

    This is an older interface; for new code that does not need to be
    compatible with versions of Tornado older than 3.0 the
    `coroutine` decorator is recommended instead.

    This decorator is similar to `coroutine`, except it does not
    return a `.Future` and the ``callback`` argument is not treated
    specially.

    In most cases, functions decorated with `engine` should take
    a ``callback`` argument and invoke it with their result when
    they are finished.  One notable exception is the
    `~tornado.web.RequestHandler` :ref:`HTTP verb methods <verbs>`,
    which use ``self.finish()`` in place of a callback argument.
    """
    func = _make_coroutine_wrapper(func, replace_callback=False)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        future = func(*args, **kwargs)
        def final_callback(future):
            if future.result() is not None:
                raise ReturnValueIgnoredError(
                    "@gen.engine functions cannot return values: %r" %
                    (future.result(),))
        future.add_done_callback(final_callback)
    return wrapper


def coroutine(func, replace_callback=True):
    """Decorator for asynchronous generators.

    Any generator that yields objects from this module must be wrapped
    in either this decorator or `engine`.

    Coroutines may "return" by raising the special exception
    `Return(value) <Return>`.  In Python 3.3+, it is also possible for
    the function to simply use the ``return value`` statement (prior to
    Python 3.3 generators were not allowed to also return values).
    In all versions of Python a coroutine that simply wishes to exit
    early may use the ``return`` statement without a value.

    Functions with this decorator return a `.Future`.  Additionally,
    they may be called with a ``callback`` keyword argument, which
    will be invoked with the future's result when it resolves.  If the
    coroutine fails, the callback will not be run and an exception
    will be raised into the surrounding `.StackContext`.  The
    ``callback`` argument is not visible inside the decorated
    function; it is handled by the decorator itself.

    From the caller's perspective, ``@gen.coroutine`` is similar to
    the combination of ``@return_future`` and ``@gen.engine``.
    """
    return _make_coroutine_wrapper(func, replace_callback=True)


def _make_coroutine_wrapper(func, replace_callback):
    """The inner workings of ``@gen.coroutine`` and ``@gen.engine``.

    The two decorators differ in their treatment of the ``callback``
    argument, so we cannot simply implement ``@engine`` in terms of
    ``@coroutine``.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        future = TracebackFuture()

        if replace_callback and 'callback' in kwargs:
            callback = kwargs.pop('callback')
            IOLoop.current().add_future(
                future, lambda future: callback(future.result()))

        try:
            result = func(*args, **kwargs)
        except (Return, StopIteration) as e:
            result = getattr(e, 'value', None)
        except Exception:
            future.set_exc_info(sys.exc_info())
            return future
        else:
            if isinstance(result, types.GeneratorType):
                # Inline the first iteration of Runner.run.  This lets us
                # avoid the cost of creating a Runner when the coroutine
                # never actually yields, which in turn allows us to
                # use "optional" coroutines in critical path code without
                # performance penalty for the synchronous case.
                try:
                    orig_stack_contexts = stack_context._state.contexts
                    yielded = next(result)
                    if stack_context._state.contexts is not orig_stack_contexts:
                        yielded = TracebackFuture()
                        yielded.set_exception(
                            stack_context.StackContextInconsistentError(
                                'stack_context inconsistency (probably caused '
                                'by yield within a "with StackContext" block)'))
                except (StopIteration, Return) as e:
                    future.set_result(getattr(e, 'value', None))
                except Exception:
                    future.set_exc_info(sys.exc_info())
                else:
                    Runner(result, future, yielded)
                return future
        future.set_result(result)
        return future
    return wrapper


class Return(Exception):
    """Special exception to return a value from a `coroutine`.

    If this exception is raised, its value argument is used as the
    result of the coroutine::

        @gen.coroutine
        def fetch_json(url):
            response = yield AsyncHTTPClient().fetch(url)
            raise gen.Return(json_decode(response.body))

    In Python 3.3, this exception is no longer necessary: the ``return``
    statement can be used directly to return a value (previously
    ``yield`` and ``return`` with a value could not be combined in the
    same function).

    By analogy with the return statement, the value argument is optional,
    but it is never necessary to ``raise gen.Return()``.  The ``return``
    statement can be used with no arguments instead.
    """
    def __init__(self, value=None):
        super(Return, self).__init__()
        self.value = value


class YieldPoint(object):
    """Base class for objects that may be yielded from the generator.

    Applications do not normally need to use this class, but it may be
    subclassed to provide additional yielding behavior.
    """
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
    """Returns the results of multiple previous `Callbacks <Callback>`.

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


def Task(func, *args, **kwargs):
    """Runs a single asynchronous operation.

    Takes a function (and optional additional arguments) and runs it with
    those arguments plus a ``callback`` keyword argument.  The argument passed
    to the callback is returned as the result of the yield expression.

    A `Task` is equivalent to a `Callback`/`Wait` pair (with a unique
    key generated automatically)::

        result = yield gen.Task(func, args)

        func(args, callback=(yield gen.Callback(key)))
        result = yield gen.Wait(key)

    .. versionchanged:: 4.0
       ``gen.Task`` is now a function that returns a `.Future`, instead of
       a subclass of `YieldPoint`.  It still behaves the same way when
       yielded.
    """
    future = Future()
    def handle_exception(typ, value, tb):
        if future.done():
            return False
        future.set_exc_info((typ, value, tb))
        return True
    def set_result(result):
        if future.done():
            return
        future.set_result(result)
    with stack_context.ExceptionStackContext(handle_exception):
        func(*args, callback=_argument_adapter(set_result), **kwargs)
    return future


class YieldFuture(YieldPoint):
    def __init__(self, future, io_loop=None):
        self.future = future
        self.io_loop = io_loop or IOLoop.current()

    def start(self, runner):
        if not self.future.done():
            self.runner = runner
            self.key = object()
            runner.register_callback(self.key)
            self.io_loop.add_future(self.future, runner.result_callback(self.key))
        else:
            self.runner = None
            self.result = self.future.result()

    def is_ready(self):
        if self.runner is not None:
            return self.runner.is_ready(self.key)
        else:
            return True

    def get_result(self):
        if self.runner is not None:
            return self.runner.pop_result(self.key).result()
        else:
            return self.result


class Multi(YieldPoint):
    """Runs multiple asynchronous operations in parallel.

    Takes a list of ``YieldPoints`` or ``Futures`` and returns a list of
    their responses.  It is not necessary to call `Multi` explicitly,
    since the engine will do so automatically when the generator yields
    a list of ``YieldPoints`` or a mixture of ``YieldPoints`` and ``Futures``.

    Instead of a list, the argument may also be a dictionary whose values are
    Futures, in which case a parallel dictionary is returned mapping the same
    keys to their results.
    """
    def __init__(self, children):
        self.keys = None
        if isinstance(children, dict):
            self.keys = list(children.keys())
            children = children.values()
        self.children = []
        for i in children:
            if is_future(i):
                i = YieldFuture(i)
            self.children.append(i)
        assert all(isinstance(i, YieldPoint) for i in self.children)
        self.unfinished_children = set(self.children)

    def start(self, runner):
        for i in self.children:
            i.start(runner)

    def is_ready(self):
        finished = list(itertools.takewhile(
            lambda i: i.is_ready(), self.unfinished_children))
        self.unfinished_children.difference_update(finished)
        return not self.unfinished_children

    def get_result(self):
        result = (i.get_result() for i in self.children)
        if self.keys is not None:
            return dict(zip(self.keys, result))
        else:
            return list(result)


def multi_future(children):
    """Wait for multiple asynchronous futures in parallel.

    Takes a list of ``Futures`` (but *not* other ``YieldPoints``) and returns
    a new Future that resolves when all the other Futures are done.
    If all the ``Futures`` succeeded, the returned Future's result is a list
    of their results.  If any failed, the returned Future raises the exception
    of the first one to fail.

    Instead of a list, the argument may also be a dictionary whose values are
    Futures, in which case a parallel dictionary is returned mapping the same
    keys to their results.

    It is not necessary to call `multi_future` explcitly, since the engine will
    do so automatically when the generator yields a list of `Futures`.
    This function is faster than the `Multi` `YieldPoint` because it does not
    require the creation of a stack context.

    .. versionadded:: 4.0
    """
    if isinstance(children, dict):
        keys = list(children.keys())
        children = children.values()
    else:
        keys = None
    assert all(is_future(i) for i in children)
    unfinished_children = set(children)

    future = Future()
    if not children:
        future.set_result({} if keys is not None else [])
    def callback(f):
        unfinished_children.remove(f)
        if not unfinished_children:
            try:
                result_list = [i.result() for i in children]
            except Exception:
                future.set_exc_info(sys.exc_info())
            else:
                if keys is not None:
                    future.set_result(dict(zip(keys, result_list)))
                else:
                    future.set_result(result_list)
    for f in children:
        f.add_done_callback(callback)
    return future


def maybe_future(x):
    """Converts ``x`` into a `.Future`.

    If ``x`` is already a `.Future`, it is simply returned; otherwise
    it is wrapped in a new `.Future`.  This is suitable for use as
    ``result = yield gen.maybe_future(f())`` when you don't know whether
    ``f()`` returns a `.Future` or not.
    """
    if is_future(x):
        return x
    else:
        fut = Future()
        fut.set_result(x)
        return fut


def with_timeout(timeout, future, io_loop=None):
    """Wraps a `.Future` in a timeout.

    Raises `TimeoutError` if the input future does not complete before
    ``timeout``, which may be specified in any form allowed by
    `.IOLoop.add_timeout` (i.e. a `datetime.timedelta` or an absolute time
    relative to `.IOLoop.time`)

    Currently only supports Futures, not other `YieldPoint` classes.

    .. versionadded:: 4.0
    """
    # TODO: allow yield points in addition to futures?
    # Tricky to do with stack_context semantics.
    #
    # It's tempting to optimize this by cancelling the input future on timeout
    # instead of creating a new one, but A) we can't know if we are the only
    # one waiting on the input future, so cancelling it might disrupt other
    # callers and B) concurrent futures can only be cancelled while they are
    # in the queue, so cancellation cannot reliably bound our waiting time.
    result = Future()
    chain_future(future, result)
    if io_loop is None:
        io_loop = IOLoop.current()
    timeout_handle = io_loop.add_timeout(
        timeout,
        lambda: result.set_exception(TimeoutError("Timeout")))
    if isinstance(future, Future):
        # We know this future will resolve on the IOLoop, so we don't
        # need the extra thread-safety of IOLoop.add_future (and we also
        # don't care about StackContext here.
        future.add_done_callback(
            lambda future: io_loop.remove_timeout(timeout_handle))
    else:
        # concurrent.futures.Futures may resolve on any thread, so we
        # need to route them back to the IOLoop.
        io_loop.add_future(
            future, lambda future: io_loop.remove_timeout(timeout_handle))
    return result


_null_future = Future()
_null_future.set_result(None)

moment = Future()
moment.__doc__ = \
    """A special object which may be yielded to allow the IOLoop to run for
one iteration.

This is not needed in normal use but it can be helpful in long-running
coroutines that are likely to yield Futures that are ready instantly.

Usage: ``yield gen.moment``

.. versionadded:: 4.0
"""
moment.set_result(None)


class Runner(object):
    """Internal implementation of `tornado.gen.engine`.

    Maintains information about pending callbacks and their results.

    The results of the generator are stored in ``result_future`` (a
    `.TracebackFuture`)
    """
    def __init__(self, gen, result_future, first_yielded):
        self.gen = gen
        self.result_future = result_future
        self.future = _null_future
        self.yield_point = None
        self.pending_callbacks = None
        self.results = None
        self.running = False
        self.finished = False
        self.had_exception = False
        self.io_loop = IOLoop.current()
        # For efficiency, we do not create a stack context until we
        # reach a YieldPoint (stack contexts are required for the historical
        # semantics of YieldPoints, but not for Futures).  When we have
        # done so, this field will be set and must be called at the end
        # of the coroutine.
        self.stack_context_deactivate = None
        if self.handle_yield(first_yielded):
            self.run()

    def register_callback(self, key):
        """Adds ``key`` to the list of callbacks."""
        if self.pending_callbacks is None:
            # Lazily initialize the old-style YieldPoint data structures.
            self.pending_callbacks = set()
            self.results = {}
        if key in self.pending_callbacks:
            raise KeyReuseError("key %r is already pending" % (key,))
        self.pending_callbacks.add(key)

    def is_ready(self, key):
        """Returns true if a result is available for ``key``."""
        if self.pending_callbacks is None or key not in self.pending_callbacks:
            raise UnknownKeyError("key %r is not pending" % (key,))
        return key in self.results

    def set_result(self, key, result):
        """Sets the result for ``key`` and attempts to resume the generator."""
        self.results[key] = result
        if self.yield_point is not None and self.yield_point.is_ready():
            try:
                self.future.set_result(self.yield_point.get_result())
            except:
                self.future.set_exc_info(sys.exc_info())
            self.yield_point = None
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
                future = self.future
                if not future.done():
                    return
                self.future = None
                try:
                    orig_stack_contexts = stack_context._state.contexts
                    try:
                        value = future.result()
                    except Exception:
                        self.had_exception = True
                        yielded = self.gen.throw(*sys.exc_info())
                    else:
                        yielded = self.gen.send(value)
                    if stack_context._state.contexts is not orig_stack_contexts:
                        self.gen.throw(
                            stack_context.StackContextInconsistentError(
                                'stack_context inconsistency (probably caused '
                                'by yield within a "with StackContext" block)'))
                except (StopIteration, Return) as e:
                    self.finished = True
                    self.future = _null_future
                    if self.pending_callbacks and not self.had_exception:
                        # If we ran cleanly without waiting on all callbacks
                        # raise an error (really more of a warning).  If we
                        # had an exception then some callbacks may have been
                        # orphaned, so skip the check in that case.
                        raise LeakedCallbackError(
                            "finished without waiting for callbacks %r" %
                            self.pending_callbacks)
                    self.result_future.set_result(getattr(e, 'value', None))
                    self.result_future = None
                    self._deactivate_stack_context()
                    return
                except Exception:
                    self.finished = True
                    self.future = _null_future
                    self.result_future.set_exc_info(sys.exc_info())
                    self.result_future = None
                    self._deactivate_stack_context()
                    return
                if not self.handle_yield(yielded):
                    return
        finally:
            self.running = False

    def handle_yield(self, yielded):
        if isinstance(yielded, list):
            if all(is_future(f) for f in yielded):
                yielded = multi_future(yielded)
            else:
                yielded = Multi(yielded)
        elif isinstance(yielded, dict):
            if all(is_future(f) for f in yielded.values()):
                yielded = multi_future(yielded)
            else:
                yielded = Multi(yielded)

        if isinstance(yielded, YieldPoint):
            self.future = TracebackFuture()
            def start_yield_point():
                try:
                    yielded.start(self)
                    if yielded.is_ready():
                        self.future.set_result(
                            yielded.get_result())
                    else:
                        self.yield_point = yielded
                except Exception:
                    self.future = TracebackFuture()
                    self.future.set_exc_info(sys.exc_info())
            if self.stack_context_deactivate is None:
                # Start a stack context if this is the first
                # YieldPoint we've seen.
                with stack_context.ExceptionStackContext(
                        self.handle_exception) as deactivate:
                    self.stack_context_deactivate = deactivate
                    def cb():
                        start_yield_point()
                        self.run()
                    self.io_loop.add_callback(cb)
                    return False
            else:
                start_yield_point()
        elif is_future(yielded):
            self.future = yielded
            if not self.future.done() or self.future is moment:
                self.io_loop.add_future(
                    self.future, lambda f: self.run())
                return False
        else:
            self.future = TracebackFuture()
            self.future.set_exception(BadYieldError(
                "yielded unknown object %r" % (yielded,)))
        return True

    def result_callback(self, key):
        return stack_context.wrap(_argument_adapter(
            functools.partial(self.set_result, key)))

    def handle_exception(self, typ, value, tb):
        if not self.running and not self.finished:
            self.future = TracebackFuture()
            self.future.set_exc_info((typ, value, tb))
            self.run()
            return True
        else:
            return False

    def _deactivate_stack_context(self):
        if self.stack_context_deactivate is not None:
            self.stack_context_deactivate()
            self.stack_context_deactivate = None

Arguments = collections.namedtuple('Arguments', ['args', 'kwargs'])


def _argument_adapter(callback):
    """Returns a function that when invoked runs ``callback`` with one arg.

    If the function returned by this function is called with exactly
    one argument, that argument is passed to ``callback``.  Otherwise
    the args tuple and kwargs dict are wrapped in an `Arguments` object.
    """
    def wrapper(*args, **kwargs):
        if kwargs or len(args) > 1:
            callback(Arguments(args, kwargs))
        elif args:
            callback(args[0])
        else:
            callback(None)
    return wrapper
