What's new in the next release of Tornado
=========================================

In progress
-----------

Backwards-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Support for secure cookies written by pre-1.0 releases of Tornado has
  been removed.  The `RequestHandler.get_secure_cookie` method no longer
  takes an ``include_name`` parameter.
* The ``debug`` application setting now causes stack traces to be displayed
  in the browser on uncaught exceptions.  Since this may leak sensitive
  information, debug mode is not recommended for public-facing servers.

New features
~~~~~~~~~~~~

* New method `tornado.iostream.IOStream.read_until_close`
* `tornado.autoreload` has a new command-line interface which can be used
  to wrap any script.  This replaces the ``--autoreload`` argument to
  `tornado.testing.main` and is more robust against syntax errors.
* `tornado.autoreload.watch` can be used to watch files other than
  the sources of imported modules.
* `tornado.web.RequestHandler.get_secure_cookie` now has a ``max_age_days``
  parameter to allow applications to override the default one-month expiration.
* `tornado.ioloop.IOLoop` and `tornado.httpclient.HTTPClient` now have
  ``close()`` methods that should be used in applications that create
  and destroy many of these objects.
* `tornado.simple_httpclient` now supports client SSL certificates with the
  ``client_key`` and ``client_cert`` parameters to
  `tornado.httpclient.HTTPRequest`
* `tornado.httpserver.HTTPServer.bind` now takes a backlog argument with the
  same meaning as ``socket.listen``.
* In `tornado.web.Application`, handlers may be specified by
  (fully-qualified) name instead of importing and passing the class object
  itself.
* `tornado.web.RequestHandler.set_default_headers` may be overridden to set
  headers in a way that does not get reset during error handling.
* `tornado.web.RequestHandler.write_error` replaces ``get_error_html`` as the
  preferred way to generate custom error pages (``get_error_html`` is still
  supported, but deprecated)
* Multi-process mode has been improved, and can now restart crashed child
  processes.  A new entry point has been added at 
  `tornado.process.fork_processes`, although
  `tornado.httpserver.HTTPServer.start` is still supported.
* To facilitate some advanced multi-process scenarios, ``HTTPServer`` has a
  new method ``add_sockets``, and socket-opening code is available separately
  as `tornado.netutil.bind_sockets`.
* Windows support has been improved.  Windows is still not an officially
  supported platform, but the test suite now passes.
* `~tornado.iostream.IOStream` performance has been improved, especially for
  small synchronous requests.
* `~tornado.httpserver.HTTPServer` can now be run on a unix socket as well
  as TCP.
* `~tornado.web.StaticFileHandler` subclasses can now override 
  ``get_cache_time`` to customize cache control behavior.
* `tornado.websocket` now supports the latest ("hybi-10") version of the
  protocol (the old version, "hixie-76" is still supported; the correct
  version is detected automatically).
* New module `tornado.platform.twisted` contains a bridge between the
  Tornado IOLoop and the Twisted Reactor, allowing code written for Twisted
  to be run on Tornado.
* `RequestHandler.flush` can now take a callback for flow control.
* `SimpleAsyncHTTPClient` now takes a maximum buffer size, to allow reading
  files larger than 100MB
* `IOLoop.install` can now be used to use a custom subclass of IOLoop
  as the singleton without monkey-patching.
* `RequestHandler.add_header` can now be used to set a header that can
  appear multiple times in the response.
* `IOLoop.add_timeout` now accepts `datetime.timedelta` objects in addition
  to absolute timestamps.
* It is now possible to use a custom subclass of ``StaticFileHandler``
  with the ``static_handler_class`` application setting, and this subclass
  can override the behavior of the ``static_url`` method.

Bug fixes
~~~~~~~~~

* `HTTPServer`: fixed exception at startup when ``socket.AI_ADDRCONFIG`` is
  not available, as on Windows XP
* `tornado.websocket`: now works on Python 3
* `SimpleAsyncHTTPClient`: now works with HTTP 1.0 servers that don't send
  a Content-Length header
* `tornado.iostream.IOStream` should now always call the close callback
  instead of the connect callback on a connection error.
* The ``allow_nonstandard_methods`` flag on HTTP client requests now
  permits methods other than ``POST`` and ``PUT`` to contain bodies.
* `tornado.locale.load_translations` now accepts any properly-formatted
  locale name, not just those in the predefined ``LOCALE_NAMES`` list.
* Uploading files whose names contain special characters will now work.
* Cookie values containing special characters are now properly quoted
  and unquoted.
* Multi-line headers are now supported.
* The `IOStream` close callback will no longer be called while there
  are pending read callbacks that can be satisfied with buffered data.
* Fixed file descriptor leaks and multiple callback invocations in
  `SimpleAsyncHTTPClient`
* Repeated Content-Length headers (which may be added by certain proxies)
  are now supported in `HTTPServer`.
* Unicode string literals now work in template expressions.
* `~tornado.ioloop.PeriodicCallback` now sticks to the specified period
  instead of creeping later due to accumulated errors.
* The template ``{% module %}`` directive now works even if applications
  use a template variable named ``modules``.
* `~tornado.auth.OpenIDMixin` now uses the correct realm when the
  callback URI is on a different domain.
