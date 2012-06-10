#!/usr/bin/env python
#
# Copyright 2012 Alek Storm
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

from __future__ import absolute_import, division, with_statement

from tornado.httpserver import HTTPServerProtocol
from tornado.tcpserver import TCPServer
from tornado.spdyserver.v2 import SPDYServerProtocol


class SPDYServer(TCPServer):
    """A non-blocking, single-threaded HTTP server that uses SPDY framing if
    the client supports TLS NPN and advertises spdy/2 support. TLS NPN requires
    that Python 3.3+ and OpenSSL 1.0.1+ are installed.

    :arg callable request_callback: Called with a `SPDYConnection` parameter
        when a new request is received.

    :arg dict ssl_options: Keyword arguments to be passed to `ssl.wrap_socket`.
        Since negotiating SPDY requires a TLS handshake, this argument is
        required.

    All other keyword arguments are passed to `SPDYServerProtocol` and
    `HTTPServerProtocol`, where applicable.

    """
    def __init__(self, request_callback, ssl_options, io_loop=None,
                 no_keep_alive=False, xheaders=False, keep_alive_timeout=600):
        http_protocol = HTTPServerProtocol(request_callback,
                            no_keep_alive=no_keep_alive,
                            xheaders=xheaders)
        TCPServer.__init__(self, http_protocol,
            npn_protocols=[
                ('spdy/2', SPDYServerProtocol(request_callback,
                               xheaders=xheaders,
                               keep_alive_timeout=keep_alive_timeout)),
                ('http/1.1', http_protocol)],
            ssl_options=ssl_options,
            io_loop=io_loop)
