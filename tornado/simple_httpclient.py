from __future__ import absolute_import, division, print_function

from tornado.escape import _unicode
from tornado import gen
from tornado.httpclient import HTTPResponse, HTTPError, AsyncHTTPClient, main, _RequestProxy
from tornado import httputil
from tornado.http1connection import HTTP1Connection, HTTP1ConnectionParameters
from tornado.ioloop import IOLoop
from tornado.iostream import StreamClosedError
from tornado.netutil import Resolver, OverrideResolver, _client_ssl_defaults
from tornado.log import gen_log
from tornado import stack_context
from tornado.tcpclient import TCPClient
from tornado.util import PY3

import base64
import collections
import copy
import functools
import re
import socket
import sys
from io import BytesIO


if PY3:
    import urllib.parse as urlparse
else:
    import urlparse

try:
    import ssl
except ImportError:
    # ssl is not available on Google App Engine.
    ssl = None


class HTTPTimeoutError(HTTPError):
    """Error raised by SimpleAsyncHTTPClient on timeout.

    For historical reasons, this is a subclass of `.HTTPClientError`
    which simulates a response code of 599.

    .. versionadded:: 5.1
    """
    def __init__(self, message):
        super(HTTPTimeoutError, self).__init__(599, message=message)

    def __str__(self):
        return self.message


class HTTPStreamClosedError(HTTPError):
    """Error raised by SimpleAsyncHTTPClient when the underlying stream is closed.

    When a more specific exception is available (such as `ConnectionResetError`),
    it may be raised instead of this one.

    For historical reasons, this is a subclass of `.HTTPClientError`
    which simulates a response code of 599.

    .. versionadded:: 5.1
    """
    def __init__(self, message):
        super(HTTPStreamClosedError, self).__init__(599, message=message)

    def __str__(self):
        return self.message


class SimpleAsyncHTTPClient(AsyncHTTPClient):
    """Non-blocking HTTP client with no external dependencies.

    This class implements an HTTP 1.1 client on top of Tornado's IOStreams.
    Some features found in the curl-based AsyncHTTPClient are not yet
    supported.  In particular, proxies are not supported, connections
    are not reused, and callers cannot select the network interface to be
    used.
    """
    def initialize(self, max_clients=10,
                   hostname_mapping=None, max_buffer_size=104857600,
                   resolver=None, defaults=None, max_header_size=None,
                   max_body_size=None):
        """Creates a AsyncHTTPClient.

        Only a single AsyncHTTPClient instance exists per IOLoop
        in order to provide limitations on the number of pending connections.
        ``force_instance=True`` may be used to suppress this behavior.

        Note that because of this implicit reuse, unless ``force_instance``
        is used, only the first call to the constructor actually uses
        its arguments. It is recommended to use the ``configure`` method
        instead of the constructor to ensure that arguments take effect.

        ``max_clients`` is the number of concurrent requests that can be
        in progress; when this limit is reached additional requests will be
        queued. Note that time spent waiting in this queue still counts
        against the ``request_timeout``.

        ``hostname_mapping`` is a dictionary mapping hostnames to IP addresses.
        It can be used to make local DNS changes when modifying system-wide
        settings like ``/etc/hosts`` is not possible or desirable (e.g. in
        unittests).

        ``max_buffer_size`` (default 100MB) is the number of bytes
        that can be read into memory at once. ``max_body_size``
        (defaults to ``max_buffer_size``) is the largest response body
        that the client will accept.  Without a
        ``streaming_callback``, the smaller of these two limits
        applies; with a ``streaming_callback`` only ``max_body_size``
        does.

        .. versionchanged:: 4.2
           Added the ``max_body_size`` argument.
        """
        super(SimpleAsyncHTTPClient, self).initialize(defaults=defaults)
        self.max_clients = max_clients
        self.queue = collections.deque()
        self.active = {}
        self.waiting = {}
        self.max_buffer_size = max_buffer_size
        self.max_header_size = max_header_size
        self.max_body_size = max_body_size
        # TCPClient could create a Resolver for us, but we have to do it
        # ourselves to support hostname_mapping.
        if resolver:
            self.resolver = resolver
            self.own_resolver = False
        else:
            self.resolver = Resolver()
            self.own_resolver = True
        if hostname_mapping is not None:
            self.resolver = OverrideResolver(resolver=self.resolver,
                                             mapping=hostname_mapping)
        self.tcp_client = TCPClient(resolver=self.resolver)

    def close(self):
        super(SimpleAsyncHTTPClient, self).close()
        if self.own_resolver:
            self.resolver.close()
        self.tcp_client.close()

    def fetch_impl(self, request, callback):
        key = object()
        self.queue.append((key, request, callback))
        if not len(self.active) < self.max_clients:
            timeout_handle = self.io_loop.add_timeout(
                self.io_loop.time() + min(request.connect_timeout,
                                          request.request_timeout),
                functools.partial(self._on_timeout, key, "in request queue"))
        else:
            timeout_handle = None
        self.waiting[key] = (request, callback, timeout_handle)
        self._process_queue()
        if self.queue:
            gen_log.debug("max_clients limit reached, request queued. "
                          "%d active, %d queued requests." % (
                              len(self.active), len(self.queue)))

    def _process_queue(self):
        with stack_context.NullContext():
            while self.queue and len(self.active) < self.max_clients:
                key, request, callback = self.queue.popleft()
                if key not in self.waiting:
                    continue
                self._remove_timeout(key)
                self.active[key] = (request, callback)
                release_callback = functools.partial(self._release_fetch, key)
                self._handle_request(request, release_callback, callback)

    def _connection_class(self):
        return _HTTPConnection

    def _handle_request(self, request, release_callback, final_callback):
        self._connection_class()(
            self, request, release_callback,
            final_callback, self.max_buffer_size, self.tcp_client,
            self.max_header_size, self.max_body_size)

    def _release_fetch(self, key):
        del self.active[key]
        self._process_queue()

    def _remove_timeout(self, key):
        if key in self.waiting:
            request, callback, timeout_handle = self.waiting[key]
            if timeout_handle is not None:
                self.io_loop.remove_timeout(timeout_handle)
            del self.waiting[key]

    def _on_timeout(self, key, info=None):
        """Timeout callback of request.

        Construct a timeout HTTPResponse when a timeout occurs.

        :arg object key: A simple object to mark the request.
        :info string key: More detailed timeout information.
        """
        request, callback, timeout_handle = self.waiting[key]
        self.queue.remove((key, request, callback))

        error_message = "Timeout {0}".format(info) if info else "Timeout"
        timeout_response = HTTPResponse(
            request, 599, error=HTTPTimeoutError(error_message),
            request_time=self.io_loop.time() - request.start_time)
        self.io_loop.add_callback(callback, timeout_response)
        del self.waiting[key]


class _HTTPConnection(httputil.HTTPMessageDelegate):
    _SUPPORTED_METHODS = set(["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    _SAFE_METHODS = set(["GET", "HEAD", "OPTIONS"])

    def __init__(self, client, request, release_callback,
                 final_callback, max_buffer_size, tcp_client,
                 max_header_size, max_body_size):
        self.io_loop = IOLoop.current()
        self.start_time = self.io_loop.time()
        self.client = client
        self.request = request
        self.release_callback = release_callback
        self.final_callback = final_callback
        self.max_buffer_size = max_buffer_size
        self.tcp_client = tcp_client
        self.max_header_size = max_header_size
        self.max_body_size = max_body_size
        self.code = None
        self.headers = None
        self.chunks = []
        self._decompressor = None
        # Timeout handle returned by IOLoop.add_timeout
        self._timeout = None
        self._sockaddr = None
        IOLoop.current().add_callback(self.run)

    @gen.coroutine
    def run(self):
        try:
            self.parsed = urlparse.urlsplit(_unicode(self.request.url))
            if self.parsed.scheme not in ("http", "https"):
                raise ValueError("Unsupported url scheme: %s" %
                                 self.request.url)
            # urlsplit results have hostname and port results, but they
            # didn't support ipv6 literals until python 2.7.
            netloc = self.parsed.netloc
            if "@" in netloc:
                userpass, _, netloc = netloc.rpartition("@")
            host, port = httputil.split_host_and_port(netloc)
            if port is None:
                port = 443 if self.parsed.scheme == "https" else 80
            if re.match(r'^\[.*\]$', host):
                # raw ipv6 addresses in urls are enclosed in brackets
                host = host[1:-1]
            self.parsed_hostname = host  # save final host for _on_connect

            if self.request.allow_ipv6 is False:
                af = socket.AF_INET
            else:
                af = socket.AF_UNSPEC

            ssl_options = self._get_ssl_options(self.parsed.scheme)

            timeout = min(self.request.connect_timeout, self.request.request_timeout)
            if timeout:
                self._timeout = self.io_loop.add_timeout(
                    self.start_time + timeout,
                    stack_context.wrap(functools.partial(self._on_timeout, "while connecting")))
                stream = yield self.tcp_client.connect(
                    host, port, af=af,
                    ssl_options=ssl_options,
                    max_buffer_size=self.max_buffer_size)

                if self.final_callback is None:
                    # final_callback is cleared if we've hit our timeout.
                    stream.close()
                    return
                self.stream = stream
                self.stream.set_close_callback(self.on_connection_close)
                self._remove_timeout()
                if self.final_callback is None:
                    return
                if self.request.request_timeout:
                    self._timeout = self.io_loop.add_timeout(
                        self.start_time + self.request.request_timeout,
                        stack_context.wrap(functools.partial(self._on_timeout, "during request")))
                if (self.request.method not in self._SUPPORTED_METHODS and
                        not self.request.allow_nonstandard_methods):
                    raise KeyError("unknown method %s" % self.request.method)
                for key in ('network_interface',
                            'proxy_host', 'proxy_port',
                            'proxy_username', 'proxy_password',
                            'proxy_auth_mode'):
                    if getattr(self.request, key, None):
                        raise NotImplementedError('%s not supported' % key)
                if "Connection" not in self.request.headers:
                    self.request.headers["Connection"] = "close"
                if "Host" not in self.request.headers:
                    if '@' in self.parsed.netloc:
                        self.request.headers["Host"] = self.parsed.netloc.rpartition('@')[-1]
                    else:
                        self.request.headers["Host"] = self.parsed.netloc
                username, password = None, None
                if self.parsed.username is not None:
                    username, password = self.parsed.username, self.parsed.password
                elif self.request.auth_username is not None:
                    username = self.request.auth_username
                    password = self.request.auth_password or ''
                if username is not None:
                    if self.request.auth_mode not in (None, "basic"):
                        raise ValueError("unsupported auth_mode %s",
                                         self.request.auth_mode)
                    self.request.headers["Authorization"] = (
                        b"Basic " + base64.b64encode(
                            httputil.encode_username_password(username, password)))
                if self.request.user_agent:
                    self.request.headers["User-Agent"] = self.request.user_agent
                if not self.request.allow_nonstandard_methods:
                    # Some HTTP methods nearly always have bodies while others
                    # almost never do. Fail in this case unless the user has
                    # opted out of sanity checks with allow_nonstandard_methods.
                    body_expected = self.request.method in ("POST", "PATCH", "PUT")
                    body_present = (self.request.body is not None or
                                    self.request.body_producer is not None)
                    if ((body_expected and not body_present) or
                            (body_present and not body_expected)):
                        raise ValueError(
                            'Body must %sbe None for method %s (unless '
                            'allow_nonstandard_methods is true)' %
                            ('not ' if body_expected else '', self.request.method))
                if self.request.expect_100_continue:
                    self.request.headers["Expect"] = "100-continue"
                if self.request.body is not None:
                    # When body_producer is used the caller is responsible for
                    # setting Content-Length (or else chunked encoding will be used).
                    self.request.headers["Content-Length"] = str(len(
                        self.request.body))
                if (self.request.method == "POST" and
                        "Content-Type" not in self.request.headers):
                    self.request.headers["Content-Type"] = "application/x-www-form-urlencoded"
                if self.request.decompress_response:
                    self.request.headers["Accept-Encoding"] = "gzip"
                req_path = ((self.parsed.path or '/') +
                            (('?' + self.parsed.query) if self.parsed.query else ''))
                self.connection = self._create_connection(stream)
                start_line = httputil.RequestStartLine(self.request.method,
                                                       req_path, '')
                self.connection.write_headers(start_line, self.request.headers)
                if self.request.expect_100_continue:
                    yield self.connection.read_response(self)
                else:
                    yield self._write_body(True)
        except Exception:
            if not self._handle_exception(*sys.exc_info()):
                raise

    def _get_ssl_options(self, scheme):
        if scheme == "https":
            if self.request.ssl_options is not None:
                return self.request.ssl_options
            # If we are using the defaults, don't construct a
            # new SSLContext.
            if (self.request.validate_cert and
                    self.request.ca_certs is None and
                    self.request.client_cert is None and
                    self.request.client_key is None):
                return _client_ssl_defaults
            ssl_ctx = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH,
                cafile=self.request.ca_certs)
            if not self.request.validate_cert:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
            if self.request.client_cert is not None:
                ssl_ctx.load_cert_chain(self.request.client_cert,
                                        self.request.client_key)
            if hasattr(ssl, 'OP_NO_COMPRESSION'):
                # See netutil.ssl_options_to_context
                ssl_ctx.options |= ssl.OP_NO_COMPRESSION
            return ssl_ctx
        return None

    def _on_timeout(self, info=None):
        """Timeout callback of _HTTPConnection instance.

        Raise a `HTTPTimeoutError` when a timeout occurs.

        :info string key: More detailed timeout information.
        """
        self._timeout = None
        error_message = "Timeout {0}".format(info) if info else "Timeout"
        if self.final_callback is not None:
            self._handle_exception(HTTPTimeoutError, HTTPTimeoutError(error_message),
                                   None)

    def _remove_timeout(self):
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
            self._timeout = None

    def _create_connection(self, stream):
        stream.set_nodelay(True)
        connection = HTTP1Connection(
            stream, True,
            HTTP1ConnectionParameters(
                no_keep_alive=True,
                max_header_size=self.max_header_size,
                max_body_size=self.max_body_size,
                decompress=self.request.decompress_response),
            self._sockaddr)
        return connection

    @gen.coroutine
    def _write_body(self, start_read):
        if self.request.body is not None:
            self.connection.write(self.request.body)
        elif self.request.body_producer is not None:
            fut = self.request.body_producer(self.connection.write)
            if fut is not None:
                yield fut
        self.connection.finish()
        if start_read:
            try:
                yield self.connection.read_response(self)
            except StreamClosedError:
                if not self._handle_exception(*sys.exc_info()):
                    raise

    def _release(self):
        if self.release_callback is not None:
            release_callback = self.release_callback
            self.release_callback = None
            release_callback()

    def _run_callback(self, response):
        self._release()
        if self.final_callback is not None:
            final_callback = self.final_callback
            self.final_callback = None
            self.io_loop.add_callback(final_callback, response)

    def _handle_exception(self, typ, value, tb):
        if self.final_callback:
            self._remove_timeout()
            if isinstance(value, StreamClosedError):
                if value.real_error is None:
                    value = HTTPStreamClosedError("Stream closed")
                else:
                    value = value.real_error
            self._run_callback(HTTPResponse(self.request, 599, error=value,
                                            request_time=self.io_loop.time() - self.start_time,
                                            ))

            if hasattr(self, "stream"):
                # TODO: this may cause a StreamClosedError to be raised
                # by the connection's Future.  Should we cancel the
                # connection more gracefully?
                self.stream.close()
            return True
        else:
            # If our callback has already been called, we are probably
            # catching an exception that is not caused by us but rather
            # some child of our callback. Rather than drop it on the floor,
            # pass it along, unless it's just the stream being closed.
            return isinstance(value, StreamClosedError)

    def on_connection_close(self):
        if self.final_callback is not None:
            message = "Connection closed"
            if self.stream.error:
                raise self.stream.error
            try:
                raise HTTPStreamClosedError(message)
            except HTTPStreamClosedError:
                self._handle_exception(*sys.exc_info())

    def headers_received(self, first_line, headers):
        if self.request.expect_100_continue and first_line.code == 100:
            self._write_body(False)
            return
        self.code = first_line.code
        self.reason = first_line.reason
        self.headers = headers

        if self._should_follow_redirect():
            return

        if self.request.header_callback is not None:
            # Reassemble the start line.
            self.request.header_callback('%s %s %s\r\n' % first_line)
            for k, v in self.headers.get_all():
                self.request.header_callback("%s: %s\r\n" % (k, v))
            self.request.header_callback('\r\n')

    def _should_follow_redirect(self):
        return (self.request.follow_redirects and
                self.request.max_redirects > 0 and
                self.code in (301, 302, 303, 307, 308) and
                self.headers.get("Location") is not None)

    def finish(self):
        data = b''.join(self.chunks)
        self._remove_timeout()
        original_request = getattr(self.request, "original_request",
                                   self.request)
        if self._should_follow_redirect():
            assert isinstance(self.request, _RequestProxy)
            new_request = copy.copy(self.request.request)
            new_request.url = urlparse.urljoin(self.request.url,
                                               self.headers["Location"])
            new_request.max_redirects = self.request.max_redirects - 1
            del new_request.headers["Host"]
            # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.4
            # Client SHOULD make a GET request after a 303.
            # According to the spec, 302 should be followed by the same
            # method as the original request, but in practice browsers
            # treat 302 the same as 303, and many servers use 302 for
            # compatibility with pre-HTTP/1.1 user agents which don't
            # understand the 303 status.
            if self.code in (301, 302, 303):
                if self.request.method not in self._SAFE_METHODS:
                    new_request.method = "GET"
                new_request.body = None
                for h in ["Content-Length", "Content-Type",
                          "Content-Encoding", "Transfer-Encoding"]:
                    try:
                        del self.request.headers[h]
                    except KeyError:
                        pass
            new_request.original_request = original_request
            final_callback = self.final_callback
            self.final_callback = None
            self._release()
            fut = self.client.fetch(new_request, raise_error=False)
            fut.add_done_callback(lambda f: final_callback(f.result()))
            self._on_end_request()
            return
        if self.request.streaming_callback:
            buffer = BytesIO()
        else:
            buffer = BytesIO(data)  # TODO: don't require one big string?
        response = HTTPResponse(original_request,
                                self.code, reason=getattr(self, 'reason', None),
                                headers=self.headers,
                                request_time=self.io_loop.time() - self.start_time,
                                buffer=buffer,
                                effective_url=self.request.url)
        self._run_callback(response)
        self._on_end_request()

    def _on_end_request(self):
        self.stream.close()

    def data_received(self, chunk):
        if self._should_follow_redirect():
            # We're going to follow a redirect so just discard the body.
            return
        if self.request.streaming_callback is not None:
            self.request.streaming_callback(chunk)
        else:
            self.chunks.append(chunk)


if __name__ == "__main__":
    AsyncHTTPClient.configure(SimpleAsyncHTTPClient)
    main()
