What's new in the next version of Tornado
=========================================

In progress
-----------

* `tornado.util.import_object` now works with top-level module names that
  do not contain a dot.
* `tornado.util.import_object` now consistently raises `ImportError`
  instead of `AttributeError` when it fails.
* The ``handlers`` list passed to the `tornado.web.Application` constructor
  and `~tornado.web.Application.add_handlers` methods can now contain
  lists in addition to tuples and `~tornado.web.URLSpec` objects.
* `tornado.httpclient.HTTPRequest` takes a new argument ``auth_mode``,
  which can be either ``basic`` or ``digest``.  Digest authentication
  is only supported with ``tornado.curl_httpclient``.
* `tornado.stack_context` has been rewritten and is now much faster.
* ``tornado.curl_httpclient`` no longer goes into an infinite loop when
  pycurl returns a negative timeout.
* `tornado.testing.AsyncTestCase.wait` now raises the correct exception
  when it has been modified by `tornado.stack_context`.
* `tornado.web.StaticFileHandler` now works on Windows when the client
  passes an ``If-Modified-Since`` timestamp before 1970.
* `tornado.httpserver.HTTPServer` handles malformed HTTP headers more
  gracefully.
* `tornado.auth.OAuthMixin` always sends ``oauth_version=1.0`` in its
  request as required by the spec.
* Many reference cycles have been broken up throughout the package,
  allowing for more efficient garbage collection on CPython.
* `tornado.testing.gen_test` can now be called as ``@gen_test(timeout=60)``
  to give some tests a longer timeout than others.
* The environment variable ``ASYNC_TEST_TIMEOUT`` can now be set to
  override the default timeout for `.AsyncTestCase.wait` and `.gen_test`.
* Some `.IOLoop` implementations (such as ``pyzmq``) accept objects
  other than integer file descriptors; these objects will now have
  their ``.close()`` method called when the ``IOLoop` is closed with
  ``all_fds=True``.
* `.HTTPServer` now supports lists of IPs in ``X-Forwarded-For``
  (it chooses the last, i.e. nearest one).
* Fixed an exception in `.WSGIContainer` when the connection is closed
  while output is being written.
* Silenced some log messages when connections are opened and immediately
  closed (i.e. port scans), or other situations related to closed
  connections.
* The default `.Resolver` implementation now works on Solaris.
* Memory is now reclaimed promptly on CPython when an HTTP request
  fails because it exceeded the maximum upload size.
* `tornado.options.define` with ``multiple=True`` now works on Python 3.
* `.Locale.format_date` now works on Python 3.
* Some internal names used by the template system have been changed;
  now all "reserved" names in templates start with ``_tt_``.
* The constructors of `.TCPServer` and `.HTTPServer` now take a
  ``max_buffer_size`` keyword argument.
* Fixed a bug in `.BaseIOStream.read_until_close` that would sometimes
  cause data to be passed to the final callback instead of the streaming
  callback.
* The `.IOStream` close callback is now run more reliably if there is
  an exception in ``_try_inline_read``.
* New method `.RequestHandler.log_exception` can be overridden to
  customize the logging behavior when an exception is uncaught.  Most
  apps that currently override ``_handle_request_exception`` can now
  use a combination of `.RequestHandler.log_exception` and
  `.write_error`.
* The ``TCP_NODELAY`` flag is now set when appropriate in `.HTTPServer`
  and ``simple_httpclient``.
* New methods `.BaseIOStream.set_nodelay` and
  `.WebSocketHandler.set_nodelay` can be used to set the
  ``TCP_NODELAY`` flag.
* The cache used in `.HTTPHeaders` will no longer grow without bound.
* Various small speedups: `.HTTPHeaders` case normalization, `.UIModule`
  proxy objects, precompile some regexes.
* `.bind_unused_port` now passes ``None`` instead of ``0`` as the port
  to ``getaddrinfo``, which works better with some unusual network
  configurations.
* `.RequestHandler.get_argument` now raises `.MissingArgumentError`
  (a subclass of `tornado.web.HTTPError`, which is what it raised previously)
  if the argument cannot be found.
* New function `.run_with_stack_context` facilitates the use of stack
  contexts with coroutines.
* `.url_escape` and `.url_unescape` have a new ``plus`` argument (defaulting
  to True for consistency with the previous behavior) which specifies
  whether they work like `urllib.parse.unquote` or `urllib.parse.unquote_plus`.
* `.Application.reverse_url` now uses `.url_escape` with ``plus=False``,
  i.e. spaces are encoded as ``%20`` instead of ``+``.
* Arguments extracted from the url path are now decoded with
  `.url_unescape` with ``plus=False``, so plus signs are left as-is
  instead of being turned into spaces.
* `.RequestHandler.send_error` will now only be called once per request,
  even if multiple exceptions are caught by the stack context.
* The `tornado.web.asynchronous` decorator is no longer necessary for
  methods that return a `.Future` (i.e. those that use the `.gen.coroutine`
  or `.return_future` decorators)
* `.RequestHandler.prepare` may now be asynchronous if it returns a
  `.Future`.  The `~tornado.web.asynchronous` decorator is not used with
  ``prepare``; one of the `.Future`-related decorators should be used instead.
* ``RequestHandler.current_user`` may now be assigned to normally.
* The `.HTTPServer` ``no_keep_alive`` option is now respected with
  HTTP 1.0 connections that explicitly pass ``Connection: keep-alive``.
* The ``Connection: keep-alive`` check for HTTP 1.0 connections is now
  case-insensitive.
* The stub handles left behind by `.IOLoop.remove_timeout` will now get
  cleaned up instead of waiting to expire.
* `.RequestHandler.redirect` no longer silently strips control characters
  and whitespace.  It is now an error to pass control characters, newlines
  or tabs.
