#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A non-blocking, single-threaded HTTP server.

Typical applications have little direct interaction with the `HTTPServer`
class except to start a server at the beginning of the process
(and even that is often done indirectly via `tornado.web.Application.listen`).

.. versionchanged:: 3.3

   The ``HTTPRequest`` class that used to live in this module has been moved
   to `tornado.httputil.HTTPServerRequest`.  The old name remains as an alias.
"""

from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.http1connection import HTTP1Connection
from tornado import httputil
from tornado import netutil
from tornado.tcpserver import TCPServer


class HTTPServer(TCPServer, httputil.HTTPServerConnectionDelegate):
    r"""A non-blocking, single-threaded HTTP server.

    A server is defined by a request callback that takes an HTTPRequest
    instance as an argument and writes a valid HTTP response with
    `.HTTPServerRequest.write`. `.HTTPServerRequest.finish` finishes the request (but does
    not necessarily close the connection in the case of HTTP/1.1 keep-alive
    requests). A simple example server that echoes back the URI you
    requested::

        import tornado.httpserver
        import tornado.ioloop

        def handle_request(request):
           message = "You requested %s\n" % request.uri
           request.write("HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (
                         len(message), message))
           request.finish()

        http_server = tornado.httpserver.HTTPServer(handle_request)
        http_server.listen(8888)
        tornado.ioloop.IOLoop.instance().start()

    `HTTPServer` is a very basic connection handler.  It parses the request
    headers and body, but the request callback is responsible for producing
    the response exactly as it will appear on the wire.  This affords
    maximum flexibility for applications to implement whatever parts
    of HTTP responses are required.

    `HTTPServer` supports keep-alive connections by default
    (automatically for HTTP/1.1, or for HTTP/1.0 when the client
    requests ``Connection: keep-alive``).  This means that the request
    callback must generate a properly-framed response, using either
    the ``Content-Length`` header or ``Transfer-Encoding: chunked``.
    Applications that are unable to frame their responses properly
    should instead return a ``Connection: close`` header in each
    response and pass ``no_keep_alive=True`` to the `HTTPServer`
    constructor.

    If ``xheaders`` is ``True``, we support the
    ``X-Real-Ip``/``X-Forwarded-For`` and
    ``X-Scheme``/``X-Forwarded-Proto`` headers, which override the
    remote IP and URI scheme/protocol for all requests.  These headers
    are useful when running Tornado behind a reverse proxy or load
    balancer.  The ``protocol`` argument can also be set to ``https``
    if Tornado is run behind an SSL-decoding proxy that does not set one of
    the supported ``xheaders``.

    To make this server serve SSL traffic, send the ``ssl_options`` dictionary
    argument with the arguments required for the `ssl.wrap_socket` method,
    including ``certfile`` and ``keyfile``.  (In Python 3.2+ you can pass
    an `ssl.SSLContext` object instead of a dict)::

       HTTPServer(applicaton, ssl_options={
           "certfile": os.path.join(data_dir, "mydomain.crt"),
           "keyfile": os.path.join(data_dir, "mydomain.key"),
       })

    `HTTPServer` initialization follows one of three patterns (the
    initialization methods are defined on `tornado.tcpserver.TCPServer`):

    1. `~tornado.tcpserver.TCPServer.listen`: simple single-process::

            server = HTTPServer(app)
            server.listen(8888)
            IOLoop.instance().start()

       In many cases, `tornado.web.Application.listen` can be used to avoid
       the need to explicitly create the `HTTPServer`.

    2. `~tornado.tcpserver.TCPServer.bind`/`~tornado.tcpserver.TCPServer.start`:
       simple multi-process::

            server = HTTPServer(app)
            server.bind(8888)
            server.start(0)  # Forks multiple sub-processes
            IOLoop.instance().start()

       When using this interface, an `.IOLoop` must *not* be passed
       to the `HTTPServer` constructor.  `~.TCPServer.start` will always start
       the server on the default singleton `.IOLoop`.

    3. `~tornado.tcpserver.TCPServer.add_sockets`: advanced multi-process::

            sockets = tornado.netutil.bind_sockets(8888)
            tornado.process.fork_processes(0)
            server = HTTPServer(app)
            server.add_sockets(sockets)
            IOLoop.instance().start()

       The `~.TCPServer.add_sockets` interface is more complicated,
       but it can be used with `tornado.process.fork_processes` to
       give you more flexibility in when the fork happens.
       `~.TCPServer.add_sockets` can also be used in single-process
       servers if you want to create your listening sockets in some
       way other than `tornado.netutil.bind_sockets`.

    """
    def __init__(self, request_callback, no_keep_alive=False, io_loop=None,
                 xheaders=False, ssl_options=None, protocol=None, gzip=False,
                 chunk_size=None, max_header_size=None, **kwargs):
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self.protocol = protocol
        self.gzip = gzip
        self.chunk_size = chunk_size
        self.max_header_size = max_header_size
        TCPServer.__init__(self, io_loop=io_loop, ssl_options=ssl_options,
                           **kwargs)

    def handle_stream(self, stream, address):
        conn = HTTP1Connection(stream, address=address, is_client=False,
                               no_keep_alive=self.no_keep_alive,
                               protocol=self.protocol,
                               chunk_size=self.chunk_size,
                               max_header_size=self.max_header_size)
        conn.start_serving(self, gzip=self.gzip)

    def start_request(self, connection):
        return _ServerRequestAdapter(self, connection)


class _ServerRequestAdapter(httputil.HTTPMessageDelegate):
    """Adapts the `HTTPMessageDelegate` interface to the interface expected
    by our clients.
    """
    def __init__(self, server, connection):
        self.server = server
        self.connection = connection
        self.request = None
        if isinstance(server.request_callback,
                      httputil.HTTPServerConnectionDelegate):
            self.delegate = server.request_callback.start_request(connection)
            self._chunks = None
        else:
            self.delegate = None
            self._chunks = []

    def _apply_xheaders(self, headers):
        """Rewrite the connection.remote_ip and connection.protocol fields.

        This is hacky, but the movement of logic between `HTTPServer`
        and `.Application` leaves us without a clean place to do this.
        """
        self._orig_remote_ip = self.connection.remote_ip
        self._orig_protocol = self.connection.protocol
        # Squid uses X-Forwarded-For, others use X-Real-Ip
        ip = headers.get("X-Forwarded-For", self.connection.remote_ip)
        ip = ip.split(',')[-1].strip()
        ip = headers.get("X-Real-Ip", ip)
        if netutil.is_valid_ip(ip):
            self.connection.remote_ip = ip
        # AWS uses X-Forwarded-Proto
        proto_header = headers.get(
            "X-Scheme", headers.get("X-Forwarded-Proto",
                                    self.connection.protocol))
        if proto_header in ("http", "https"):
            self.connection.protocol = proto_header

    def _unapply_xheaders(self):
        """Undo changes from `_apply_xheaders`.

        Xheaders are per-request so they should not leak to the next
        request on the same connection.
        """
        self.connection.remote_ip = self._orig_remote_ip
        self.connection.protocol = self._orig_protocol

    def headers_received(self, start_line, headers):
        if self.server.xheaders:
            self._apply_xheaders(headers)
        if self.delegate is None:
            self.request = httputil.HTTPServerRequest(
                connection=self.connection, start_line=start_line,
                headers=headers)
        else:
            return self.delegate.headers_received(start_line, headers)

    def data_received(self, chunk):
        if self.delegate is None:
            self._chunks.append(chunk)
        else:
            return self.delegate.data_received(chunk)

    def finish(self):
        if self.delegate is None:
            self.request.body = b''.join(self._chunks)
            self.request._parse_body()
            self.server.request_callback(self.request)
        else:
            self.delegate.finish()
        if self.server.xheaders:
            self._unapply_xheaders()


HTTPRequest = httputil.HTTPServerRequest
