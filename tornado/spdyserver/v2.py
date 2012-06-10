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

from tornado import gen, httputil, stack_context
from tornado.httpserver import BaseHTTPConnection, HTTPRequest
from tornado.spdysession import ResetStreamException
from tornado.spdysession.v2 import SPDYSession
from tornado.spdyutil import to_spdy_headers
from tornado.spdyutil.v2 import DataFrame, StatusCode, SynReplyFrame, SynStreamFrame
from tornado.util import b

import httplib


class SPDYServerProtocol(object):
    """A server protocol handler implementing the SPDYv2 specification, meant
    to be instantiated and passed to the `TCPServer` constructor.

    :arg bool xheaders: If ``True``, we support the ``X-Real-Ip`` and
        ``X-Scheme`` headers, which override the remote IP and HTTP scheme for
        all requests. These headers are useful when running Tornado behind a
        reverse proxy or load balancer.

    :arg float keep_alive_timeout: how long (in seconds) to maintain the TCP
        connection to the client when there are no active streams

    """
    def __init__(self, request_callback, xheaders=False, keep_alive_timeout=600):
        self.request_callback = request_callback
        self.xheaders = xheaders
        self.keep_alive_timeout = keep_alive_timeout

    def __call__(self, stream, address, server):
        _SPDYServerSession(stream, address, self, server.io_loop).listen()


class _SPDYServerSession(BaseHTTPConnection, SPDYSession):
    @gen.engine
    def __init__(self, conn, address, protocol, io_loop):
        SPDYSession.__init__(self, conn, address, protocol.keep_alive_timeout, io_loop)
        BaseHTTPConnection.__init__(self, conn, address, protocol.request_callback, protocol.xheaders)
        self.protocol = protocol
        self.stream_counter = 2

    def _handle_syn_stream(self, frame):
        if frame.data.unidirectional or frame.data.stream_id % 2 == 0:
            raise ResetStreamException(frame.data.stream_id, StatusCode.PROTOCOL_ERROR, error=False)
        stream = self.streams[frame.data.stream_id]
        if any([key not in stream.headers for key in ('Method', 'Url', 'Version', 'Scheme')]):
            SPDYConnection(stream).write_preamble(status_code=httplib.BAD_REQUEST, finished=True)
            self._close_stream(stream)

    def _handle_syn_reply(self, frame):
        raise ResetStreamException(frame.data.stream_id, StatusCode.PROTOCOL_ERROR)

    def _handle_ping(self, frame):
        if frame.data.id % 2 == 1:
            self.write(frame)

    def _handle_goaway(self, frame):
        self.remote_goaway = True

    def _finish_stream(self, stream):
        self._remote_close_stream(stream)
        request = HTTPRequest(
            method=stream.headers['Method'],
            uri=stream.headers['Url'],
            version=stream.headers['Version'],
            protocol=stream.headers['Scheme'],
            headers=stream.headers,
            body=b('').join(stream.body),
            remote_ip=self.address[0],
            xheaders=self.protocol.xheaders,
            priority=stream.priority,
            framing='spdy/2',
            connection=SPDYConnection(stream))
        httputil.parse_body_arguments(request.headers.get('Content-Type', ''), request.body, request.arguments, request.files)
        self.protocol.request_callback(request)


class SPDYConnection(object):
    """Implements the same interface as `HTTPConnection`, but adds a ``push``
    method that returns a new `SPDYConnection` for pushing a resource to the
    client.

    """
    def __init__(self, stream):
        self.stream = stream

    def set_close_callback(self, callback):
        self.stream.close_callback = stack_context.wrap(callback)

    @gen.engine
    def write(self, data, finished=False, callback=None):
        if self.stream.local_closed:
            return
        self.stream.session.write_data(self.stream.id, data, finished, callback)
        if finished:
            self._finish()

    def write_preamble(self, status_code, reason=None, version="HTTP/1.1", headers=None, finished=False, callback=None):
        if self.stream.local_closed:
            return
        spdy_headers = to_spdy_headers(headers or [])
        spdy_headers.update({
            "status": ["%i %s" % (status_code, httplib.responses.get(status_code, ''))],
            "version": [version],
        })
        if self.stream.associated_to_stream is None:
            self.stream.session.write(SynReplyFrame(self.stream.id, headers=spdy_headers, finished=finished), callback)
        else:
            spdy_headers['url'] = [self.stream.request.full_url()]
            self.stream.session.write(SynStreamFrame(self.stream.id, headers=spdy_headers, associated_to_stream_id=self.stream.associated_to_stream.id, unidirectional=True, finished=finished), callback)
        if finished:
            self._finish()

    def push(self, request):
        if not self.stream.local_closed and not self.stream.session.remote_goaway:
            return SPDYConnection(self.stream.session.add_stream(request, None, self.stream.id))

    def _finish(self):
        self.stream.session._local_close_stream(self.stream)
