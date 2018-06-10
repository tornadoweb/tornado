"""Blocking and non-blocking HTTP client interfaces.

This module defines a common interface shared by two implementations,
``simple_httpclient`` and ``curl_httpclient``.  Applications may either
instantiate their chosen implementation class directly or use the
`AsyncHTTPClient` class from this module, which selects an implementation
that can be overridden with the `AsyncHTTPClient.configure` method.

The default implementation is ``simple_httpclient``, and this is expected
to be suitable for most users' needs.  However, some applications may wish
to switch to ``curl_httpclient`` for reasons such as the following:

* ``curl_httpclient`` has some features not found in ``simple_httpclient``,
  including support for HTTP proxies and the ability to use a specified
  network interface.

* ``curl_httpclient`` is more likely to be compatible with sites that are
  not-quite-compliant with the HTTP spec, or sites that use little-exercised
  features of HTTP.

* ``curl_httpclient`` is faster.

* ``curl_httpclient`` was the default prior to Tornado 2.0.

Note that if you are using ``curl_httpclient``, it is highly
recommended that you use a recent version of ``libcurl`` and
``pycurl``.  Currently the minimum supported version of libcurl is
7.22.0, and the minimum version of pycurl is 7.18.2.  It is highly
recommended that your ``libcurl`` installation is built with
asynchronous DNS resolver (threaded or c-ares), otherwise you may
encounter various problems with request timeouts (for more
information, see
http://curl.haxx.se/libcurl/c/curl_easy_setopt.html#CURLOPTCONNECTTIMEOUTMS
and comments in curl_httpclient.py).

To select ``curl_httpclient``, call `AsyncHTTPClient.configure` at startup::

    AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
"""

from __future__ import absolute_import, division, print_function

import functools
import time
import warnings
import weakref

from tornado.concurrent import Future, future_set_result_unless_cancelled
from tornado.escape import utf8, native_str
from tornado import gen, httputil, stack_context
from tornado.ioloop import IOLoop
from tornado.util import Configurable


class HTTPClient(object):
    """A blocking HTTP client.

    This interface is provided to make it easier to share code between
    synchronous and asynchronous applications. Applications that are
    running an `.IOLoop` must use `AsyncHTTPClient` instead.

    Typical usage looks like this::

        http_client = httpclient.HTTPClient()
        try:
            response = http_client.fetch("http://www.google.com/")
            print(response.body)
        except httpclient.HTTPError as e:
            # HTTPError is raised for non-200 responses; the response
            # can be found in e.response.
            print("Error: " + str(e))
        except Exception as e:
            # Other errors are possible, such as IOError.
            print("Error: " + str(e))
        http_client.close()

    .. versionchanged:: 5.0

       Due to limitations in `asyncio`, it is no longer possible to
       use the synchronous ``HTTPClient`` while an `.IOLoop` is running.
       Use `AsyncHTTPClient` instead.

    """
    def __init__(self, async_client_class=None, **kwargs):
        # Initialize self._closed at the beginning of the constructor
        # so that an exception raised here doesn't lead to confusing
        # failures in __del__.
        self._closed = True
        self._io_loop = IOLoop(make_current=False)
        if async_client_class is None:
            async_client_class = AsyncHTTPClient
        # Create the client while our IOLoop is "current", without
        # clobbering the thread's real current IOLoop (if any).
        self._async_client = self._io_loop.run_sync(
            gen.coroutine(lambda: async_client_class(**kwargs)))
        self._closed = False

    def __del__(self):
        self.close()

    def close(self):
        """Closes the HTTPClient, freeing any resources used."""
        if not self._closed:
            self._async_client.close()
            self._io_loop.close()
            self._closed = True

    def fetch(self, request, **kwargs):
        """Executes a request, returning an `HTTPResponse`.

        The request may be either a string URL or an `HTTPRequest` object.
        If it is a string, we construct an `HTTPRequest` using any additional
        kwargs: ``HTTPRequest(request, **kwargs)``

        If an error occurs during the fetch, we raise an `HTTPError` unless
        the ``raise_error`` keyword argument is set to False.
        """
        response = self._io_loop.run_sync(functools.partial(
            self._async_client.fetch, request, **kwargs))
        return response


class AsyncHTTPClient(Configurable):
    """An non-blocking HTTP client.

    Example usage::

        async def f():
            http_client = AsyncHTTPClient()
            try:
                response = await http_client.fetch("http://www.google.com")
            except Exception as e:
                print("Error: %s" % e)
            else:
                print(response.body)

    The constructor for this class is magic in several respects: It
    actually creates an instance of an implementation-specific
    subclass, and instances are reused as a kind of pseudo-singleton
    (one per `.IOLoop`). The keyword argument ``force_instance=True``
    can be used to suppress this singleton behavior. Unless
    ``force_instance=True`` is used, no arguments should be passed to
    the `AsyncHTTPClient` constructor. The implementation subclass as
    well as arguments to its constructor can be set with the static
    method `configure()`

    All `AsyncHTTPClient` implementations support a ``defaults``
    keyword argument, which can be used to set default values for
    `HTTPRequest` attributes.  For example::

        AsyncHTTPClient.configure(
            None, defaults=dict(user_agent="MyUserAgent"))
        # or with force_instance:
        client = AsyncHTTPClient(force_instance=True,
            defaults=dict(user_agent="MyUserAgent"))

    .. versionchanged:: 5.0
       The ``io_loop`` argument (deprecated since version 4.1) has been removed.

    """
    @classmethod
    def configurable_base(cls):
        return AsyncHTTPClient

    @classmethod
    def configurable_default(cls):
        from tornado.simple_httpclient import SimpleAsyncHTTPClient
        return SimpleAsyncHTTPClient

    @classmethod
    def _async_clients(cls):
        attr_name = '_async_client_dict_' + cls.__name__
        if not hasattr(cls, attr_name):
            setattr(cls, attr_name, weakref.WeakKeyDictionary())
        return getattr(cls, attr_name)

    def __new__(cls, force_instance=False, **kwargs):
        io_loop = IOLoop.current()
        if force_instance:
            instance_cache = None
        else:
            instance_cache = cls._async_clients()
        if instance_cache is not None and io_loop in instance_cache:
            return instance_cache[io_loop]
        instance = super(AsyncHTTPClient, cls).__new__(cls, **kwargs)
        # Make sure the instance knows which cache to remove itself from.
        # It can't simply call _async_clients() because we may be in
        # __new__(AsyncHTTPClient) but instance.__class__ may be
        # SimpleAsyncHTTPClient.
        instance._instance_cache = instance_cache
        if instance_cache is not None:
            instance_cache[instance.io_loop] = instance
        return instance

    def initialize(self, defaults=None):
        self.io_loop = IOLoop.current()
        self.defaults = dict(HTTPRequest._DEFAULTS)
        if defaults is not None:
            self.defaults.update(defaults)
        self._closed = False

    def close(self):
        """Destroys this HTTP client, freeing any file descriptors used.

        This method is **not needed in normal use** due to the way
        that `AsyncHTTPClient` objects are transparently reused.
        ``close()`` is generally only necessary when either the
        `.IOLoop` is also being closed, or the ``force_instance=True``
        argument was used when creating the `AsyncHTTPClient`.

        No other methods may be called on the `AsyncHTTPClient` after
        ``close()``.

        """
        if self._closed:
            return
        self._closed = True
        if self._instance_cache is not None:
            if self._instance_cache.get(self.io_loop) is not self:
                raise RuntimeError("inconsistent AsyncHTTPClient cache")
            del self._instance_cache[self.io_loop]

    def fetch(self, request, callback=None, raise_error=True, **kwargs):
        """Executes a request, asynchronously returning an `HTTPResponse`.

        The request may be either a string URL or an `HTTPRequest` object.
        If it is a string, we construct an `HTTPRequest` using any additional
        kwargs: ``HTTPRequest(request, **kwargs)``

        This method returns a `.Future` whose result is an
        `HTTPResponse`. By default, the ``Future`` will raise an
        `HTTPError` if the request returned a non-200 response code
        (other errors may also be raised if the server could not be
        contacted). Instead, if ``raise_error`` is set to False, the
        response will always be returned regardless of the response
        code.

        If a ``callback`` is given, it will be invoked with the `HTTPResponse`.
        In the callback interface, `HTTPError` is not automatically raised.
        Instead, you must check the response's ``error`` attribute or
        call its `~HTTPResponse.rethrow` method.

        .. deprecated:: 5.1

           The ``callback`` argument is deprecated and will be removed
           in 6.0. Use the returned `.Future` instead.

           The ``raise_error=False`` argument currently suppresses
           *all* errors, encapsulating them in `HTTPResponse` objects
           with a 599 response code. This will change in Tornado 6.0:
           ``raise_error=False`` will only affect the `HTTPError`
           raised when a non-200 response code is used.

        """
        if self._closed:
            raise RuntimeError("fetch() called on closed AsyncHTTPClient")
        if not isinstance(request, HTTPRequest):
            request = HTTPRequest(url=request, **kwargs)
        else:
            if kwargs:
                raise ValueError("kwargs can't be used if request is an HTTPRequest object")
        # We may modify this (to add Host, Accept-Encoding, etc),
        # so make sure we don't modify the caller's object.  This is also
        # where normal dicts get converted to HTTPHeaders objects.
        request.headers = httputil.HTTPHeaders(request.headers)
        request = _RequestProxy(request, self.defaults)
        future = Future()
        if callback is not None:
            warnings.warn("callback arguments are deprecated, use the returned Future instead",
                          DeprecationWarning)
            callback = stack_context.wrap(callback)

            def handle_future(future):
                exc = future.exception()
                if isinstance(exc, HTTPError) and exc.response is not None:
                    response = exc.response
                elif exc is not None:
                    response = HTTPResponse(
                        request, 599, error=exc,
                        request_time=time.time() - request.start_time)
                else:
                    response = future.result()
                self.io_loop.add_callback(callback, response)
            future.add_done_callback(handle_future)

        def handle_response(response):
            if raise_error and response.error:
                if isinstance(response.error, HTTPError):
                    response.error.response = response
                future.set_exception(response.error)
            else:
                if response.error and not response._error_is_response_code:
                    warnings.warn("raise_error=False will allow '%s' to be raised in the future" %
                                  response.error, DeprecationWarning)
                future_set_result_unless_cancelled(future, response)
        self.fetch_impl(request, handle_response)
        return future

    def fetch_impl(self, request, callback):
        raise NotImplementedError()

    @classmethod
    def configure(cls, impl, **kwargs):
        """Configures the `AsyncHTTPClient` subclass to use.

        ``AsyncHTTPClient()`` actually creates an instance of a subclass.
        This method may be called with either a class object or the
        fully-qualified name of such a class (or ``None`` to use the default,
        ``SimpleAsyncHTTPClient``)

        If additional keyword arguments are given, they will be passed
        to the constructor of each subclass instance created.  The
        keyword argument ``max_clients`` determines the maximum number
        of simultaneous `~AsyncHTTPClient.fetch()` operations that can
        execute in parallel on each `.IOLoop`.  Additional arguments
        may be supported depending on the implementation class in use.

        Example::

           AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
        """
        super(AsyncHTTPClient, cls).configure(impl, **kwargs)


class HTTPRequest(object):
    """HTTP client request object."""

    # Default values for HTTPRequest parameters.
    # Merged with the values on the request object by AsyncHTTPClient
    # implementations.
    _DEFAULTS = dict(
        connect_timeout=20.0,
        request_timeout=20.0,
        follow_redirects=True,
        max_redirects=5,
        decompress_response=True,
        proxy_password='',
        allow_nonstandard_methods=False,
        validate_cert=True)

    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None, auth_mode=None,
                 connect_timeout=None, request_timeout=None,
                 if_modified_since=None, follow_redirects=None,
                 max_redirects=None, user_agent=None, use_gzip=None,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 proxy_host=None, proxy_port=None, proxy_username=None,
                 proxy_password=None, proxy_auth_mode=None,
                 allow_nonstandard_methods=None, validate_cert=None,
                 ca_certs=None, allow_ipv6=None, client_key=None,
                 client_cert=None, body_producer=None,
                 expect_100_continue=False, decompress_response=None,
                 ssl_options=None):
        r"""All parameters except ``url`` are optional.

        :arg str url: URL to fetch
        :arg str method: HTTP method, e.g. "GET" or "POST"
        :arg headers: Additional HTTP headers to pass on the request
        :type headers: `~tornado.httputil.HTTPHeaders` or `dict`
        :arg body: HTTP request body as a string (byte or unicode; if unicode
           the utf-8 encoding will be used)
        :arg body_producer: Callable used for lazy/asynchronous request bodies.
           It is called with one argument, a ``write`` function, and should
           return a `.Future`.  It should call the write function with new
           data as it becomes available.  The write function returns a
           `.Future` which can be used for flow control.
           Only one of ``body`` and ``body_producer`` may
           be specified.  ``body_producer`` is not supported on
           ``curl_httpclient``.  When using ``body_producer`` it is recommended
           to pass a ``Content-Length`` in the headers as otherwise chunked
           encoding will be used, and many servers do not support chunked
           encoding on requests.  New in Tornado 4.0
        :arg str auth_username: Username for HTTP authentication
        :arg str auth_password: Password for HTTP authentication
        :arg str auth_mode: Authentication mode; default is "basic".
           Allowed values are implementation-defined; ``curl_httpclient``
           supports "basic" and "digest"; ``simple_httpclient`` only supports
           "basic"
        :arg float connect_timeout: Timeout for initial connection in seconds,
           default 20 seconds
        :arg float request_timeout: Timeout for entire request in seconds,
           default 20 seconds
        :arg if_modified_since: Timestamp for ``If-Modified-Since`` header
        :type if_modified_since: `datetime` or `float`
        :arg bool follow_redirects: Should redirects be followed automatically
           or return the 3xx response? Default True.
        :arg int max_redirects: Limit for ``follow_redirects``, default 5.
        :arg str user_agent: String to send as ``User-Agent`` header
        :arg bool decompress_response: Request a compressed response from
           the server and decompress it after downloading.  Default is True.
           New in Tornado 4.0.
        :arg bool use_gzip: Deprecated alias for ``decompress_response``
           since Tornado 4.0.
        :arg str network_interface: Network interface to use for request.
           ``curl_httpclient`` only; see note below.
        :arg collections.abc.Callable streaming_callback: If set, ``streaming_callback`` will
           be run with each chunk of data as it is received, and
           ``HTTPResponse.body`` and ``HTTPResponse.buffer`` will be empty in
           the final response.
        :arg collections.abc.Callable header_callback: If set, ``header_callback`` will
           be run with each header line as it is received (including the
           first line, e.g. ``HTTP/1.0 200 OK\r\n``, and a final line
           containing only ``\r\n``.  All lines include the trailing newline
           characters).  ``HTTPResponse.headers`` will be empty in the final
           response.  This is most useful in conjunction with
           ``streaming_callback``, because it's the only way to get access to
           header data while the request is in progress.
        :arg collections.abc.Callable prepare_curl_callback: If set, will be called with
           a ``pycurl.Curl`` object to allow the application to make additional
           ``setopt`` calls.
        :arg str proxy_host: HTTP proxy hostname.  To use proxies,
           ``proxy_host`` and ``proxy_port`` must be set; ``proxy_username``,
           ``proxy_pass`` and ``proxy_auth_mode`` are optional.  Proxies are
           currently only supported with ``curl_httpclient``.
        :arg int proxy_port: HTTP proxy port
        :arg str proxy_username: HTTP proxy username
        :arg str proxy_password: HTTP proxy password
        :arg str proxy_auth_mode: HTTP proxy Authentication mode;
           default is "basic". supports "basic" and "digest"
        :arg bool allow_nonstandard_methods: Allow unknown values for ``method``
           argument? Default is False.
        :arg bool validate_cert: For HTTPS requests, validate the server's
           certificate? Default is True.
        :arg str ca_certs: filename of CA certificates in PEM format,
           or None to use defaults.  See note below when used with
           ``curl_httpclient``.
        :arg str client_key: Filename for client SSL key, if any.  See
           note below when used with ``curl_httpclient``.
        :arg str client_cert: Filename for client SSL certificate, if any.
           See note below when used with ``curl_httpclient``.
        :arg ssl.SSLContext ssl_options: `ssl.SSLContext` object for use in
           ``simple_httpclient`` (unsupported by ``curl_httpclient``).
           Overrides ``validate_cert``, ``ca_certs``, ``client_key``,
           and ``client_cert``.
        :arg bool allow_ipv6: Use IPv6 when available?  Default is true.
        :arg bool expect_100_continue: If true, send the
           ``Expect: 100-continue`` header and wait for a continue response
           before sending the request body.  Only supported with
           simple_httpclient.

        .. note::

            When using ``curl_httpclient`` certain options may be
            inherited by subsequent fetches because ``pycurl`` does
            not allow them to be cleanly reset.  This applies to the
            ``ca_certs``, ``client_key``, ``client_cert``, and
            ``network_interface`` arguments.  If you use these
            options, you should pass them on every request (you don't
            have to always use the same values, but it's not possible
            to mix requests that specify these options with ones that
            use the defaults).

        .. versionadded:: 3.1
           The ``auth_mode`` argument.

        .. versionadded:: 4.0
           The ``body_producer`` and ``expect_100_continue`` arguments.

        .. versionadded:: 4.2
           The ``ssl_options`` argument.

        .. versionadded:: 4.5
           The ``proxy_auth_mode`` argument.
        """
        # Note that some of these attributes go through property setters
        # defined below.
        self.headers = headers
        if if_modified_since:
            self.headers["If-Modified-Since"] = httputil.format_timestamp(
                if_modified_since)
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.proxy_auth_mode = proxy_auth_mode
        self.url = url
        self.method = method
        self.body = body
        self.body_producer = body_producer
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.auth_mode = auth_mode
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        if decompress_response is not None:
            self.decompress_response = decompress_response
        else:
            self.decompress_response = use_gzip
        self.network_interface = network_interface
        self.streaming_callback = streaming_callback
        self.header_callback = header_callback
        self.prepare_curl_callback = prepare_curl_callback
        self.allow_nonstandard_methods = allow_nonstandard_methods
        self.validate_cert = validate_cert
        self.ca_certs = ca_certs
        self.allow_ipv6 = allow_ipv6
        self.client_key = client_key
        self.client_cert = client_cert
        self.ssl_options = ssl_options
        self.expect_100_continue = expect_100_continue
        self.start_time = time.time()

    @property
    def headers(self):
        return self._headers

    @headers.setter
    def headers(self, value):
        if value is None:
            self._headers = httputil.HTTPHeaders()
        else:
            self._headers = value

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value):
        self._body = utf8(value)

    @property
    def body_producer(self):
        return self._body_producer

    @body_producer.setter
    def body_producer(self, value):
        self._body_producer = stack_context.wrap(value)

    @property
    def streaming_callback(self):
        return self._streaming_callback

    @streaming_callback.setter
    def streaming_callback(self, value):
        self._streaming_callback = stack_context.wrap(value)

    @property
    def header_callback(self):
        return self._header_callback

    @header_callback.setter
    def header_callback(self, value):
        self._header_callback = stack_context.wrap(value)

    @property
    def prepare_curl_callback(self):
        return self._prepare_curl_callback

    @prepare_curl_callback.setter
    def prepare_curl_callback(self, value):
        self._prepare_curl_callback = stack_context.wrap(value)


class HTTPResponse(object):
    """HTTP Response object.

    Attributes:

    * request: HTTPRequest object

    * code: numeric HTTP status code, e.g. 200 or 404

    * reason: human-readable reason phrase describing the status code

    * headers: `tornado.httputil.HTTPHeaders` object

    * effective_url: final location of the resource after following any
      redirects

    * buffer: ``cStringIO`` object for response body

    * body: response body as bytes (created on demand from ``self.buffer``)

    * error: Exception object, if any

    * request_time: seconds from request start to finish. Includes all network
      operations from DNS resolution to receiving the last byte of data.
      Does not include time spent in the queue (due to the ``max_clients`` option).
      If redirects were followed, only includes the final request.

    * start_time: Time at which the HTTP operation started, based on `time.time`
      (not the monotonic clock used by `.IOLoop.time`). May be ``None`` if the request
      timed out while in the queue.

    * time_info: dictionary of diagnostic timing information from the request.
      Available data are subject to change, but currently uses timings
      available from http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html,
      plus ``queue``, which is the delay (if any) introduced by waiting for
      a slot under `AsyncHTTPClient`'s ``max_clients`` setting.

    .. versionadded:: 5.1

       Added the ``start_time`` attribute.

    .. versionchanged:: 5.1

       The ``request_time`` attribute previously included time spent in the queue
       for ``simple_httpclient``, but not in ``curl_httpclient``. Now queueing time
       is excluded in both implementations. ``request_time`` is now more accurate for
       ``curl_httpclient`` because it uses a monotonic clock when available.
    """
    def __init__(self, request, code, headers=None, buffer=None,
                 effective_url=None, error=None, request_time=None,
                 time_info=None, reason=None, start_time=None):
        if isinstance(request, _RequestProxy):
            self.request = request.request
        else:
            self.request = request
        self.code = code
        self.reason = reason or httputil.responses.get(code, "Unknown")
        if headers is not None:
            self.headers = headers
        else:
            self.headers = httputil.HTTPHeaders()
        self.buffer = buffer
        self._body = None
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        self._error_is_response_code = False
        if error is None:
            if self.code < 200 or self.code >= 300:
                self._error_is_response_code = True
                self.error = HTTPError(self.code, message=self.reason,
                                       response=self)
            else:
                self.error = None
        else:
            self.error = error
        self.start_time = start_time
        self.request_time = request_time
        self.time_info = time_info or {}

    @property
    def body(self):
        if self.buffer is None:
            return None
        elif self._body is None:
            self._body = self.buffer.getvalue()

        return self._body

    def rethrow(self):
        """If there was an error on the request, raise an `HTTPError`."""
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in sorted(self.__dict__.items()))
        return "%s(%s)" % (self.__class__.__name__, args)


class HTTPClientError(Exception):
    """Exception thrown for an unsuccessful HTTP request.

    Attributes:

    * ``code`` - HTTP error integer error code, e.g. 404.  Error code 599 is
      used when no HTTP response was received, e.g. for a timeout.

    * ``response`` - `HTTPResponse` object, if any.

    Note that if ``follow_redirects`` is False, redirects become HTTPErrors,
    and you can look at ``error.response.headers['Location']`` to see the
    destination of the redirect.

    .. versionchanged:: 5.1

       Renamed from ``HTTPError`` to ``HTTPClientError`` to avoid collisions with
       `tornado.web.HTTPError`. The name ``tornado.httpclient.HTTPError`` remains
       as an alias.
    """
    def __init__(self, code, message=None, response=None):
        self.code = code
        self.message = message or httputil.responses.get(code, "Unknown")
        self.response = response
        super(HTTPClientError, self).__init__(code, message, response)

    def __str__(self):
        return "HTTP %d: %s" % (self.code, self.message)

    # There is a cyclic reference between self and self.response,
    # which breaks the default __repr__ implementation.
    # (especially on pypy, which doesn't have the same recursion
    # detection as cpython).
    __repr__ = __str__


HTTPError = HTTPClientError


class _RequestProxy(object):
    """Combines an object with a dictionary of defaults.

    Used internally by AsyncHTTPClient implementations.
    """
    def __init__(self, request, defaults):
        self.request = request
        self.defaults = defaults

    def __getattr__(self, name):
        request_attr = getattr(self.request, name)
        if request_attr is not None:
            return request_attr
        elif self.defaults is not None:
            return self.defaults.get(name, None)
        else:
            return None


def main():
    from tornado.options import define, options, parse_command_line
    define("print_headers", type=bool, default=False)
    define("print_body", type=bool, default=True)
    define("follow_redirects", type=bool, default=True)
    define("validate_cert", type=bool, default=True)
    define("proxy_host", type=str)
    define("proxy_port", type=int)
    args = parse_command_line()
    client = HTTPClient()
    for arg in args:
        try:
            response = client.fetch(arg,
                                    follow_redirects=options.follow_redirects,
                                    validate_cert=options.validate_cert,
                                    proxy_host=options.proxy_host,
                                    proxy_port=options.proxy_port,
                                    )
        except HTTPError as e:
            if e.response is not None:
                response = e.response
            else:
                raise
        if options.print_headers:
            print(response.headers)
        if options.print_body:
            print(native_str(response.body))
    client.close()


if __name__ == "__main__":
    main()
