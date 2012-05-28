What's new in the next version of Tornado
=========================================

In progress
-----------

* `tornado.simple_httpclient` is better about closing its sockets
  instead of leaving them for garbage collection.
* Repeated calls to `RequestHandler.set_cookie` with the same name now
  overwrite the previous cookie instead of producing additional copies.
* `tornado.simple_httpclient` correctly verifies SSL certificates for
  URLs containing IPv6 literals (This bug affected Python 2.5 and 2.6).
* Fixed a bug on python versions before 2.6.5 when `URLSpec` regexes
  are constructed from unicode strings and keyword arguments are extracted.
* `tornado.curl_httpclient` now supports client SSL certificates (using
  the same ``client_cert`` and ``client_key`` arguments as
  `tornado.simple_httpclient`)
* `tornado.httpclient.HTTPClient` now supports the same constructor
  keyword arguments as `AsyncHTTPClient`.
* `tornado.locale.get_supported_locales` no longer takes a meaningless
  ``cls`` argument.
* The ``reverse_url`` function in the template namespace now comes from
  the `RequestHandler` rather than the `Application`.  (Unless overridden,
  `RequestHandler.reverse_url` is just an alias for the `Application`
  method).
* The ``Etag`` header is now returned on 304 responses to an ``If-None-Match``
  request, improving compatibility with some caches.
* `tornado.simple_httpclient` no longer includes basic auth credentials
  in the ``Host`` header when those credentials are extracted from the URL.
* `tornado.testing.AsyncTestCase.wait` now resets its timeout on each call.
* `tornado.simple_httpclient` no longer modifies the caller-supplied header
  dictionary, which caused problems when following redirects.
* `tornado.web.addslash` and ``removeslash`` decorators now send permanent
  redirects (301) instead of temporary (302).
* `tornado.wsgi.WSGIApplication` now parses arguments correctly on Python 3.
* `tornado.auth.FacebookGraphMixin` no longer sends ``post_args`` redundantly
  in the url.
* `tornado.iostream.IOStream.read_until` and ``read_until_regex`` are much
  faster with large input.
* `tornado.simple_httpclient` now supports the ``OPTIONS`` and ``PATCH``
  HTTP methods.
* `tornado.web.RequestHandler` now supports the ``PATCH`` HTTP method.
  Note that this means any existing methods named ``patch`` in
  ``RequestHandler`` subclasses will need to be renamed.
* `tornado.options` options with ``multiple=True`` that are set more than
  once now overwrite rather than append.  This makes it possible to override
  values set in `parse_config_file` with `parse_command_line`.
* `tornado.options` ``--help`` output is now prettier.
* Templates now support ``else`` clauses in
  ``try``/``except``/``finally``/``else`` blocks.
* Template files containing non-ASCII (utf8) characters now work on Python 3
  regardless of the locale environment variables.
* `RequestHandler.flush` now invokes its callback whether there was any data
  to flush or not.
* `IOLoop.instance()` is now thread-safe.
* `tornado.options.options` now supports attribute assignment.
* The ``max_clients`` keyword argument to `AsyncHTTPClient.configure` now works.
* The ``extra_params`` argument to `tornado.escape.linkify` may now be
  a callable, to allow parameters to be chosen separately for each link.
* `HTTPServer` now works correctly with paths starting with ``//``
* Exception handling on Python 3 has been improved; previously some exceptions
  such as `UnicodeDecodeError` would generate `TypeErrors`
* `tornado.web.OutputTransform.transform_first_chunk` now takes and returns
  a status code in addition to the headers and chunk.  This is a
  backwards-incompatible change to an interface that was never technically
  private, but was not included in the documentation and does not appear
  to have been used outside Tornado itself.
* `tornado.web` will no longer produce responses with status code 304
  that also have entity headers such as ``Content-Length``.
* `StackContext` instances now have a deactivation callback that can be
  used to prevent further propagation.
* `tornado.gen` no longer leaks `StackContexts` when a ``@gen.engine`` wrapped
  function is called repeatedly.
* Extra data at the end of multipart form bodies is now ignored, which fixes
  a compatibility problem with an iOS HTTP client library.
* `IOStream.write` performs better when given very large strings.
* `HTTPHeaders.copy` (inherited from `dict.copy`) now works correctly.
* `HTTPConnection.address` is now always the socket address, even for non-IP
  sockets.  `HTTPRequest.remote_ip` is still always an IP-style address
  (fake data is used for non-IP sockets)
* `IOStream` now has an ``error`` attribute that can be used to determine
  why a socket was closed.
