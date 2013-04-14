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
* Some reference cycles have been broken up (in `tornado.web.RequestHandler`
  and `tornado.websocket.WebSocketHandler`), allowing for more efficient
  garbage collection on CPython.
