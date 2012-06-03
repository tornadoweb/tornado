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

from tornado.httpclient import AsyncHTTPClient, main
from tornado.simple_httpclient import QueuedAsyncHTTPClient, _HTTPClientConnection
from tornado.spdyclient.v2 import SPDYClientSession
from tornado import gen, netutil, stack_context

import collections
import urlparse


_SPDYSessionParams = collections.namedtuple('SPDYSession', ['scheme', 'netloc', 'port', 'validate_cert', 'ca_certs', 'allow_ipv6', 'client_key', 'client_cert'])

class AsyncSPDYClient(QueuedAsyncHTTPClient):
    """An asynchronous HTTP client that uses SPDY framing if the server
    supports TLS NPN and advertises spdy/2 support. TLS NPN requires that
    Python 3.3+ and OpenSSL 1.0.1+ are installed.

    A key feature of SPDY is multiplexing multiple streams over a single TCP
    connection. If multiple requests are made at once to a single domain, the
    latter ones are delayed until the connection for the first is established
    and the TLS handshake is completed. If SPDY capability is discovered, the
    other requests are multiplexed over the connection. Otherwise, a new
    connection is started up for each pending request, and they are completed
    using traditional HTTP framing.

    To force a request to open a new TCP connection regardless of the protocol
    chosen, set `HTTPRequest.force_connection` to ``True``. Note that future
    requests to the same domain without this attribute set will use the new
    connection if it uses SPDY framing.

    :arg bool default_spdy: If ``True``, assume the server can speak SPDY even
        if NPN failed or the connection is not over TLS. Servers will probably
        not support this on the open Internet.

    :arg float keep_alive_timeout: how long (in seconds) to maintain the TCP
        connection to the server when there are no active streams

    """
    def initialize(self, default_spdy=False, keep_alive_timeout=600, **kwargs):
        self.keep_alive_timeout = keep_alive_timeout
        self._pending_connections = {}
        self._sessions = {}

        @gen.engine
        def handler(request, release_callback, final_callback):
            parsed = urlparse.urlsplit(request.url)
            # Requests are only shared over the same connection if they share
            # all these properties.
            session_params = _SPDYSessionParams(
                parsed.scheme, parsed.netloc, parsed.port,
                request.validate_cert, request.ca_certs, request.allow_ipv6,
                request.client_key, request.client_cert)
            session = self._sessions.get(session_params)
            if not session or session.remote_goaway:
                connection_params = request, release_callback, final_callback
                if (session_params not in self._pending_connections or
                    request.force_connection):
                    self._pending_connections[session_params] = [connection_params]
                    npn_protocols = ['spdy/2', 'http/1.1'] if netutil.SUPPORTS_NPN else None
                    conn, address = yield gen.Task(self._http_connect, request,
                                        npn_protocols=npn_protocols)

                    if ((parsed.scheme == 'http' and not default_spdy) or
                        (parsed.scheme == 'https' and
                         (not netutil.SUPPORTS_NPN or
                          conn.socket.selected_npn_protocol() == 'http/1.1'))):
                        for pending_connection_params in \
                            self._pending_connections[session_params]:
                            if connection_params == pending_connection_params:
                                _HTTPClientConnection(conn, address, self,
                                    request, release_callback,
                                    final_callback)
                            else:
                                # To prevent loop-internal variables from being
                                # overwritten by the time the callback is
                                # invoked, we wrap the whole thing in a closure.
                                def closure(pending_connection_params):
                                    def http_callback(params):
                                        conn, address = params
                                        _HTTPClientConnection(conn, address,
                                            self, request, release_callback,
                                            final_callback)
                                    request, release_callback, final_callback = pending_connection_params
                                    self._http_connect(request,
                                        callback=stack_context.wrap(
                                            http_callback))
                                closure(pending_connection_params)
                    else:
                        session = SPDYClientSession(conn, address, self,
                            session_params, self.io_loop)
                        self._sessions[session_params] = session
                        session.listen()
                        for request, release_callback, final_callback in \
                             self._pending_connections[session_params]:
                            session.add_stream(request, release_callback,
                                               final_callback)
                    del self._pending_connections[session_params]
                else:
                    self._pending_connections[session_params].append(
                        connection_params)
            else:
                session.add_stream(request, release_callback, final_callback)

        QueuedAsyncHTTPClient.initialize(self, handler, **kwargs)

    # TODO make sure this is really necessary - callbacks aren't preserved after IOLoop is stopped and restarted
    def reset(self):
        self._sessions.clear()
        self._pending_connections.clear()


if __name__ == "__main__":
    AsyncHTTPClient.configure(AsyncSPDYClient)
    main()
