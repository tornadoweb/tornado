#!/usr/bin/env python
from __future__ import absolute_import, division, print_function, with_statement

from tornado.concurrent import is_future
from tornado.escape import native_str, utf8, _unicode
from tornado import gen
from tornado.httpclient import HTTPResponse, HTTPError, AsyncHTTPClient, main, _RequestProxy
from tornado import httputil
from tornado.http1connection import HTTP1Connection, HTTP1ConnectionParameters
from tornado.iostream import StreamClosedError
from tornado.netutil import Resolver, OverrideResolver
from tornado.log import gen_log
from tornado import stack_context
from tornado.tcpclient import TCPClient

import base64
import collections
import copy
import functools
import re
import socket
import sys
from io import BytesIO


try:
    import urlparse  # py2
except ImportError:
    import urllib.parse as urlparse  # py3

try:
    import ssl
except ImportError:
    # ssl is not available on Google App Engine.
    ssl = None

try:
    import certifi
except ImportError:
    certifi = None


def _default_ca_certs():
    if certifi is None:
        raise Exception("The 'certifi' package is required to use https "
                        "in simple_httpclient")
    return certifi.where()


class SimpleAsyncHTTPClient(AsyncHTTPClient):
    """Non-blocking HTTP client with no external dependencies.

    This class implements an HTTP 1.1 client on top of Tornado's IOStreams.
    It does not currently implement all applicable parts of the HTTP
    specification, but it does enough to work with major web service APIs.

    Some features found in the curl-based AsyncHTTPClient are not yet
    supported.  In particular, connections are not reused, and callers
    cannot select the network interface to be used.
    """
    def initialize(self, io_loop, max_clients=10,
                   hostname_mapping=None, max_buffer_size=104857600,
                   resolver=None, defaults=None, max_header_size=None):
        """Creates a AsyncHTTPClient.

        Only a single AsyncHTTPClient instance exists per IOLoop
        in order to provide limitations on the number of pending connections.
        force_instance=True may be used to suppress this behavior.

        max_clients is the number of concurrent requests that can be
        in progress.  Note that this arguments are only used when the
        client is first created, and will be ignored when an existing
        client is reused.

        hostname_mapping is a dictionary mapping hostnames to IP addresses.
        It can be used to make local DNS changes when modifying system-wide
        settings like /etc/hosts is not possible or desirable (e.g. in
        unittests).

        max_buffer_size is the number of bytes that can be read by IOStream. It
        defaults to 100mb.
        """
        super(SimpleAsyncHTTPClient, self).initialize(io_loop,
                                                      defaults=defaults)
        self.max_clients = max_clients
        self.queue = collections.deque()
        self.active = {}
        self.waiting = {}
        self.max_buffer_size = max_buffer_size
        self.max_header_size = max_header_size
        # TCPClient could create a Resolver for us, but we have to do it
        # ourselves to support hostname_mapping.
        if resolver:
            self.resolver = resolver
            self.own_resolver = False
        else:
            self.resolver = Resolver(io_loop=io_loop)
            self.own_resolver = True
        if hostname_mapping is not None:
            self.resolver = OverrideResolver(resolver=self.resolver,
                                             mapping=hostname_mapping)
        self.tcp_client = TCPClient(resolver=self.resolver, io_loop=io_loop)

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
                functools.partial(self._on_timeout, key))
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

    def _handle_request(self, request, release_callback, final_callback):
        _HTTPConnection(self.io_loop, self, request, release_callback,
                        final_callback, self.max_buffer_size, self.tcp_client,
                        self.max_header_size)

    def _release_fetch(self, key):
        del self.active[key]
        self._process_queue()

    def _remove_timeout(self, key):
        if key in self.waiting:
            request, callback, timeout_handle = self.waiting[key]
            if timeout_handle is not None:
                self.io_loop.remove_timeout(timeout_handle)
            del self.waiting[key]

    def _on_timeout(self, key):
        request, callback, timeout_handle = self.waiting[key]
        self.queue.remove((key, request, callback))
        timeout_response = HTTPResponse(
            request, 599, error=HTTPError(599, "Timeout"),
            request_time=self.io_loop.time() - request.start_time)
        self.io_loop.add_callback(callback, timeout_response)
        del self.waiting[key]


class _HTTPConnection(httputil.HTTPMessageDelegate):
    _SUPPORTED_METHODS = set(["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])

    def __init__(self, io_loop, client, request, release_callback,
                 final_callback, max_buffer_size, tcp_client,
                 max_header_size):
        self.start_time = io_loop.time()
        self.io_loop = io_loop
        self.client = client
        self.request = request
        self.release_callback = release_callback
        self.final_callback = final_callback
        self.max_buffer_size = max_buffer_size
        self.tcp_client = tcp_client
        self.max_header_size = max_header_size
        self.code = None
        self.headers = None
        self.chunks = []
        self._decompressor = None
        # Timeout handle returned by IOLoop.add_timeout
        self._timeout = None
        self._sockaddr = None
        with stack_context.ExceptionStackContext(self._handle_exception):
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
            self.parsed_hostname = host  # save final host for _on_connect and _on_proxy_connect
            self.parsed_port = port      # save port for _on_proxy_connect

            if request.allow_ipv6 is False:
                af = socket.AF_INET
            else:
                af = socket.AF_UNSPEC

            ssl_options = self._get_ssl_options(self.parsed.scheme)

            timeout = min(self.request.connect_timeout, self.request.request_timeout)
            if timeout:
                self._timeout = self.io_loop.add_timeout(
                    self.start_time + timeout,
                    stack_context.wrap(self._on_timeout))

            proxy_host = getattr(self.request, "proxy_host", None)
            proxy_port = getattr(self.request, "proxy_port", None)
            if proxy_host is not None or proxy_port is not None:
                if proxy_host is not None and proxy_port is not None:
                    self.proxy_host = proxy_host
                    self.proxy_port = int(proxy_port)
                    self.use_connect_proxy = ssl_options is not None
                    callback = self._on_proxy_connect if self.use_connect_proxy else self._on_connect
                    self.tcp_client.connect(self.proxy_host, self.proxy_port, af=af,
                                            max_buffer_size=self.max_buffer_size,
                                            callback=callback)
                else:
                    raise ValueError("Both proxy_host and proxy_port must be set.")
            else:
                self.proxy_host = self.proxy_port = None
                self.use_connect_proxy = False
                self.tcp_client.connect(host, port, af=af,
                                        ssl_options=ssl_options,
                                        max_buffer_size=self.max_buffer_size,
                                        callback=self._on_connect)

    def _get_ssl_options(self, scheme):
        if scheme == "https":
            ssl_options = {}
            if self.request.validate_cert:
                ssl_options["cert_reqs"] = ssl.CERT_REQUIRED
            if self.request.ca_certs is not None:
                ssl_options["ca_certs"] = self.request.ca_certs
            else:
                ssl_options["ca_certs"] = _default_ca_certs()
            if self.request.client_key is not None:
                ssl_options["keyfile"] = self.request.client_key
            if self.request.client_cert is not None:
                ssl_options["certfile"] = self.request.client_cert

            # SSL interoperability is tricky.  We want to disable
            # SSLv2 for security reasons; it wasn't disabled by default
            # until openssl 1.0.  The best way to do this is to use
            # the SSL_OP_NO_SSLv2, but that wasn't exposed to python
            # until 3.2.  Python 2.7 adds the ciphers argument, which
            # can also be used to disable SSLv2.  As a last resort
            # on python 2.6, we set ssl_version to TLSv1.  This is
            # more narrow than we'd like since it also breaks
            # compatibility with servers configured for SSLv3 only,
            # but nearly all servers support both SSLv3 and TLSv1:
            # http://blog.ivanristic.com/2011/09/ssl-survey-protocol-support.html
            if sys.version_info >= (2, 7):
                # In addition to disabling SSLv2, we also exclude certain
                # classes of insecure ciphers.
                ssl_options["ciphers"] = "DEFAULT:!SSLv2:!EXPORT:!DES"
            else:
                # This is really only necessary for pre-1.0 versions
                # of openssl, but python 2.6 doesn't expose version
                # information.
                ssl_options["ssl_version"] = ssl.PROTOCOL_TLSv1
            return ssl_options
        return None

    def _on_timeout(self):
        self._timeout = None
        if self.final_callback is not None:
            raise HTTPError(599, "Timeout")

    def _remove_timeout(self):
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
            self._timeout = None

    def _on_connect(self, stream):
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
                stack_context.wrap(self._on_timeout))
        if (self.request.method not in self._SUPPORTED_METHODS and
                not self.request.allow_nonstandard_methods):
            raise KeyError("unknown method %s" % self.request.method)
        for key in ('network_interface'):
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
            auth = utf8(username) + b":" + utf8(password)
            self.request.headers["Authorization"] = (b"Basic " +
                                                     base64.b64encode(auth))

        # Add a Proxy-Authorization header if this connection is not using the transparent CONNECT proxy.
        if not self.use_connect_proxy:
            proxy_username = getattr(self.request, "proxy_username", None)
            proxy_password = getattr(self.request, "proxy_password", None)
            if proxy_username is not None and proxy_password is not None:
                if self.proxy_host is None or self.proxy_port is None:
                    raise ValueError("proxy_username and proxy_password set without proxy_host and proxy_port both set")
                proxy_username = proxy_username or ''
                proxy_password = proxy_password or ''
                proxy_auth = utf8(proxy_username) + b":" + utf8(proxy_password)
                self.request.headers["Proxy-Authorization"] = (b"Basic " +
                                                               base64.b64encode(proxy_auth))

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
                    'Body must %sbe None for method %s (unelss '
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

        if self.proxy_host is not None and not self.use_connect_proxy:
            req_path = self.request.url
        else:
            req_path = ((self.parsed.path or '/') +
                        (('?' + self.parsed.query) if self.parsed.query else ''))

        self.stream.set_nodelay(True)
        self.connection = HTTP1Connection(
            self.stream, True,
            HTTP1ConnectionParameters(
                no_keep_alive=True,
                max_header_size=self.max_header_size,
                decompress=self.request.decompress_response),
            self._sockaddr)
        start_line = httputil.RequestStartLine(self.request.method,
                                               req_path, 'HTTP/1.1')
        self.connection.write_headers(start_line, self.request.headers)
        if self.request.expect_100_continue:
            self._read_response()
        else:
            self._write_body(True)

    # Establish a tunnel through the proxy using the HTTP CONNECT method.
    @gen.coroutine
    def _on_proxy_connect(self, stream):
        if self.final_callback is None:
            # final_callback is cleared if we've hit our timeout.
            stream.close()
            return

        self.stream = stream
        self.stream.set_close_callback(self.on_connection_close)
        self._remove_timeout()
        if self.final_callback is None:
            return

        stream.set_nodelay(True)

        proxy_auth_header = None
        proxy_username = getattr(self.request, "proxy_username", None)
        proxy_password = getattr(self.request, "proxy_password", None)
        if proxy_username is not None and proxy_password is not None:
            auth = utf8(proxy_username) + b":" + utf8(proxy_password)
            proxy_auth_header = b"Basic " + base64.b64encode(auth)

        host_port_str = utf8(self.parsed_hostname) + b":" + utf8(str(self.parsed_port))
        headers = b"CONNECT {host_port} HTTP/1.1\r\nHost: {host_port}\r\n".format(host_port=host_port_str)
        if proxy_auth_header is not None:
            headers += b"Proxy-Authorization: " + proxy_auth_header + b"\r\n"
        headers += "\r\n"

        yield stream.write(headers)

        def _parse_headers(data):
            data = native_str(data.decode('latin1'))
            eol = data.find("\r\n")
            start_line = data[:eol]
            try:
                headers = httputil.HTTPHeaders.parse(data[eol:])
            except ValueError:
                # probably form split() if there was no ':' in the line
                raise httputil.HTTPInputException("Malformed HTTP headers: %r" %
                                                  data[eol:100])
            return start_line, headers

        response_data = yield stream.read_until_regex(b"\r?\n\r?\n")
        start_line, headers = _parse_headers(response_data)
        start_line = httputil.parse_response_start_line(start_line)
        if 200 <= start_line.code < 300:
            # Tunnel established. Continue with the main request.
            ssl_options = self._get_ssl_options(self.parsed.scheme)
            if ssl_options is not None:
                ssl_stream = yield stream.start_tls(False, ssl_options, server_hostname=self.parsed_hostname)
                self.io_loop.add_callback(self._on_connect, ssl_stream)
            else:
                self.io_loop.add_callback(self._on_connect, stream)
        else:
            content_length = headers.get("Content-Length")
            if content_length:
                content_length = int(content_length)
                if content_length > self._max_body_size:
                    raise httputil.HTTPInputException("Content-Length too long")
                response = ""
                while content_length > 0:
                    body = yield self.stream.read_bytes(content_length, partial=True)
                    content_length -= len(body)
                    response.append(body)
            else:
                yield stream.read_until_close()

            raise HTTPError(start_line.code, start_line.reason)

    def _write_body(self, start_read):
        if self.request.body is not None:
            self.connection.write(self.request.body)
            self.connection.finish()
        elif self.request.body_producer is not None:
            fut = self.request.body_producer(self.connection.write)
            if is_future(fut):
                def on_body_written(fut):
                    fut.result()
                    self.connection.finish()
                    if start_read:
                        self._read_response()
                self.io_loop.add_future(fut, on_body_written)
                return
            self.connection.finish()
        if start_read:
            self._read_response()

    def _read_response(self):
        # Ensure that any exception raised in read_response ends up in our
        # stack context.
        self.io_loop.add_future(
            self.connection.read_response(self),
            lambda f: f.result())

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
                value = HTTPError(599, "Stream closed")
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
                raise HTTPError(599, message)
            except HTTPError:
                self._handle_exception(*sys.exc_info())

    def headers_received(self, first_line, headers):
        if self.request.expect_100_continue and first_line.code == 100:
            self._write_body(False)
            return
        self.headers = headers
        self.code = first_line.code
        self.reason = first_line.reason

        if self.request.header_callback is not None:
            # Reassemble the start line.
            self.request.header_callback('%s %s %s\r\n' % first_line)
            for k, v in self.headers.get_all():
                self.request.header_callback("%s: %s\r\n" % (k, v))
            self.request.header_callback('\r\n')

    def finish(self):
        data = b''.join(self.chunks)
        self._remove_timeout()
        original_request = getattr(self.request, "original_request",
                                   self.request)
        if (self.request.follow_redirects and
            self.request.max_redirects > 0 and
                self.code in (301, 302, 303, 307)):
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
            if self.code in (302, 303):
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
            self.client.fetch(new_request, final_callback)
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
        if self.request.streaming_callback is not None:
            self.request.streaming_callback(chunk)
        else:
            self.chunks.append(chunk)


if __name__ == "__main__":
    AsyncHTTPClient.configure(SimpleAsyncHTTPClient)
    main()
