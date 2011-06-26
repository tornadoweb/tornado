What's new in the next release of Tornado
=========================================

In progress
-----------

New features
~~~~~~~~~~~~

* New method `tornado.iostream.IOStream.read_until_close`
* `tornado.autoreload` has a new command-line interface which can be used
  to wrap any script.  This replaces the ``--autoreload`` argument to
  `tornado.testing.main` and is more robust against syntax errors.
* `tornado.autoreload.watch` can be used to watch files other than
  the sources of imported modules.
* `tornado.ioloop.IOLoop` and `tornado.httpclient.HTTPClient` now have
  ``close()`` methods that should be used in applications that create
  and destroy many of these objects.

Bug fixes
~~~~~~~~~

* `HTTPServer`: fixed exception at startup when ``socket.AI_ADDRCONFIG`` is
  not available, as on Windows XP
* `tornado.websocket`: now works on Python 3
* `SimpleAsyncHTTPClient`: now works with HTTP 1.0 servers that don't send
  a Content-Length header
