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
  closed (i.e. port scans).
* The default `.Resolver` implementation now works on Solaris.
* Memory is now reclaimed promptly on CPython when an HTTP request
  fails because it exceeded the maximum upload size.
* `tornado.options.define` with ``multiple=True`` now works on Python 3.
* `.Locale.format_date` now works on Python 3.
* Some internal names used by the template system have been changed;
  now all "reserved" names in templates start with ``_tt_``.
