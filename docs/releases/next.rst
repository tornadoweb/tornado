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
* Tornado now depends on the `certifi <https://pypi.python.org/pypi/certifi>`_
  package instead of bundling its own copy of the Mozilla CA list. This will
  be installed automatically when using ``pip`` or ``easy_install``.


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
* New function `.with_timeout` wraps a `.Future` and raises an exception
  if it doesn't complete in a given amount of time.

`tornado.http1connection`
~~~~~~~~~~~~~~~~~~~~~~~~~

* New module contains the HTTP implementation shared by `tornado.httpserver`
  and ``tornado.simple_httpclient``.

`tornado.httpclient`
~~~~~~~~~~~~~~~~~~~~

* The command-line HTTP client (``python -m tornado.httpclient $URL``)
  now works on Python 3.

`tornado.httpserver`
~~~~~~~~~~~~~~~~~~~~

* ``tornado.httpserver.HTTPRequest`` has moved to
  `tornado.httputil.HTTPServerRequest`.
* HTTP implementation has been unified with ``tornado.simple_httpclient``
  in `tornado.http1connection`.
* Now supports ``Transfer-Encoding: chunked`` for request bodies.
* Now supports ``Content-Encoding: gzip`` for request bodies if ``gzip=True``
  is passed to the `.HTTPServer` constructor.
* The ``connection`` attribute of `.HTTPServerRequest` is now documented
  for public use; applications are expected to write their responses
  via the `.HTTPConnection` interface.
* The `.HTTPServerRequest.write` and `.HTTPServerRequest.finish` methods
  are now deprecated.
* `.HTTPServer` now supports `.HTTPServerConnectionDelegate` in addition to
  the old ``request_callback`` interface.  The delegate interface supports
  streaming of request bodies.
* `.HTTPServer` now detects the error of an application sending a
  ``Content-Length`` error that is inconsistent with the actual content.
* New constructor arguments ``max_header_size`` and ``max_body_size``
  allow separate limits to be set for different parts of the request.
  ``max_body_size`` is applied even in streaming mode.
* New constructor argument ``chunk_size`` can be used to limit the amount
  of data read into memory at one time per request.
* New constructor arguments ``idle_connection_timeout`` and ``body_timeout``
  allow time limits to be placed on the reading of requests.

`tornado.httputil`
~~~~~~~~~~~~~~~~~~

* `.HTTPServerRequest` was moved to this module from `tornado.httpserver`.
* New base classes `.HTTPConnection`, `.HTTPServerConnectionDelegate`,
  and `.HTTPMessageDelegate` define the interaction between applications
  and the HTTP implementation.


`tornado.ioloop`
~~~~~~~~~~~~~~~~

* `.IOLoop.add_handler` and related methods now accept file-like objects
  in addition to raw file descriptors.  Passing the objects is recommended
  (when possible) to avoid a garbage-collection-related problem in unit tests.
* New method `.IOLoop.clear_instance` makes it possible to uninstall the
  singleton instance.
* `.IOLoop.add_timeout` is now a bit more efficient.

`tornado.iostream`
~~~~~~~~~~~~~~~~~~

* The ``callback`` argument to most `.IOStream` methods is now optional.
  When called without a callback the method will return a `.Future`
  for use with coroutines.
* No longer gets confused when an ``IOError`` or ``OSError`` without
  an ``errno`` attribute is raised.
* `.BaseIOStream.read_bytes` now accepts a ``partial`` keyword argument,
  which can be used to return before the full amount has been read.
  This is a more coroutine-friendly alternative to ``streaming_callback``.
* `.BaseIOStream.read_until` and ``read_until_regex`` now acept a
  ``max_bytes`` keyword argument which will cause the request to fail if
  it cannot be satisfied from the given number of bytes.
* `.IOStream` no longer reads from the socket into memory if it does not
  need data to satisfy a pending read.  As a side effect, the close callback
  will not be run immediately if the other side closes the connection
  while there is unconsumed data in the buffer.
* The default ``chunk_size`` has been increased to 64KB (from 4KB)

`tornado.netutil`
~~~~~~~~~~~~~~~~~

* When `.bind_sockets` chooses a port automatically, it will now use
  the same port for IPv4 and IPv6.
* TLS compression is now disabled by default on Python 3.3 and higher
  (it is not possible to change this option in older versions.

`tornado.options`
~~~~~~~~~~~~~~~~~

* It is now possible to disable the default logging configuration
  by setting ``options.logging`` to ``None`` instead of the string "none".

`tornado.platform.asyncio`
~~~~~~~~~~~~~~~~~~~~~~~~~~

* Now works on Python 2.6.

``tornado.simple_httpclient``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Improved default cipher suite selection (Python 2.7+).
* HTTP implementation has been unified with ``tornado.httpserver``
  in `tornado.http1connection`
* Streaming request bodies are now supported via the ``body_producer``
  keyword argument to `tornado.httpclient.HTTPRequest`.
* The ``expect_100_continue`` keyword argument to
  `tornado.httpclient.HTTPRequest` allows the use of the HTTP ``Expect:
  100-continue`` feature.

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
* Fixed the test suite when ``unittest2`` is installed on Python 3.

`tornado.web`
~~~~~~~~~~~~~

* When gzip support is enabled, all ``text/*`` mime types will be compressed,
  not just those on a whitelist.
* `.Application` now implements the `.HTTPMessageDelegate` interface.
* It is now possible to support streaming request bodies with the
  `.stream_request_body` decorator and the new `.RequestHandler.data_received`
  method.
* `.RequestHandler.flush` now returns a `.Future` if no callback is given.

`tornado.websocket`
~~~~~~~~~~~~~~~~~~~

* `.WebSocketHandler.close` and `.WebSocketClientConnection.close` now
  support ``code`` and ``reason`` arguments to send a status code and
  message to the other side of the connection when closing.  Both classes
  also have ``close_code`` and ``close_reason`` attributes to receive these
  values when the other side closes.
* The C speedup module now builds correctly with MSVC, and can support
  messages larger than 2GB on 64-bit systems.
* The fallback mechanism for detecting a missing C compiler now
  works correctly on Mac OS X.
* Arguments to `.WebSocketHandler.open` are now decoded in the same way
  as arguments to `.RequestHandler.get` and similar methods.

`tornado.wsgi`
~~~~~~~~~~~~~~

* New class `.WSGIAdapter` supports running a Tornado `.Application` on
  a WSGI server in a way that is more compatible with Tornado's non-WSGI
  `.HTTPServer`.  `.WSGIApplication` is deprecated in favor of using
  `.WSGIAdapter` with a regular `.Application`.
* `.WSGIAdapter` now supports gzipped output.
