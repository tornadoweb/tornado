"""``tornado.gen`` implements generator-based coroutines.

.. note::

   The "decorator and generator" approach in this module is a
   precursor to native coroutines (using ``async def`` and ``await``)
   which were introduced in Python 3.5. Applications that do not
   require compatibility with older versions of Python should use
   native coroutines instead. Some parts of this module are still
   useful with native coroutines, notably `multi`, `sleep`,
   `WaitIterator`, and `with_timeout`. Some of these functions have
   counterparts in the `asyncio` module which may be used as well,
   although the two may not necessarily be 100% compatible.

Coroutines provide an easier way to work in an asynchronous
environment than chaining callbacks. Code using coroutines is
technically asynchronous, but it is written as a single generator
instead of a collection of separate functions.

For example, the following asynchronous handler:

.. testcode::

    class AsyncHandler(RequestHandler):
        @asynchronous
        def get(self):
            http_client = AsyncHTTPClient()
            http_client.fetch("http://example.com",
                              callback=self.on_fetch)

        def on_fetch(self, response):
            do_something_with_response(response)
            self.render("template.html")

.. testoutput::
   :hide:

could be written with ``gen`` as:

.. testcode::

    class GenAsyncHandler(RequestHandler):
        @gen.coroutine
        def get(self):
            http_client = AsyncHTTPClient()
            response = yield http_client.fetch("http://example.com")
            do_something_with_response(response)
            self.render("template.html")

.. testoutput::
   :hide:

Most asynchronous functions in Tornado return a `.Future`;
yielding this object returns its ``Future.result``.

You can also yield a list or dict of ``Futures``, which will be
started at the same time and run in parallel; a list or dict of results will
be returned when they are all finished:

.. testcode::

    @gen.coroutine
    def get(self):
        http_client = AsyncHTTPClient()
        response1, response2 = yield [http_client.fetch(url1),
                                      http_client.fetch(url2)]
        response_dict = yield dict(response3=http_client.fetch(url3),
                                   response4=http_client.fetch(url4))
        response3 = response_dict['response3']
        response4 = response_dict['response4']

.. testoutput::
   :hide:

If the `~functools.singledispatch` library is available (standard in
Python 3.4, available via the `singledispatch
<https://pypi.python.org/pypi/singledispatch>`_ package on older
versions), additional types of objects may be yielded. Tornado includes
support for ``asyncio.Future`` and Twisted's ``Deferred`` class when
``tornado.platform.asyncio`` and ``tornado.platform.twisted`` are imported.
See the `convert_yielded` function to extend this mechanism.

.. versionchanged:: 3.2
   Dict support added.

.. versionchanged:: 4.1
   Support added for yielding ``asyncio`` Futures and Twisted Deferreds
   via ``singledispatch``.

"""
from __future__ import absolute_import, division, print_function

import collections
import functools
import itertools
import os
import sys
import types

from tornado.concurrent import (Future, is_future, chain_future, future_set_exc_info,
                                future_add_done_callback, future_set_result_unless_cancelled)
from tornado.ioloop import IOLoop
from tornado.log import app_log
from tornado import stack_context
from tornado.util import PY3, raise_exc_info, TimeoutError

try:
    try:
        # py34+
        from functools import singledispatch  # type: ignore
    except ImportError:
        from singledispatch import singledispatch  # backport
except ImportError:
    # In most cases, singledispatch is required (to avoid
    # difficult-to-diagnose problems in which the functionality
    # available differs depending on which invisble packages are
    # installed). However, in Google App Engine third-party
    # dependencies are more trouble so we allow this module to be
    # imported without it.
    if 'APPENGINE_RUNTIME' not in os.environ:
        raise
    singledispatch = None

try:
    try:
        # py35+
        from collections.abc import Generator as GeneratorType  # type: ignore
    except ImportError:
        from backports_abc import Generator as GeneratorType  # type: ignore

    try:
        # py35+
        from inspect import isawaitable  # type: ignore
    except ImportError:
        from backports_abc import isawaitable
except ImportError:
    if 'APPENGINE_RUNTIME' not in os.environ:
        raise
    from types import GeneratorType

    def isawaitable(x):  # type: ignore
        return False

if PY3:
    import builtins
else:
    import __builtin__ as builtins


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


def _value_from_stopiteration(e):
    try:
        # StopIteration has a value attribute beginning in py33.
        # So does our Return class.
        return e.value
    except AttributeError:
        pass
    try:
        # Cython backports coroutine functionality by putting the value in
        # e.args[0].
        return e.args[0]
    except (AttributeError, IndexError):
        return None


def _create_future():
    future = Future()
    # Fixup asyncio debug info by removing extraneous stack entries
    source_traceback = getattr(future, "_source_traceback", ())
    while source_traceback:
        # Each traceback entry is equivalent to a
        # (filename, self.lineno, self.name, self.line) tuple
        filename = source_traceback[-1][0]
        if filename == __file__:
            del source_traceback[-1]
        else:
            break
    return future


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
        # The engine interface doesn't give us any way to return
        # errors but to raise them into the stack context.
        # Save the stack context here to use when the Future has resolved.
        future_add_done_callback(future, stack_context.wrap(final_callback))
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

    .. warning::

       When exceptions occur inside a coroutine, the exception
       information will be stored in the `.Future` object. You must
       examine the result of the `.Future` object, or the exception
       may go unnoticed by your code. This means yielding the function
       if called from another coroutine, using something like
       `.IOLoop.run_sync` for top-level calls, or passing the `.Future`
       to `.IOLoop.add_future`.

    """
    return _make_coroutine_wrapper(func, replace_callback=True)


def _make_coroutine_wrapper(func, replace_callback):
    """The inner workings of ``@gen.coroutine`` and ``@gen.engine``.

    The two decorators differ in their treatment of the ``callback``
    argument, so we cannot simply implement ``@engine`` in terms of
    ``@coroutine``.
    """
    # On Python 3.5, set the coroutine flag on our generator, to allow it
    # to be used with 'await'.
    wrapped = func
    if hasattr(types, 'coroutine'):
        func = types.coroutine(func)

    @functools.wraps(wrapped)
    def wrapper(*args, **kwargs):
        future = _create_future()

        if replace_callback and 'callback' in kwargs:
            callback = kwargs.pop('callback')
            IOLoop.current().add_future(
                future, lambda future: callback(future.result()))

        try:
            result = func(*args, **kwargs)
        except (Return, StopIteration) as e:
            result = _value_from_stopiteration(e)
        except Exception:
            future_set_exc_info(future, sys.exc_info())
            try:
                return future
            finally:
                # Avoid circular references
                future = None
        else:
            if isinstance(result, GeneratorType):
                # Inline the first iteration of Runner.run.  This lets us
                # avoid the cost of creating a Runner when the coroutine
                # never actually yields, which in turn allows us to
                # use "optional" coroutines in critical path code without
                # performance penalty for the synchronous case.
                try:
                    orig_stack_contexts = stack_context._state.contexts
                    yielded = next(result)
                    if stack_context._state.contexts is not orig_stack_contexts:
                        yielded = _create_future()
                        yielded.set_exception(
                            stack_context.StackContextInconsistentError(
                                'stack_context inconsistency (probably caused '
                                'by yield within a "with StackContext" block)'))
                except (StopIteration, Return) as e:
                    future_set_result_unless_cancelled(future, _value_from_stopiteration(e))
                except Exception:
                    future_set_exc_info(future, sys.exc_info())
                else:
                    # Provide strong references to Runner objects as long
                    # as their result future objects also have strong
                    # references (typically from the parent coroutine's
                    # Runner). This keeps the coroutine's Runner alive.
                    # We do this by exploiting the public API
                    # add_done_callback() instead of putting a private
                    # attribute on the Future.
                    # (Github issues #1769, #2229).
                    runner = Runner(result, future, yielded)
                    future.add_done_callback(lambda _: runner)
                yielded = None
                try:
                    return future
                finally:
                    # Subtle memory optimization: if next() raised an exception,
                    # the future's exc_info contains a traceback which
                    # includes this stack frame.  This creates a cycle,
                    # which will be collected at the next full GC but has
                    # been shown to greatly increase memory usage of
                    # benchmarks (relative to the refcount-based scheme
                    # used in the absence of cycles).  We can avoid the
                    # cycle by clearing the local variable after we return it.
                    future = None
        future_set_result_unless_cancelled(future, result)
        return future

    wrapper.__wrapped__ = wrapped
    wrapper.__tornado_coroutine__ = True
    return wrapper


def is_coroutine_function(func):
    """Return whether *func* is a coroutine function, i.e. a function
    wrapped with `~.gen.coroutine`.

    .. versionadded:: 4.5
    """
    return getattr(func, '__tornado_coroutine__', False)


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
        # Cython recognizes subclasses of StopIteration with a .args tuple.
        self.args = (value,)


class WaitIterator(object):
    """Provides an iterator to yield the results of futures as they finish.

    Yielding a set of futures like this:

    ``results = yield [future1, future2]``

    pauses the coroutine until both ``future1`` and ``future2``
    return, and then restarts the coroutine with the results of both
    futures. If either future is an exception, the expression will
    raise that exception and all the results will be lost.

    If you need to get the result of each future as soon as possible,
    or if you need the result of some futures even if others produce
    errors, you can use ``WaitIterator``::

      wait_iterator = gen.WaitIterator(future1, future2)
      while not wait_iterator.done():
          try:
              result = yield wait_iterator.next()
          except Exception as e:
              print("Error {} from {}".format(e, wait_iterator.current_future))
          else:
              print("Result {} received from {} at {}".format(
                  result, wait_iterator.current_future,
                  wait_iterator.current_index))

    Because results are returned as soon as they are available the
    output from the iterator *will not be in the same order as the
    input arguments*. If you need to know which future produced the
    current result, you can use the attributes
    ``WaitIterator.current_future``, or ``WaitIterator.current_index``
    to get the index of the future from the input list. (if keyword
    arguments were used in the construction of the `WaitIterator`,
    ``current_index`` will use the corresponding keyword).

    On Python 3.5, `WaitIterator` implements the async iterator
    protocol, so it can be used with the ``async for`` statement (note
    that in this version the entire iteration is aborted if any value
    raises an exception, while the previous example can continue past
    individual errors)::

      async for result in gen.WaitIterator(future1, future2):
          print("Result {} received from {} at {}".format(
              result, wait_iterator.current_future,
              wait_iterator.current_index))

    .. versionadded:: 4.1

    .. versionchanged:: 4.3
       Added ``async for`` support in Python 3.5.

    """
    def __init__(self, *args, **kwargs):
        if args and kwargs:
            raise ValueError(
                "You must provide args or kwargs, not both")

        if kwargs:
            self._unfinished = dict((f, k) for (k, f) in kwargs.items())
            futures = list(kwargs.values())
        else:
            self._unfinished = dict((f, i) for (i, f) in enumerate(args))
            futures = args

        self._finished = collections.deque()
        self.current_index = self.current_future = None
        self._running_future = None

        for future in futures:
            future_add_done_callback(future, self._done_callback)

    def done(self):
        """Returns True if this iterator has no more results."""
        if self._finished or self._unfinished:
            return False
        # Clear the 'current' values when iteration is done.
        self.current_index = self.current_future = None
        return True

    def next(self):
        """Returns a `.Future` that will yield the next available result.

        Note that this `.Future` will not be the same object as any of
        the inputs.
        """
        self._running_future = Future()

        if self._finished:
            self._return_result(self._finished.popleft())

        return self._running_future

    def _done_callback(self, done):
        if self._running_future and not self._running_future.done():
            self._return_result(done)
        else:
            self._finished.append(done)

    def _return_result(self, done):
        """Called set the returned future's state that of the future
        we yielded, and set the current future for the iterator.
        """
        chain_future(done, self._running_future)

        self.current_future = done
        self.current_index = self._unfinished.pop(done)

    def __aiter__(self):
        return self

    def __anext__(self):
        if self.done():
            # Lookup by name to silence pyflakes on older versions.
            raise getattr(builtins, 'StopAsyncIteration')()
        return self.next()


class YieldPoint(object):
    """Base class for objects that may be yielded from the generator.

    .. deprecated:: 4.0
       Use `Futures <.Future>` instead.
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

    .. deprecated:: 4.0
       Use `Futures <.Future>` instead.
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
    """Returns the argument passed to the result of a previous `Callback`.

    .. deprecated:: 4.0
       Use `Futures <.Future>` instead.
    """
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

    .. deprecated:: 4.0
       Use `Futures <.Future>` instead.
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
    """Adapts a callback-based asynchronous function for use in coroutines.

    Takes a function (and optional additional arguments) and runs it with
    those arguments plus a ``callback`` keyword argument.  The argument passed
    to the callback is returned as the result of the yield expression.

    .. versionchanged:: 4.0
       ``gen.Task`` is now a function that returns a `.Future`, instead of
       a subclass of `YieldPoint`.  It still behaves the same way when
       yielded.
    """
    future = _create_future()

    def handle_exception(typ, value, tb):
        if future.done():
            return False
        future_set_exc_info(future, (typ, value, tb))
        return True

    def set_result(result):
        if future.done():
            return
        future_set_result_unless_cancelled(future, result)
    with stack_context.ExceptionStackContext(handle_exception):
        func(*args, callback=_argument_adapter(set_result), **kwargs)
    return future


class YieldFuture(YieldPoint):
    def __init__(self, future):
        """Adapts a `.Future` to the `YieldPoint` interface.

        .. versionchanged:: 5.0
           The ``io_loop`` argument (deprecated since version 4.1) has been removed.
        """
        self.future = future
        self.io_loop = IOLoop.current()

    def start(self, runner):
        if not self.future.done():
            self.runner = runner
            self.key = object()
            runner.register_callback(self.key)
            self.io_loop.add_future(self.future, runner.result_callback(self.key))
        else:
            self.runner = None
            self.result_fn = self.future.result

    def is_ready(self):
        if self.runner is not None:
            return self.runner.is_ready(self.key)
        else:
            return True

    def get_result(self):
        if self.runner is not None:
            return self.runner.pop_result(self.key).result()
        else:
            return self.result_fn()


def _contains_yieldpoint(children):
    """Returns True if ``children`` contains any YieldPoints.

    ``children`` may be a dict or a list, as used by `MultiYieldPoint`
    and `multi_future`.
    """
    if isinstance(children, dict):
        return any(isinstance(i, YieldPoint) for i in children.values())
    if isinstance(children, list):
        return any(isinstance(i, YieldPoint) for i in children)
    return False


def multi(children, quiet_exceptions=()):
    """Runs multiple asynchronous operations in parallel.

    ``children`` may either be a list or a dict whose values are
    yieldable objects. ``multi()`` returns a new yieldable
    object that resolves to a parallel structure containing their
    results. If ``children`` is a list, the result is a list of
    results in the same order; if it is a dict, the result is a dict
    with the same keys.

    That is, ``results = yield multi(list_of_futures)`` is equivalent
    to::

        results = []
        for future in list_of_futures:
            results.append(yield future)

    If any children raise exceptions, ``multi()`` will raise the first
    one. All others will be logged, unless they are of types
    contained in the ``quiet_exceptions`` argument.

    If any of the inputs are `YieldPoints <YieldPoint>`, the returned
    yieldable object is a `YieldPoint`. Otherwise, returns a `.Future`.
    This means that the result of `multi` can be used in a native
    coroutine if and only if all of its children can be.

    In a ``yield``-based coroutine, it is not normally necessary to
    call this function directly, since the coroutine runner will
    do it automatically when a list or dict is yielded. However,
    it is necessary in ``await``-based coroutines, or to pass
    the ``quiet_exceptions`` argument.

    This function is available under the names ``multi()`` and ``Multi()``
    for historical reasons.

    Cancelling a `.Future` returned by ``multi()`` does not cancel its
    children. `asyncio.gather` is similar to ``multi()``, but it does
    cancel its children.

    .. versionchanged:: 4.2
       If multiple yieldables fail, any exceptions after the first
       (which is raised) will be logged. Added the ``quiet_exceptions``
       argument to suppress this logging for selected exception types.

    .. versionchanged:: 4.3
       Replaced the class ``Multi`` and the function ``multi_future``
       with a unified function ``multi``. Added support for yieldables
       other than `YieldPoint` and `.Future`.

    """
    if _contains_yieldpoint(children):
        return MultiYieldPoint(children, quiet_exceptions=quiet_exceptions)
    else:
        return multi_future(children, quiet_exceptions=quiet_exceptions)


Multi = multi


class MultiYieldPoint(YieldPoint):
    """Runs multiple asynchronous operations in parallel.

    This class is similar to `multi`, but it always creates a stack
    context even when no children require it. It is not compatible with
    native coroutines.

    .. versionchanged:: 4.2
       If multiple ``YieldPoints`` fail, any exceptions after the first
       (which is raised) will be logged. Added the ``quiet_exceptions``
       argument to suppress this logging for selected exception types.

    .. versionchanged:: 4.3
       Renamed from ``Multi`` to ``MultiYieldPoint``. The name ``Multi``
       remains as an alias for the equivalent `multi` function.

    .. deprecated:: 4.3
       Use `multi` instead.
    """
    def __init__(self, children, quiet_exceptions=()):
        self.keys = None
        if isinstance(children, dict):
            self.keys = list(children.keys())
            children = children.values()
        self.children = []
        for i in children:
            if not isinstance(i, YieldPoint):
                i = convert_yielded(i)
            if is_future(i):
                i = YieldFuture(i)
            self.children.append(i)
        assert all(isinstance(i, YieldPoint) for i in self.children)
        self.unfinished_children = set(self.children)
        self.quiet_exceptions = quiet_exceptions

    def start(self, runner):
        for i in self.children:
            i.start(runner)

    def is_ready(self):
        finished = list(itertools.takewhile(
            lambda i: i.is_ready(), self.unfinished_children))
        self.unfinished_children.difference_update(finished)
        return not self.unfinished_children

    def get_result(self):
        result_list = []
        exc_info = None
        for f in self.children:
            try:
                result_list.append(f.get_result())
            except Exception as e:
                if exc_info is None:
                    exc_info = sys.exc_info()
                else:
                    if not isinstance(e, self.quiet_exceptions):
                        app_log.error("Multiple exceptions in yield list",
                                      exc_info=True)
        if exc_info is not None:
            raise_exc_info(exc_info)
        if self.keys is not None:
            return dict(zip(self.keys, result_list))
        else:
            return list(result_list)


def multi_future(children, quiet_exceptions=()):
    """Wait for multiple asynchronous futures in parallel.

    This function is similar to `multi`, but does not support
    `YieldPoints <YieldPoint>`.

    .. versionadded:: 4.0

    .. versionchanged:: 4.2
       If multiple ``Futures`` fail, any exceptions after the first (which is
       raised) will be logged. Added the ``quiet_exceptions``
       argument to suppress this logging for selected exception types.

    .. deprecated:: 4.3
       Use `multi` instead.
    """
    if isinstance(children, dict):
        keys = list(children.keys())
        children = children.values()
    else:
        keys = None
    children = list(map(convert_yielded, children))
    assert all(is_future(i) or isinstance(i, _NullFuture) for i in children)
    unfinished_children = set(children)

    future = _create_future()
    if not children:
        future_set_result_unless_cancelled(future,
                                           {} if keys is not None else [])

    def callback(f):
        unfinished_children.remove(f)
        if not unfinished_children:
            result_list = []
            for f in children:
                try:
                    result_list.append(f.result())
                except Exception as e:
                    if future.done():
                        if not isinstance(e, quiet_exceptions):
                            app_log.error("Multiple exceptions in yield list",
                                          exc_info=True)
                    else:
                        future_set_exc_info(future, sys.exc_info())
            if not future.done():
                if keys is not None:
                    future_set_result_unless_cancelled(future,
                                                       dict(zip(keys, result_list)))
                else:
                    future_set_result_unless_cancelled(future, result_list)

    listening = set()
    for f in children:
        if f not in listening:
            listening.add(f)
            future_add_done_callback(f, callback)
    return future


def maybe_future(x):
    """Converts ``x`` into a `.Future`.

    If ``x`` is already a `.Future`, it is simply returned; otherwise
    it is wrapped in a new `.Future`.  This is suitable for use as
    ``result = yield gen.maybe_future(f())`` when you don't know whether
    ``f()`` returns a `.Future` or not.

    .. deprecated:: 4.3
       This function only handles ``Futures``, not other yieldable objects.
       Instead of `maybe_future`, check for the non-future result types
       you expect (often just ``None``), and ``yield`` anything unknown.
    """
    if is_future(x):
        return x
    else:
        fut = _create_future()
        fut.set_result(x)
        return fut


def with_timeout(timeout, future, quiet_exceptions=()):
    """Wraps a `.Future` (or other yieldable object) in a timeout.

    Raises `tornado.util.TimeoutError` if the input future does not
    complete before ``timeout``, which may be specified in any form
    allowed by `.IOLoop.add_timeout` (i.e. a `datetime.timedelta` or
    an absolute time relative to `.IOLoop.time`)

    If the wrapped `.Future` fails after it has timed out, the exception
    will be logged unless it is of a type contained in ``quiet_exceptions``
    (which may be an exception type or a sequence of types).

    Does not support `YieldPoint` subclasses.

    The wrapped `.Future` is not canceled when the timeout expires,
    permitting it to be reused. `asyncio.wait_for` is similar to this
    function but it does cancel the wrapped `.Future` on timeout.

    .. versionadded:: 4.0

    .. versionchanged:: 4.1
       Added the ``quiet_exceptions`` argument and the logging of unhandled
       exceptions.

    .. versionchanged:: 4.4
       Added support for yieldable objects other than `.Future`.

    """
    # TODO: allow YieldPoints in addition to other yieldables?
    # Tricky to do with stack_context semantics.
    #
    # It's tempting to optimize this by cancelling the input future on timeout
    # instead of creating a new one, but A) we can't know if we are the only
    # one waiting on the input future, so cancelling it might disrupt other
    # callers and B) concurrent futures can only be cancelled while they are
    # in the queue, so cancellation cannot reliably bound our waiting time.
    future = convert_yielded(future)
    result = _create_future()
    chain_future(future, result)
    io_loop = IOLoop.current()

    def error_callback(future):
        try:
            future.result()
        except Exception as e:
            if not isinstance(e, quiet_exceptions):
                app_log.error("Exception in Future %r after timeout",
                              future, exc_info=True)

    def timeout_callback():
        if not result.done():
            result.set_exception(TimeoutError("Timeout"))
        # In case the wrapped future goes on to fail, log it.
        future_add_done_callback(future, error_callback)
    timeout_handle = io_loop.add_timeout(
        timeout, timeout_callback)
    if isinstance(future, Future):
        # We know this future will resolve on the IOLoop, so we don't
        # need the extra thread-safety of IOLoop.add_future (and we also
        # don't care about StackContext here.
        future_add_done_callback(
            future, lambda future: io_loop.remove_timeout(timeout_handle))
    else:
        # concurrent.futures.Futures may resolve on any thread, so we
        # need to route them back to the IOLoop.
        io_loop.add_future(
            future, lambda future: io_loop.remove_timeout(timeout_handle))
    return result


def sleep(duration):
    """Return a `.Future` that resolves after the given number of seconds.

    When used with ``yield`` in a coroutine, this is a non-blocking
    analogue to `time.sleep` (which should not be used in coroutines
    because it is blocking)::

        yield gen.sleep(0.5)

    Note that calling this function on its own does nothing; you must
    wait on the `.Future` it returns (usually by yielding it).

    .. versionadded:: 4.1
    """
    f = _create_future()
    IOLoop.current().call_later(duration,
                                lambda: future_set_result_unless_cancelled(f, None))
    return f


class _NullFuture(object):
    """_NullFuture resembles a Future that finished with a result of None.

    It's not actually a `Future` to avoid depending on a particular event loop.
    Handled as a special case in the coroutine runner.
    """
    def result(self):
        return None

    def done(self):
        return True


# _null_future is used as a dummy value in the coroutine runner. It differs
# from moment in that moment always adds a delay of one IOLoop iteration
# while _null_future is processed as soon as possible.
_null_future = _NullFuture()

moment = _NullFuture()
moment.__doc__ = \
    """A special object which may be yielded to allow the IOLoop to run for
one iteration.

This is not needed in normal use but it can be helpful in long-running
coroutines that are likely to yield Futures that are ready instantly.

Usage: ``yield gen.moment``

.. versionadded:: 4.0

.. deprecated:: 4.5
   ``yield None`` (or ``yield`` with no argument) is now equivalent to
    ``yield gen.moment``.
"""


class Runner(object):
    """Internal implementation of `tornado.gen.engine`.

    Maintains information about pending callbacks and their results.

    The results of the generator are stored in ``result_future`` (a
    `.Future`)
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
            gen = result_future = first_yielded = None
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
                future_set_result_unless_cancelled(self.future,
                                                   self.yield_point.get_result())
            except:
                future_set_exc_info(self.future, sys.exc_info())
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
                    exc_info = None

                    try:
                        value = future.result()
                    except Exception:
                        self.had_exception = True
                        exc_info = sys.exc_info()
                    future = None

                    if exc_info is not None:
                        try:
                            yielded = self.gen.throw(*exc_info)
                        finally:
                            # Break up a reference to itself
                            # for faster GC on CPython.
                            exc_info = None
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
                    future_set_result_unless_cancelled(self.result_future,
                                                       _value_from_stopiteration(e))
                    self.result_future = None
                    self._deactivate_stack_context()
                    return
                except Exception:
                    self.finished = True
                    self.future = _null_future
                    future_set_exc_info(self.result_future, sys.exc_info())
                    self.result_future = None
                    self._deactivate_stack_context()
                    return
                if not self.handle_yield(yielded):
                    return
                yielded = None
        finally:
            self.running = False

    def handle_yield(self, yielded):
        # Lists containing YieldPoints require stack contexts;
        # other lists are handled in convert_yielded.
        if _contains_yieldpoint(yielded):
            yielded = multi(yielded)

        if isinstance(yielded, YieldPoint):
            # YieldPoints are too closely coupled to the Runner to go
            # through the generic convert_yielded mechanism.
            self.future = Future()

            def start_yield_point():
                try:
                    yielded.start(self)
                    if yielded.is_ready():
                        future_set_result_unless_cancelled(self.future, yielded.get_result())
                    else:
                        self.yield_point = yielded
                except Exception:
                    self.future = Future()
                    future_set_exc_info(self.future, sys.exc_info())

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
        else:
            try:
                self.future = convert_yielded(yielded)
            except BadYieldError:
                self.future = Future()
                future_set_exc_info(self.future, sys.exc_info())

        if self.future is moment:
            self.io_loop.add_callback(self.run)
            return False
        elif not self.future.done():
            def inner(f):
                # Break a reference cycle to speed GC.
                f = None # noqa
                self.run()
            self.io_loop.add_future(
                self.future, inner)
            return False
        return True

    def result_callback(self, key):
        return stack_context.wrap(_argument_adapter(
            functools.partial(self.set_result, key)))

    def handle_exception(self, typ, value, tb):
        if not self.running and not self.finished:
            self.future = Future()
            future_set_exc_info(self.future, (typ, value, tb))
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


# Convert Awaitables into Futures.
try:
    import asyncio
except ImportError:
    # Py2-compatible version for use with Cython.
    # Copied from PEP 380.
    @coroutine
    def _wrap_awaitable(x):
        if hasattr(x, '__await__'):
            _i = x.__await__()
        else:
            _i = iter(x)
        try:
            _y = next(_i)
        except StopIteration as _e:
            _r = _value_from_stopiteration(_e)
        else:
            while 1:
                try:
                    _s = yield _y
                except GeneratorExit as _e:
                    try:
                        _m = _i.close
                    except AttributeError:
                        pass
                    else:
                        _m()
                    raise _e
                except BaseException as _e:
                    _x = sys.exc_info()
                    try:
                        _m = _i.throw
                    except AttributeError:
                        raise _e
                    else:
                        try:
                            _y = _m(*_x)
                        except StopIteration as _e:
                            _r = _value_from_stopiteration(_e)
                            break
                else:
                    try:
                        if _s is None:
                            _y = next(_i)
                        else:
                            _y = _i.send(_s)
                    except StopIteration as _e:
                        _r = _value_from_stopiteration(_e)
                        break
        raise Return(_r)
else:
    _wrap_awaitable = asyncio.ensure_future


def convert_yielded(yielded):
    """Convert a yielded object into a `.Future`.

    The default implementation accepts lists, dictionaries, and Futures.

    If the `~functools.singledispatch` library is available, this function
    may be extended to support additional types. For example::

        @convert_yielded.register(asyncio.Future)
        def _(asyncio_future):
            return tornado.platform.asyncio.to_tornado_future(asyncio_future)

    .. versionadded:: 4.1
    """
    # Lists and dicts containing YieldPoints were handled earlier.
    if yielded is None or yielded is moment:
        return moment
    elif yielded is _null_future:
        return _null_future
    elif isinstance(yielded, (list, dict)):
        return multi(yielded)
    elif is_future(yielded):
        return yielded
    elif isawaitable(yielded):
        return _wrap_awaitable(yielded)
    else:
        raise BadYieldError("yielded unknown object %r" % (yielded,))


if singledispatch is not None:
    convert_yielded = singledispatch(convert_yielded)
