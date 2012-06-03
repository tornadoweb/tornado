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

from tornado.escape import utf8, native_str
from tornado.httpclient import HTTPRequest, HTTPResponse
from tornado.httputil import HTTPHeaders
from tornado.simple_httpclient import TCPConnectionException
from tornado.spdysession.v2 import ResetStreamException, SPDYSession
from tornado.spdyutil import to_spdy_headers
from tornado.spdyutil.v2 import DataFrame, StatusCode, SynStreamFrame
from tornado.util import b, BytesIO
from tornado import gen, stack_context

import base64
import copy
import urlparse
import time


_DATA_FRAME_MAX_LENGTH = 0xffffff # 24 bits

class SPDYClientSession(SPDYSession):
    def __init__(self, conn, address, client, session_params, io_loop):
        SPDYSession.__init__(self, conn, address, client.keep_alive_timeout, io_loop)
        self.client = client
        self.session_params = session_params
        self.stream_counter = 1
        self.settings_key = address
        self.settings = {}

        def on_close():
            for stream in self.streams.itervalues():
                if stream.release_callback is not None:
                    stream.release_callback()
            del self.client._sessions[self.session_params]
            if len(self.streams) > 0:
                raise TCPConnectionException("Connection closed")
        self.conn.set_close_callback(on_close)

    def _handle_data(self, frame):
        stream = self.streams[frame.stream_id]
        if stream.request.streaming_callback:
            stream.request.streaming_callback(stream.body[0])
            stream.body = []

    def _handle_syn_stream(self, frame):
        stream = self.streams[frame.data.stream_id]
        if frame.data.stream_id % 2 == 1 or not frame.data.unidirectional or 'url' not in frame.data.headers or stream.data_received:
            raise ResetStreamException(frame.data.stream_id, StatusCode.PROTOCOL_ERROR, error=False)
        if stream.associated_to_stream.request.push_callback is None:
            raise ResetStreamException(frame.data.stream_id, StatusCode.CANCEL, error=False)
        stream.callback = stream.associated_to_stream.request.push_callback
        stream.request = HTTPRequest(url=frame.data.headers['url'][0], method='GET')

    def _handle_syn_reply(self, frame):
        if 'status' not in frame.data.headers or 'version' not in frame.data.headers:
            raise ResetStreamException(frame.data.stream_id, StatusCode.PROTOCOL_ERROR)

    def _handle_settings(self, frame):
        if frame.data.clear_previously_persisted_settings:
            self.settings.clear()
        for id, setting in frame.data.settings.iteritems():
            if setting.persist_value:
                self.settings[id] = setting.value

    def _handle_ping(self, frame):
        if frame.data.id % 2 == 0:
            self.conn.write(frame.serialize(self.context))

    def _handle_goaway(self, frame):
        if not self.remote_goaway:
            self.remote_goaway = True
            for id, stream in self.streams.items():
                if id > frame.data.last_good_stream_id and stream.headers is None:
                    self.client.fetch(stream.request, callback=stream.callback)
                    self._close_stream(stream)

    def _merge_headers(self, stream, spdy_headers, use_callback=True):
        SPDYSession._merge_headers(self, stream, spdy_headers, use_callback)
        if use_callback and stream.request.header_callback:
            for name, values in spdy_headers.iteritems():
                for value in values:
                    stream.request.header_callback("%s: %s\r\n" % (HTTPHeaders.normalize_name(name), native_str(value)))

    def _finish_stream(self, stream):
        self._remote_close_stream(stream)
        original_request = getattr(stream.request, "original_request",
                                   stream.request)
        status_code = int(stream.headers["Status"].split()[0])
        if stream.release_callback is not None:
            stream.release_callback()
        if (stream.request.follow_redirects and
            stream.request.max_redirects > 0 and
            status_code in (301, 302, 303, 307)):
            new_request = copy.copy(stream.request)
            new_request.url = urlparse.urljoin(stream.request.url,
                                               stream.headers["Location"])
            new_request.max_redirects -= 1
            new_request.headers.pop("Host", None)
            # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.4
            # client SHOULD make a GET request
            if status_code == 303:
                new_request.method = "GET"
                new_request.body = None
                for h in ("Content-Length", "Content-Type",
                          "Content-Encoding", "Transfer-Encoding"):
                    new_request.headers.pop(h, None)
            new_request.original_request = original_request
            self.client.fetch(new_request, stream.callback)
        else:
            if stream.associated_to_stream is not None:
                associated_to_url = stream.associated_to_stream.request.url
                associated_urls = None
            else:
                associated_to_url = None
                associated_urls = [associated_stream.request.url for associated_stream in stream.associated_streams]
            stream.callback(HTTPResponse(request=stream.request,
                                         code=status_code,
                                         headers=stream.headers,
                                         request_time=time.time()-stream.start_time,
                                         buffer=BytesIO(b('').join(stream.body)),
                                         effective_url=stream.request.url,
                                         framing='spdy/2',
                                         associated_to_url=associated_to_url,
                                         associated_urls=associated_urls))

    @gen.engine
    def add_stream(self, request, release_callback, final_callback):
        if self.timeout is not None:
            self.io_loop.remove_timeout(self.timeout)
            self.timeout = None
        for key in ('network_interface',
                    'proxy_host', 'proxy_port',
                    'proxy_username', 'proxy_password'):
            if getattr(request, key, None):
                raise NotImplementedError('%s not supported' % key)
        parsed = urlparse.urlsplit(request.url)
        if "Host" not in request.headers:
            if '@' in parsed.netloc:
                request.headers["Host"] = parsed.netloc.rpartition('@')[-1]
            else:
                request.headers["Host"] = parsed.netloc
        username, password = None, None
        if parsed.username is not None:
            username, password = parsed.username, parsed.password
        elif request.auth_username is not None:
            username = request.auth_username
            password = request.auth_password or ''
        if username is not None:
            auth = utf8(username) + b(":") + utf8(password)
            request.headers["Authorization"] = (b("Basic ") +
                                                     base64.b64encode(auth))
        if request.user_agent:
            request.headers["User-Agent"] = request.user_agent
        if not request.allow_nonstandard_methods:
            if request.method in ("POST", "PUT"):
                assert request.body is not None
            else:
                assert request.body is None
        if request.body is not None:
            request.headers["Content-Length"] = str(len(request.body))
        if (request.method == "POST" and
            "Content-Type" not in request.headers):
            request.headers["Content-Type"] = "application/x-www-form-urlencoded"

        request.headers.update({
            "Method": request.method,
            "Scheme": parsed.scheme,
            "Url": (parsed.path or '/') + (('?' + parsed.query) if parsed.query else ''),
            "Version": "HTTP/1.1",
        })
        request_headers = to_spdy_headers(request.headers.get_all())

        timeout = None
        if request.request_timeout:
            def on_timeout():
                self._reset_stream(stream.id, StatusCode.CANCEL, error=False)
                raise TCPConnectionException("Timeout")
            timeout = self.client.io_loop.add_timeout(
                time.time() + request.request_timeout,
                stack_context.wrap(on_timeout))

        stream = SPDYSession.add_stream(self, request, final_callback, timeout=timeout)
        finished = not bool(request.body)
        self.conn.write(SynStreamFrame(stream_id=stream.id, headers=request_headers, priority=request.priority, finished=finished).serialize(self.context))
        body = BytesIO(request.body)
        while not finished:
            chunk = body.read(_DATA_FRAME_MAX_LENGTH)
            finished = len(chunk) < _DATA_FRAME_MAX_LENGTH
            yield gen.Task(self.conn.write, DataFrame(stream.id, chunk, finished=finished).serialize(self.context))
        self._local_close_stream(stream)
