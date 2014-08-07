What's new in the next release of Tornado
=========================================

In progress
-----------

* `~tornado.options.parse_config_file` now always decodes the config
  file as utf8 on Python 3.
* ``tornado.curl_httpclient`` now supports request bodies for ``PATCH``
  and custom methods.
* `.RequestHandler.send_error` now supports a ``reason`` keyword
  argument, similar to `tornado.web.HTTPError`.
* ``tornado.curl_httpclient`` now supports resubmitting bodies after
  following redirects for methods other than ``POST``.
* The build will now fall back to pure-python mode if the C extension
  fails to build for any reason (previously it would fall back for some
  errors but not others).
* The ``context`` argument to `.HTTPServerRequest` is now optional,
  and if a context is supplied the ``remote_ip`` attribute is also optional.
* `.IOLoop.call_at` and `.IOLoop.call_later` now always return
  a timeout handle for use with `.IOLoop.remove_timeout`.
* `.HTTPServer` now tolerates extra newlines which are sometimes inserted
  between requests on keep-alive connections.
* `.HTTPServer` can now use keep-alive connections after a request
  with a chunked body.
* `.SSLIOStream` will no longer consume 100% CPU after certain error conditions.
* `.SSLIOStream` no longer logs ``EBADF`` errors during the handshake as they
  can result from nmap scans in certain modes.
* The `tornado.websocket` module now supports compression via the
  "permessage-deflate" extension.  Override
  `.WebSocketHandler.get_compression_options` to enable on the server
  side, and use the ``compression_options`` keyword argument to
  `.websocket_connect` on the client side.
* If the callback of a `.PeriodicCallback` returns a `.Future`, any error
  raised in that future will now be logged (similar to the behavior of
  `.IOLoop.add_callback`).
