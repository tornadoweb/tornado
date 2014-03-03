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
                 **kwargs):
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self.protocol = protocol
        self.gzip = gzip
        TCPServer.__init__(self, io_loop=io_loop, ssl_options=ssl_options,
                           **kwargs)

    def handle_stream(self, stream, address):
        conn = HTTP1Connection(stream, address=address,
                               no_keep_alive=self.no_keep_alive,
                               protocol=self.protocol)
        conn.start_serving(self, gzip=self.gzip)

    def start_request(self, connection):
        return _ServerRequestAdapter(self, connection)

class _ServerRequestAdapter(httputil.HTTPMessageDelegate):
    """Adapts the `HTTPMessageDelegate` interface to the `HTTPServerRequest`
    interface expected by our clients.
    """
    def __init__(self, server, connection):
        self.server = server
        self.connection = connection

    def headers_received(self, start_line, headers):
        try:
            method, uri, version = start_line.split(" ")
        except ValueError:
            raise httputil.HTTPMessageException("Malformed HTTP request line")
        if not version.startswith("HTTP/"):
            raise httputil.HTTPMessageException(
                "Malformed HTTP version in HTTP Request-Line")
        # HTTPRequest wants an IP, not a full socket address
        if self.connection.address_family in (socket.AF_INET, socket.AF_INET6):
            remote_ip = self.connection.address[0]
        else:
            # Unix (or other) socket; fake the remote address
            remote_ip = '0.0.0.0'

        protocol = self.connection.protocol

        # xheaders can override the defaults
        if self.server.xheaders:
            # Squid uses X-Forwarded-For, others use X-Real-Ip
            ip = headers.get("X-Forwarded-For", remote_ip)
            ip = ip.split(',')[-1].strip()
            ip = headers.get("X-Real-Ip", ip)
            if netutil.is_valid_ip(ip):
                remote_ip = ip
            # AWS uses X-Forwarded-Proto
            proto_header = headers.get(
                "X-Scheme", headers.get("X-Forwarded-Proto", protocol))
            if proto_header in ("http", "https"):
                protocol = proto_header

        self.request = httputil.HTTPServerRequest(
            connection=self.connection, method=method, uri=uri, version=version,
            headers=headers, remote_ip=remote_ip, protocol=protocol)

    def data_received(self, chunk):
        assert not self.request.body
        self.request.body = chunk

    def finish(self):
        if self.request.method in ("POST", "PATCH", "PUT"):
            httputil.parse_body_arguments(
                self.request.headers.get("Content-Type", ""), self.request.body,
                self.request.body_arguments, self.request.files,
                self.request.headers)

            for k, v in self.request.body_arguments.items():
                self.request.arguments.setdefault(k, []).extend(v)

        self.server.request_callback(self.request)


HTTPRequest = httputil.HTTPServerRequest
