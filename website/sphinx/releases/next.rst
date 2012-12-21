What's new in the next release of Tornado
=========================================

In progress
-----------

* The Tornado test suite now requires ``unittest2`` when run on Python 2.5
  or 2.6.
* `tornado.testing.AsyncTestCase` and friends now extend ``unittest2.TestCase``
  when it is available (and continue to use the standard ``unittest`` module
  when ``unittest2`` is not available)
* `tornado.netutil.bind_sockets` no longer sets ``AI_ADDRCONFIG``; this will
  cause it to bind to both ipv4 and ipv6 more often than before.
* `tornado.netutil.bind_sockets` has a new ``flags`` argument that can
  be used to pass additional flags to ``getaddrinfo``.
* Tornado no longer logs to the root logger.  Details on the new logging
  scheme can be found under the `tornado.log` module.  Note that in some
  cases this will require that you add an explicit logging configuration
  in order to see any output (perhaps just calling ``logging.basicConfig()``),
  although both `IOLoop.start()` and `tornado.options.parse_command_line`
  will do this for you.
* Errors while rendering templates no longer log the generated code,
  since the enhanced stack traces (from version 2.1) should make this
  unnecessary.
* `tornado.testing.ExpectLog` can be used as a finer-grained alternative
  to `tornado.testing.LogTrapTestCase`
* The command-line interface to `tornado.testing.main` now supports
  additional arguments from the underlying `unittest` module:
  ``verbose``, ``quiet``, ``failfast``, ``catch``, ``buffer``.
* Empty HTTP request arguments are no longer ignored.  This applies to
  ``HTTPRequest.arguments`` and ``RequestHandler.get_argument[s]``
  in WSGI and non-WSGI modes.
* New function `tornado.testing.bind_unused_port` both chooses a port
  and binds a socket to it, so there is no risk of another process
  using the same port.  ``get_unused_port`` is now deprecated.
* The `tornado.database` module has been removed.  It is now available
  as a separate package, `torndb <https://github.com/bdarnell/torndb>`_
* New class `tornado.iostream.PipeIOStream` provides the IOStream
  interface on pipe file descriptors.
* Much of `IOStream` has been refactored into a separate class
  `BaseIOStream`.
* New class `tornado.process.Subprocess` wraps `subprocess.Popen` with
  `PipeIOStream` access to the child's file descriptors.
* `IOLoop` now uses `signal.set_wakeup_fd` where available (Python 2.6+
  on Unix) to avoid a race condition that could result in Python signal
  handlers being delayed.
* `WebSocketHandler` has new methods `ping` and `on_pong` to send pings
  to the browser (not supported on the ``draft76`` protocol)
* The ``Date`` HTTP header is now set by default on all responses.
* Several methods related to HTTP status codes now take a ``reason`` keyword
  argument to specify an alternate "reason" string (i.e. the "Not Found" in
  "HTTP/1.1 404 Not Found").  It is now possible to set status codes other
  than those defined in the spec, as long as a reason string is given.
* New method `IOLoop.add_callback_from_signal` is safe to use in a signal
  handler (the regular `add_callback` method may deadlock).
* `stack_context.wrap` now runs the wrapped callback in a more consistent
  environment by recreating contexts even if they already exist on the
  stack.
* Fixed a bug in which stack contexts could leak from one callback
  chain to another.
* `tornado.autoreload` is now more reliable when there are errors at import
  time.
* New optional dependency on `concurrent.futures` to provide better support
  for working with threads.  `concurrent.futures` is in the standard library
  for Python 3.2+, and can be installed on older versions with
  ``pip install futures``.
* New module `tornado.concurrent` contains code to support working with
  `concurrent.futures`, or to emulate future-based interface when that module
  is not available.
* New method `IOLoop.add_future` to run a callback on the IOLoop when
  an asynchronous ``Future`` finishes.
* New class `tornado.netutil.Resolver` provides an asynchronous
  interface to `socket.getaddrinfo`.  The interface is based on (but
  does not require) `concurrent.futures`.  When used with
  `concurrent.futures.ThreadPoolExecutor`, it allows for DNS
  resolution without blocking the main thread.
* `SimpleAsyncHTTPClient` now takes a ``resolver`` keyword argument (which
  may be passed to either the constructor or ``configure``), to allow it to
  use the new non-blocking `tornado.netutil.Resolver`.
* Functions using `gen.engine` may now yield ``Future`` objects.
* New function `IOLoop.current` returns the ``IOLoop`` that is running
  on the current thread (as opposed to `IOLoop.instance`, which returns a
  specific thread's (usually the main thread's) IOLoop).
* `tornado.options.parse_config_file` now configures logging automatically
  by default, in the same way that `parse_command_line` does.
* New function `tornado.options.add_parse_callback` schedules a callback
  to be run after the command line or config file has been parsed.  The
  keyword argument ``final=False`` can be used on either parsing function
  to supress these callbacks.
* Function `tornado.options.enable_pretty_logging` has been moved to the
  `tornado.log` module.
* `tornado.options.define` now takes a ``callback`` argument.  This callback
  will be run with the new value whenever the option is changed.  This is
  especially useful for options that set other options, such as by reading
  from a config file.
* `tornado.option.parse_command_line` ``--help`` output now goes to ``stderr``
  rather than ``stdout``.
* The class underlying the functions in `tornado.options` is now public
  (`tornado.options.OptionParser`).  This can be used to create multiple
  independent option sets, such as for subcommands.
* `tornado.options.options` is no longer a subclass of `dict`; attribute-style
  access is now required.
* The ``max_clients`` argument to `AsyncHTTPClient` is now a keyword-only
  argument.
* Keyword arguments to `AsyncHTTPClient.configure` are no longer used
  when instantiating an implementation subclass directly.
* The `IOLoop` poller implementations (``select``, ``epoll``, ``kqueue``)
  are now available as distinct subclasses of `IOLoop`.  Instantiating
  `IOLoop` will continue to automatically choose the best available
  implementation.
* `IOLoop` now has a static ``configure`` method like the one on
  `AsyncHTTPClient`, which can be used to select an IOLoop implementation
  other than the default.
* The deprecated ``--autoreload`` option of `tornado.testing.main` has
  been removed.  Use ``python -m tornado.autoreload`` as a prefix command
  instead.
* The ``--httpclient`` option of `tornado.testing.main` has been moved
  to `tornado.test.runtests` so as not to pollute the application
  option namespace.  The `tornado.options` module's new callback
  support now makes it easy to add options from a wrapper script
  instead of putting all possible options in `tornado.testing.main`.
* The `IOLoop` constructor has a new keyword argument ``time_func``,
  which can be used to set the time function used when scheduling callbacks.
  This is most useful with the `time.monotonic()` function, introduced
  in Python 3.3 and backported to older versions via the ``monotime``
  module.  Using a monotonic clock here avoids problems when the system
  clock is changed.
* New function `IOLoop.time` returns the current time according to the
  IOLoop.  To use the new monotonic clock functionality, all calls to
  `IOLoop.add_timeout` must be either pass a `datetime.timedelta` or
  a time relative to `IOLoop.time`, not `time.time`.  (`time.time` will
  continue to work only as long as the IOLoop's ``time_func`` argument
  is not used).
* `IOStream` now raises a new exception
  `tornado.iostream.StreamClosedError` when you attempt to read or
  write after the stream has been closed (by either side).
* `IOStream` now simply closes the connection when it gets an
  ``ECONNRESET`` error, rather than logging it as an error.
* `HTTPServer` no longer logs an error when it is unable to read a second
  request from an HTTP 1.1 keep-alive connection.
* The ``{% apply %}`` directive now works properly with functions that return
  both unicode strings and byte strings (previously only byte strings were
  supported).
* Calling `tornado.autoreload.start` (or creating an `Application` with
  ``debug=True``) twice on the same `IOLoop` now does nothing (instead of
  creating multiple periodic callbacks).  Starting autoreload on
  more than one `IOLoop` in the same process now logs a warning.
* Method `IOLoop.running()` has been removed.
* `IOLoop` has been refactored to better support subclassing.
* New class `tornado.platform.twisted.TwistedIOLoop` allows Tornado
  code to be run on the Twisted reactor (as opposed to the existing
  `TornadoReactor`, which bridges the gap in the other direction).
* `AsyncHTTPTestCase` no longer calls `AsyncHTTPClient.close` for tests
  that use the singletion `IOLoop.instance`.
* When following redirects, `SimpleAsyncHTTPClient` now treats a 302
  response code the same as a 303.  This is contrary to the HTTP spec
  but consistent with all browsers and other major HTTP clients
  (including `CurlAsyncHTTPClient`).
* The `tornado.auth` mixin classes now define a method
  ``get_auth_http_client``, which can be overridden to use a non-default
  `AsyncHTTPClient` instance (e.g. to use a different `IOLoop`)
* ``Etag``/``If-None-Match`` requests now work with `StaticFileHandler`.
* `StaticFileHandler` no longer sets ``Cache-Control: public`` unnecessarily.
* The behavior of ``header_callback`` with `SimpleAsyncHTTPClient` has
  changed and is now the same as that of `CurlAsyncHTTPClient`.  The
  header callback now receives the first line of the response (e.g.
  ``HTTP/1.0 200 OK``) and the final empty line.
* Secondary `AsyncHTTPClient` callbacks (``streaming_callback``,
  ``header_callback``, and ``prepare_curl_callback``) now respect
  `StackContext`.
* `AsyncHTTPClient.configure` and all `AsyncHTTPClient` constructors
  now take a ``defaults`` keyword argument.  This argument should be a
  dictionary, and its values will be used in place of corresponding
  attributes of `HTTPRequest` that are not set.
* All unset attributes of `tornado.httpclient.HTTPRequest` are now ``None``.
  The default values of some attributes (``connect_timeout``,
  ``request_timeout``, ``follow_redirects``, ``max_redirects``,
  ``use_gzip``, ``proxy_password``, ``allow_nonstandard_methods``,
  and ``validate_cert`` have been moved from `HTTPRequest` to the
  client implementations.
* `simple_httpclient` now accepts responses with a 304 status code that
  include a ``Content-Length`` header.
* `HTTPServer` now takes a ``protocol`` keyword argument which can be set
  to ``https`` if the server is behind an SSL-decoding proxy that does not
  set any supported X-headers.
* `tornado.web.ErrorHandler` no longer requires XSRF tokens on ``POST``
  requests, so posts to an unknown url will always return 404 instead of
  complaining about XSRF tokens.
* `tornado.options.options` (and `OptionParser` instances generally) now
  have a `mockable()` method that returns a wrapper object compatible with
  `mock.patch`.
* `tornado.web.RequestHandler` has new attributes ``path_args`` and
  ``path_kwargs``, which contain the positional and keyword arguments
  that are passed to the ``get``/``post``/etc method.  These attributes
  are set before those methods are called, so they are available during
  ``prepare()``
* `IOLoop.add_callback` and `add_callback_from_signal` now take
  ``*args, **kwargs`` to pass along to the callback.
* When gzip is enabled in a `tornado.web.Application`, appropriate
  ``Vary: Accept-Encoding`` headers are now sent.
* Fixed a bug in which `SimpleAsyncHTTPClient` callbacks were being run in the
  client's ``stack_context``.
