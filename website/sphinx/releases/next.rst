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
