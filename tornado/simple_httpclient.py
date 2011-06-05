#!/usr/bin/env python
from __future__ import with_statement

from tornado.escape import utf8, _unicode, native_str
from tornado.httpclient import HTTPRequest, HTTPResponse, HTTPError, AsyncHTTPClient
from tornado.httputil import HTTPHeaders
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream, SSLIOStream
from tornado import stack_context
from tornado.util import b

import base64
import collections
import contextlib
import copy
import functools
import logging
import os.path
import re
import socket
import time
import urlparse
import zlib

try:
    from io import BytesIO  # python 3
except ImportError:
    from cStringIO import StringIO as BytesIO  # python 2

try:
    import ssl # python 2.6+
except ImportError:
    ssl = None

_DEFAULT_CA_CERTS = os.path.dirname(__file__) + '/ca-certificates.crt'

class SimpleAsyncHTTPClient(AsyncHTTPClient):
    """Non-blocking HTTP client with no external dependencies.

    This class implements an HTTP 1.1 client on top of Tornado's IOStreams.
    It does not currently implement all applicable parts of the HTTP
    specification, but it does enough to work with major web service APIs
    (mostly tested against the Twitter API so far).

    This class has not been tested extensively in production and
    should be considered somewhat experimental as of the release of
    tornado 1.2.  It is intended to become the default AsyncHTTPClient
    implementation in a future release.  It may either be used
    directly, or to facilitate testing of this class with an existing
    application, setting the environment variable
    USE_SIMPLE_HTTPCLIENT=1 will cause this class to transparently
    replace tornado.httpclient.AsyncHTTPClient.

    Some features found in the curl-based AsyncHTTPClient are not yet
    supported.  In particular, proxies are not supported, connections
    are not reused, and callers cannot select the network interface to be 
    used.

    Python 2.6 or higher is required for HTTPS support.  Users of Python 2.5
    should use the curl-based AsyncHTTPClient if HTTPS support is required.

    """
    def initialize(self, io_loop=None, max_clients=10,
                   max_simultaneous_connections=None,
                   hostname_mapping=None):
        """Creates a AsyncHTTPClient.

        Only a single AsyncHTTPClient instance exists per IOLoop
        in order to provide limitations on the number of pending connections.
        force_instance=True may be used to suppress this behavior.

        max_clients is the number of concurrent requests that can be in
        progress.  max_simultaneous_connections has no effect and is accepted
        only for compatibility with the curl-based AsyncHTTPClient.  Note
        that these arguments are only used when the client is first created,
        and will be ignored when an existing client is reused.

        hostname_mapping is a dictionary mapping hostnames to IP addresses.
        It can be used to make local DNS changes when modifying system-wide
        settings like /etc/hosts is not possible or desirable (e.g. in
        unittests).
        """
        self.io_loop = io_loop
        self.max_clients = max_clients
        self.queue = collections.deque()
        self.active = {}
        self.hostname_mapping = hostname_mapping

    def fetch(self, request, callback, **kwargs):
        if not isinstance(request, HTTPRequest):
            request = HTTPRequest(url=request, **kwargs)
        if not isinstance(request.headers, HTTPHeaders):
            request.headers = HTTPHeaders(request.headers)
        callback = stack_context.wrap(callback)
        self.queue.append((request, callback))
        self._process_queue()
        if self.queue:
            logging.debug("max_clients limit reached, request queued. "
                          "%d active, %d queued requests." % (
                    len(self.active), len(self.queue)))

    def _process_queue(self):
        with stack_context.NullContext():
            while self.queue and len(self.active) < self.max_clients:
                request, callback = self.queue.popleft()
                key = object()
                self.active[key] = (request, callback)
                _HTTPConnection(self.io_loop, self, request,
                                functools.partial(self._on_fetch_complete,
                                                  key, callback))

    def _on_fetch_complete(self, key, callback, response):
        del self.active[key]
        callback(response)
        self._process_queue()



class _HTTPConnection(object):
    _SUPPORTED_METHODS = set(["GET", "HEAD", "POST", "PUT", "DELETE"])

    def __init__(self, io_loop, client, request, callback):
        self.start_time = time.time()
        self.io_loop = io_loop
        self.client = client
        self.request = request
        self.callback = callback
        self.code = None
        self.headers = None
        self.chunks = None
        self._decompressor = None
        # Timeout handle returned by IOLoop.add_timeout
        self._timeout = None
        with stack_context.StackContext(self.cleanup):
            parsed = urlparse.urlsplit(_unicode(self.request.url))
            # urlsplit results have hostname and port results, but they
            # didn't support ipv6 literals until python 2.7.
            netloc = parsed.netloc
            if "@" in netloc:
                userpass, _, netloc = netloc.rpartition("@")
            match = re.match(r'^(.+):(\d+)$', netloc)
            if match:
                host = match.group(1)
                port = int(match.group(2))
            else:
                host = netloc
                port = 443 if parsed.scheme == "https" else 80
            if re.match(r'^\[.*\]$', host):
                # raw ipv6 addresses in urls are enclosed in brackets
                host = host[1:-1]
            if self.client.hostname_mapping is not None:
                host = self.client.hostname_mapping.get(host, host)

            if request.allow_ipv6:
                af = socket.AF_UNSPEC
            else:
                # We only try the first IP we get from getaddrinfo,
                # so restrict to ipv4 by default.
                af = socket.AF_INET

            addrinfo = socket.getaddrinfo(host, port, af, socket.SOCK_STREAM,
                                          0, 0)
            af, socktype, proto, canonname, sockaddr = addrinfo[0]

            if parsed.scheme == "https":
                ssl_options = {}
                if request.validate_cert:
                    ssl_options["cert_reqs"] = ssl.CERT_REQUIRED
                if request.ca_certs is not None:
                    ssl_options["ca_certs"] = request.ca_certs
                else:
                    ssl_options["ca_certs"] = _DEFAULT_CA_CERTS
                self.stream = SSLIOStream(socket.socket(af, socktype, proto),
                                          io_loop=self.io_loop,
                                          ssl_options=ssl_options)
            else:
                self.stream = IOStream(socket.socket(af, socktype, proto),
                                       io_loop=self.io_loop)
            timeout = min(request.connect_timeout, request.request_timeout)
            if timeout:
                self._connect_timeout = self.io_loop.add_timeout(
                    self.start_time + timeout,
                    self._on_timeout)
            self.stream.set_close_callback(self._on_close)
            self.stream.connect(sockaddr,
                                functools.partial(self._on_connect, parsed))

    def _on_timeout(self):
        self._timeout = None
        if self.callback is not None:
            self.callback(HTTPResponse(self.request, 599,
                                       error=HTTPError(599, "Timeout")))
            self.callback = None
        self.stream.close()

    def _on_connect(self, parsed):
        if self._timeout is not None:
            self.io_loop.remove_callback(self._timeout)
            self._timeout = None
        if self.request.request_timeout:
            self._timeout = self.io_loop.add_timeout(
                self.start_time + self.request.request_timeout,
                self._on_timeout)
        if (self.request.validate_cert and
            isinstance(self.stream, SSLIOStream)):
            match_hostname(self.stream.socket.getpeercert(),
                           parsed.hostname)
        if (self.request.method not in self._SUPPORTED_METHODS and
            not self.request.allow_nonstandard_methods):
            raise KeyError("unknown method %s" % self.request.method)
        for key in ('network_interface',
                    'proxy_host', 'proxy_port',
                    'proxy_username', 'proxy_password'):
            if getattr(self.request, key, None):
                raise NotImplementedError('%s not supported' % key)
        if "Host" not in self.request.headers:
            self.request.headers["Host"] = parsed.netloc
        username, password = None, None
        if parsed.username is not None:
            username, password = parsed.username, parsed.password
        elif self.request.auth_username is not None:
            username = self.request.auth_username
            password = self.request.auth_password
        if username is not None:
            auth = utf8(username) + b(":") + utf8(password)
            self.request.headers["Authorization"] = (b("Basic ") +
                                                     base64.b64encode(auth))
        if self.request.user_agent:
            self.request.headers["User-Agent"] = self.request.user_agent
        has_body = self.request.method in ("POST", "PUT")
        if has_body:
            assert self.request.body is not None
            self.request.headers["Content-Length"] = str(len(
                self.request.body))
        else:
            assert self.request.body is None
        if (self.request.method == "POST" and
            "Content-Type" not in self.request.headers):
            self.request.headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.request.use_gzip:
            self.request.headers["Accept-Encoding"] = "gzip"
        req_path = ((parsed.path or '/') +
                (('?' + parsed.query) if parsed.query else ''))
        request_lines = [utf8("%s %s HTTP/1.1" % (self.request.method,
                                                  req_path))]
        for k, v in self.request.headers.get_all():
            line = utf8(k) + b(": ") + utf8(v)
            if b('\n') in line:
                raise ValueError('Newline in header: ' + repr(line))
            request_lines.append(line)
        self.stream.write(b("\r\n").join(request_lines) + b("\r\n\r\n"))
        if has_body:
            self.stream.write(self.request.body)
        self.stream.read_until(b("\r\n\r\n"), self._on_headers)

    @contextlib.contextmanager
    def cleanup(self):
        try:
            yield
        except Exception, e:
            logging.warning("uncaught exception", exc_info=True)
            if self.callback is not None:
                callback = self.callback
                self.callback = None
                callback(HTTPResponse(self.request, 599, error=e))

    def _on_close(self):
        if self.callback is not None:
            callback = self.callback
            self.callback = None
            callback(HTTPResponse(self.request, 599,
                                  error=HTTPError(599, "Connection closed")))

    def _on_headers(self, data):
        data = native_str(data.decode("latin1"))
        first_line, _, header_data = data.partition("\r\n")
        match = re.match("HTTP/1.[01] ([0-9]+)", first_line)
        assert match
        self.code = int(match.group(1))
        self.headers = HTTPHeaders.parse(header_data)
        if self.request.header_callback is not None:
            for k, v in self.headers.get_all():
                self.request.header_callback("%s: %s\r\n" % (k, v))
        if (self.request.use_gzip and
            self.headers.get("Content-Encoding") == "gzip"):
            # Magic parameter makes zlib module understand gzip header
            # http://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib
            self._decompressor = zlib.decompressobj(16+zlib.MAX_WBITS)
        if self.headers.get("Transfer-Encoding") == "chunked":
            self.chunks = []
            self.stream.read_until(b("\r\n"), self._on_chunk_length)
        elif "Content-Length" in self.headers:
            self.stream.read_bytes(int(self.headers["Content-Length"]),
                                   self._on_body)
        else:
            raise Exception("No Content-length or chunked encoding, "
                            "don't know how to read %s", self.request.url)

    def _on_body(self, data):
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
            self._timeout = None
        if self._decompressor:
            data = self._decompressor.decompress(data)
        if self.request.streaming_callback:
            if self.chunks is None:
                # if chunks is not None, we already called streaming_callback
                # in _on_chunk_data
                self.request.streaming_callback(data)
            buffer = BytesIO()
        else:
            buffer = BytesIO(data) # TODO: don't require one big string?
        original_request = getattr(self.request, "original_request",
                                   self.request)
        if (self.request.follow_redirects and
            self.request.max_redirects > 0 and
            self.code in (301, 302)):
            new_request = copy.copy(self.request)
            new_request.url = urlparse.urljoin(self.request.url,
                                               self.headers["Location"])
            new_request.max_redirects -= 1
            del new_request.headers["Host"]
            new_request.original_request = original_request
            self.client.fetch(new_request, self.callback)
            self.callback = None
            return
        response = HTTPResponse(original_request,
                                self.code, headers=self.headers,
                                buffer=buffer,
                                effective_url=self.request.url)
        self.callback(response)
        self.callback = None

    def _on_chunk_length(self, data):
        # TODO: "chunk extensions" http://tools.ietf.org/html/rfc2616#section-3.6.1
        length = int(data.strip(), 16)
        if length == 0:
            # all the data has been decompressed, so we don't need to
            # decompress again in _on_body
            self._decompressor = None
            self._on_body(b('').join(self.chunks))
        else:
            self.stream.read_bytes(length + 2,  # chunk ends with \r\n
                              self._on_chunk_data)

    def _on_chunk_data(self, data):
        assert data[-2:] == b("\r\n")
        chunk = data[:-2]
        if self._decompressor:
            chunk = self._decompressor.decompress(chunk)
        if self.request.streaming_callback is not None:
            self.request.streaming_callback(chunk)
        else:
            self.chunks.append(chunk)
        self.stream.read_until(b("\r\n"), self._on_chunk_length)


# match_hostname was added to the standard library ssl module in python 3.2.
# The following code was backported for older releases and copied from
# https://bitbucket.org/brandon/backports.ssl_match_hostname
class CertificateError(ValueError):
    pass

def _dnsname_to_pat(dn):
    pats = []
    for frag in dn.split(r'.'):
        if frag == '*':
            # When '*' is a fragment by itself, it matches a non-empty dotless
            # fragment.
            pats.append('[^.]+')
        else:
            # Otherwise, '*' matches any dotless fragment.
            frag = re.escape(frag)
            pats.append(frag.replace(r'\*', '[^.]*'))
    return re.compile(r'\A' + r'\.'.join(pats) + r'\Z', re.IGNORECASE)

def match_hostname(cert, hostname):
    """Verify that *cert* (in decoded format as returned by
    SSLSocket.getpeercert()) matches the *hostname*.  RFC 2818 rules
    are mostly followed, but IP addresses are not accepted for *hostname*.

    CertificateError is raised on failure. On success, the function
    returns nothing.
    """
    if not cert:
        raise ValueError("empty or no certificate")
    dnsnames = []
    san = cert.get('subjectAltName', ())
    for key, value in san:
        if key == 'DNS':
            if _dnsname_to_pat(value).match(hostname):
                return
            dnsnames.append(value)
    if not san:
        # The subject is only checked when subjectAltName is empty
        for sub in cert.get('subject', ()):
            for key, value in sub:
                # XXX according to RFC 2818, the most specific Common Name
                # must be used.
                if key == 'commonName':
                    if _dnsname_to_pat(value).match(hostname):
                        return
                    dnsnames.append(value)
    if len(dnsnames) > 1:
        raise CertificateError("hostname %r "
            "doesn't match either of %s"
            % (hostname, ', '.join(map(repr, dnsnames))))
    elif len(dnsnames) == 1:
        raise CertificateError("hostname %r "
            "doesn't match %r"
            % (hostname, dnsnames[0]))
    else:
        raise CertificateError("no appropriate commonName or "
            "subjectAltName fields were found")

def main():
    from tornado.options import define, options, parse_command_line
    define("print_headers", type=bool, default=False)
    define("print_body", type=bool, default=True)
    define("follow_redirects", type=bool, default=True)
    args = parse_command_line()
    client = SimpleAsyncHTTPClient()
    io_loop = IOLoop.instance()
    for arg in args:
        def callback(response):
            io_loop.stop()
            response.rethrow()
            if options.print_headers:
                print response.headers
            if options.print_body:
                print response.body
        client.fetch(arg, callback, follow_redirects=options.follow_redirects)
        io_loop.start()

if __name__ == "__main__":
    main()
