What's new in the next version of Tornado
=========================================

In Progress
-----------

* `.WSGIContainer` now calls the iterable's ``close()`` method even if
  an error is raised, in compliance with the spec.
* Fixed an incorrect error message when handler methods return a value
  other than None or a Future.
* `.xhtml_escape` now escapes apostrophes as well.
* `.Subprocess` no longer leaks file descriptors if `subprocess.Popen` fails.
* `.IOLoop` now frees callback objects earlier, reducing memory usage
  while idle.
* `.FacebookGraphMixin` has been updated to use the current Facebook login
  URL, which saves a redirect.
* `.IOStream` now recognizes ``ECONNABORTED`` error codes in more places
  (which was mainly an issue on Windows).
* `.IOStream` now frees memory earlier if a connection is closed while
  there is data in the write buffer.
* `.StaticFileHandler` no longer fails if the client requests a ``Range`` that
  is larger than the entire file (Facebook has a crawler that does this).
* `.PipeIOStream` now handles ``EAGAIN`` error codes correctly.
* `.SSLIOStream` now initiates the SSL handshake automatically without
  waiting for the application to try and read or write to the connection.
* `.IOLoop` now uses `~.IOLoop.handle_callback_exception` consistently for
  error logging.
* `.RequestHandler.on_connection_close` now works correctly on subsequent
  requests of a keep-alive connection.
* `.RequestHandler.clear_all_cookies` now accepts ``domain`` and ``path``
  arguments, just like `~.RequestHandler.clear_cookie`.
* The embedded ``ca-certificats.crt`` file has been updated with the current
  Mozilla CA list.
* `.GoogleOAuth2Mixin` has been added so that Google's OAuth2 only apps are
  able to get a context without OpenID (which uses OAuth 1).
* `.WebSocketHandler.write_message` now raises `.WebSocketClosedError` instead
  of `AttributeError` when the connection has been closed.
* ``simple_httpclient`` now applies the ``connect_timeout`` to requests
  that are queued and have not yet started.
* `.is_valid_ip` (and therefore ``HTTPRequest.remote_ip``) now rejects
  empty strings.
* `.websocket_connect` now accepts preconstructed ``HTTPRequest`` objects.
* Fix a bug with `.WebSocketHandler` when used with some proxies that
  unconditionally modify the ``Connection`` header.
* New application setting ``default_handler_class`` can be used to easily
  set up custom 404 pages.
* Fix some error messages for unix sockets (and other non-IP sockets)
* New application settings ``autoreload``, ``compiled_template_cache``,
  ``static_hash_cache``, and ``serve_traceback`` can be used to control
  individual aspects of debug mode.
* New methods `.RequestHandler.get_query_argument` and
  `.RequestHandler.get_body_argument` and new attributes
  `.HTTPRequest.query_arguments` and `.HTTPRequest.body_arguments` allow access
  to arguments without intermingling those from the query string with those
  from the request body.
* `.websocket_connect` now returns an error immediately for refused connections
  instead of waiting for the timeout.
* Exceptions will no longer be logged twice when using both ``@asynchronous``
  and ``@gen.coroutine``
* Swallow a spurious exception from ``set_nodelay`` when a connection
  has been reset.
* Coroutines may now yield dicts in addition to lists to wait for
  multiple tasks in parallel.
* Fix an error from `tornado.log.enable_pretty_logging` when
  `sys.stderr` does not have an ``isatty`` method.
* `.WebSocketClientConnection` now has a ``close`` method.
* It is now possible to specify handlers by name when using the `.URLSpec`
  class.
* On Python 2.6, ``simple_httpclient`` now uses TLSv1 instead of SSLv3.
* Added `.GoogleOAuth2Mixin` support authentication to Google services
  with OAuth 2 instead of OpenID and OAuth 1.
* `.Application` now accepts 4-tuples to specify the ``name`` parameter
  (which previously required constructing a `.URLSpec` object instead of
  a tuple).
* ``simple_httpclient`` now enforces the connect timeout during DNS resolution.
* Tornado now depends on the `backports.ssl_match_hostname
  <https://pypi.python.org/pypi/backports.ssl_match_hostname>`_ when
  running on Python 2.  This will be installed automatically when using ``pip``
  or ``easy_install``
* Tornado now includes an optional C extension module, which greatly improves
  performance of websockets.  This extension will be built automatically
  if a C compiler is found at install time.
* The `tornado.platform.asyncio` module provides integration with the
  ``asyncio`` module introduced in Python 3.4.
* Malformed ``x-www-form-urlencoded`` request bodies will now log a warning
  and continue instead of causing the request to fail (similar to the existing
  handling of malformed ``multipart/form-data`` bodies.  This is done mainly
  because some libraries send this content type by default even when the data
  is not form-encoded.
