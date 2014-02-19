What's new in the next version of Tornado
=========================================

In progress
-----------

Backwards-compatibility notes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Authors of alternative `.IOLoop` implementations should see the changes
  to `.IOLoop.add_handler` in this release.
* `tornado.concurrent.Future` is no longer thread-safe; use
  `concurrent.futures.Future` when thread-safety is needed.

`tornado.concurrent`
~~~~~~~~~~~~~~~~~~~~

* `tornado.concurrent.Future` is now always thread-unsafe (previously
  it would be thread-safe if the `concurrent.futures` package was available).
  This improves performance and provides more consistent semantics.
  The parts of Tornado that accept Futures will accept both Tornado's
  thread-unsafe Futures and the thread-safe `concurrent.futures.Future`.
* `tornado.concurrent.Future` now includes all the functionality
  of the old ``TracebackFuture`` class.  ``TracebackFuture`` is now
  simply an alias for ``Future``.

`tornado.gen`
~~~~~~~~~~~~~

* The internals of the `tornado.gen` module have been rewritten to
  improve performance when using ``Futures``, at the expense of some
  performance degradation for the older `.YieldPoint` interfaces.
* Performance of coroutines has been improved.
* Coroutines no longer generate ``StackContexts`` by default, but they
  will be created on demand when needed.

`tornado.ioloop`
~~~~~~~~~~~~~~~~

* `.IOLoop.add_handler` and related methods now accept file-like objects
  in addition to raw file descriptors.  Passing the objects is recommended
  (when possible) to avoid a garbage-collection-related problem in unit tests.

`tornado.iostream`
~~~~~~~~~~~~~~~~~~

* The ``callback`` argument to most `.IOStream` methods is now optional.
  When called without a callback the method will return a `.Future`
  for use with coroutines.

`tornado.options`
~~~~~~~~~~~~~~~~~

* It is now possible to disable the default logging configuration
  by setting ``options.logging`` to ``None`` instead of the string "none".

`tornado.platform.asyncio`
~~~~~~~~~~~~~~~~~~~~~~~~~~

* Now works on Python 2.6.

`tornado.stack_context`
~~~~~~~~~~~~~~~~~~~~~~~

* The stack context system now has less performance overhead when no
  stack contexts are active.

`tornado.testing`
~~~~~~~~~~~~~~~~~

* `.AsyncTestCase` now attempts to detect test methods that are generators
  but were not run with ``@gen_test`` or any similar decorator (this would
  previously result in the test silently being skipped).
* Better stack traces are now displayed when a test times out.

`tornado.web`
~~~~~~~~~~~~~

* When gzip support is enabled, all ``text/*`` mime types will be compressed,
  not just those on a whitelist.

`tornado.websocket`
~~~~~~~~~~~~~~~~~~~

* `.WebSocketHandler.close` and `.WebSocketClientConnection.close` now
  support ``code`` and ``reason`` arguments to send a status code and
  message to the other side of the connection when closing.  Both classes
  also have ``close_code`` and ``close_reason`` attributes to receive these
  values when the other side closes.
* The C speedup module now builds correctly with MSVC, and can support
  messages larger than 2GB on 64-bit systems.
