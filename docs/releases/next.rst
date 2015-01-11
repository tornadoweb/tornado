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
* The ``context`` argument to `.HTTPServerRequest` is now optional,
  and if a context is supplied the ``remote_ip`` attribute is also optional.
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
* `.RequestHandler.locale` now has a property setter.
* `.Future` now catches and logs exceptions in its callbacks.
* `.gen.engine` now correctly captures the stack context for its callbacks.
* `.AsyncTestCase` has better support for multiple exceptions. Previously
  it would silently swallow all but the last; now it raises the first
  and logs all the rest.
* ``curl_httpclient`` now runs the streaming and header callbacks on
  the IOLoop.
* `.StaticFileHandler` no longer logs a stack trace if the connection is
  closed while sending the file.
* `.WebSocketHandler` no longer logs stack traces when the connection
  is closed.
* `tornado.options.define` more accurately finds the module defining the
  option.
* `.WebSocketHandler.open` now accepts ``*args, **kw`` for consistency
  with ``RequestHandler.get`` and related methods.
* `.AsyncTestCase` now cleans up `.Subprocess` state on ``tearDown`` when
  necessary.
* The ``kqueue`` and ``select`` IOLoop implementations now reports
  writeability correctly, fixing flow control in IOStream.
* `tornado.httpclient.HTTPRequest` accepts a new argument
  ``raise_error=False`` to suppress the default behavior of raising an
  error for non-200 response codes.
* `.Application.add_handlers` hostname matching now works correctly with
  IPv6 literals.
* Redirects for the `.Application` ``default_host`` setting now match
  the request protocol instead of redirecting HTTPS to HTTP.
* New function `tornado.httputil.split_host_and_port` for parsing
  the ``netloc`` portion of URLs.
* The `.asynchronous` decorator now understands `concurrent.futures.Future`
  in addition to `tornado.concurrent.Future`.
* `.HTTPServerRequest.body` is now always a byte string (previously the default
  empty body would be a unicode string on python 3).
* `.TCPServer` no longer ignores its ``read_chunk_size`` argument.
* The ``Sec-WebSocket-Version`` header now includes all supported versions.
* Header parsing now works correctly when newline-like unicode characters
  are present.
* Header parsing again supports both CRLF and bare LF line separators.
* `.HTTPServer` now always reports ``HTTP/1.1`` instead of echoing
  the request version.
