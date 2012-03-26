What's new in the next version of Tornado
=========================================

In progress
-----------

* Colored logging configuration in `tornado.options` is compatible with
  the upcoming release of Python 3.3.
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
