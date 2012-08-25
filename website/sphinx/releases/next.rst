What's new in the next release of Tornado
=========================================

In progress
-----------

* New class `tornado.testing.AsyncHTTPSTestCase` is like `AsyncHTTPTestCase`.
  but enables SSL for the testing server (by default using a self-signed
  testing certificate).
* Fixed Python 3 bugs in `tornado.auth`, `tornado.locale`, and `tornado.wsgi`.
* `tornado.locale` module now works on Python 3.
* `RequestHandler.add_header` now works with `WSGIApplication`.
* Fixed some Python 3 bugs in `tornado.wsgi` module.
* ``{% break %}`` and ``{% continue %}`` can now be used in templates.
* The logging configuration used in `tornado.options` is now more tolerant
  of non-ascii byte strings.
* Improved error handling in `SSLIOStream` and SSL-enabled `TCPServer`.
* On Windows, `TCPServer` uses `SO_EXCLUSIVEADDRUSER` instead of `SO_REUSEADDR`.
* `IOLoop.add_handler` cannot be called more than once with the same file
  descriptor.  This was always true for ``epoll``, but now the other
  implementations enforce it too.
* `tornado.testing.main` now accepts additional keyword arguments and forwards
  them to `unittest.main`.
* `RequestHandler.get_secure_cookie` now handles a potential error case.
* Fixed a bug introduced in 2.3 that would cause `IOStream` close callbacks
  to not run if there were pending reads.
* `RequestHandler.__init__` now calls ``super().__init__`` to ensure that
  all constructors are called when multiple inheritance is used.
* `OAuthMixin` now accepts ``"oob"`` as a ``callback_uri``.
* `tornado.platform.twisted` shutdown sequence is now more compatible.
* Removed ``max_simultaneous_connections`` argument from `tornado.httpclient`
  (both implementations).  This argument hasn't been useful for some time
  (if you were using it you probably want ``max_clients`` instead)
* `tornado.simple_httpclient` now accepts and ignores HTTP 1xx status
  responses.
* `SSLIOStream.get_ssl_certificate` now has a ``binary_form`` argument
  which is passed to ``SSLSocket.getpeercert``.
* `SSLIOStream.write` can now be called while the connection is in progress,
  same as non-SSL `IOStream`.
* tornado.util.GzipDecompressor, tornado.httputil.parse_body_arguments (TODO
  are these public?)
