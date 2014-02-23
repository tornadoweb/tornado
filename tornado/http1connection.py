#!/usr/bin/env python
#
# Copyright 2014 Facebook
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

from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.concurrent import Future
from tornado.escape import native_str
from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado.log import gen_log
from tornado import netutil
from tornado import stack_context


class _BadRequestException(Exception):
    """Exception class for malformed HTTP requests."""
    pass


class HTTP1Connection(object):
    """Handles a connection to an HTTP client, executing HTTP requests.

    We parse HTTP headers and bodies, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, request_callback, no_keep_alive=False,
                 xheaders=False, protocol=None):
        self.stream = stream
        self.address = address
        # Save the socket's address family now so we know how to
        # interpret self.address even after the stream is closed
        # and its socket attribute replaced with None.
        self.address_family = stream.socket.family
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        if protocol:
            self.protocol = protocol
        elif isinstance(stream, iostream.SSLIOStream):
            self.protocol = "https"
        else:
            self.protocol = "http"
        self._clear_request_state()
        self.stream.set_close_callback(self._on_connection_close)
        self._finish_future = None
        # Register the future on the IOLoop so its errors get logged.
        stream.io_loop.add_future(self._process_requests(),
                                  lambda f: f.result())

    @gen.coroutine
    def _process_requests(self):
        while True:
            try:
                header_data = yield self.stream.read_until(b"\r\n\r\n")
                self._finish_future = Future()
                start_line, headers = self._parse_headers(header_data)
                request = self._make_request(start_line, headers)
                self._request = request
                body_future = self._read_body(headers)
                if body_future is not None:
                    request.body = yield body_future
                self._parse_body(request)
                self.request_callback(request)
                yield self._finish_future
            except _BadRequestException as e:
                gen_log.info("Malformed HTTP request from %r: %s",
                             self.address, e)
                self.close()
                return
            except iostream.StreamClosedError:
                self.close()
                return


    def _clear_request_state(self):
        """Clears the per-request state.

        This is run in between requests to allow the previous handler
        to be garbage collected (and prevent spurious close callbacks),
        and when the connection is closed (to break up cycles and
        facilitate garbage collection in cpython).
        """
        self._request = None
        self._request_finished = False
        self._write_callback = None
        self._close_callback = None

    def set_close_callback(self, callback):
        """Sets a callback that will be run when the connection is closed.

        Use this instead of accessing
        `HTTPConnection.stream.set_close_callback
        <.BaseIOStream.set_close_callback>` directly (which was the
        recommended approach prior to Tornado 3.0).
        """
        self._close_callback = stack_context.wrap(callback)

    def _on_connection_close(self):
        if self._close_callback is not None:
            callback = self._close_callback
            self._close_callback = None
            callback()
        if self._finish_future is not None and not self._finish_future.done():
            self._finish_future.set_result(None)
        # Delete any unfinished callbacks to break up reference cycles.
        self._clear_request_state()

    def close(self):
        self.stream.close()
        # Remove this reference to self, which would otherwise cause a
        # cycle and delay garbage collection of this connection.
        self._clear_request_state()

    def write(self, chunk, callback=None):
        """Writes a chunk of output to the stream."""
        if not self.stream.closed():
            self._write_callback = stack_context.wrap(callback)
            self.stream.write(chunk, self._on_write_complete)

    def finish(self):
        """Finishes the request."""
        self._request_finished = True
        # No more data is coming, so instruct TCP to send any remaining
        # data immediately instead of waiting for a full packet or ack.
        self.stream.set_nodelay(True)
        if not self.stream.writing():
            self._finish_request()

    def _on_write_complete(self):
        if self._write_callback is not None:
            callback = self._write_callback
            self._write_callback = None
            callback()
        # _on_write_complete is enqueued on the IOLoop whenever the
        # IOStream's write buffer becomes empty, but it's possible for
        # another callback that runs on the IOLoop before it to
        # simultaneously write more data and finish the request.  If
        # there is still data in the IOStream, a future
        # _on_write_complete will be responsible for calling
        # _finish_request.
        if self._request_finished and not self.stream.writing():
            self._finish_request()

    def _finish_request(self):
        if self.no_keep_alive or self._request is None:
            disconnect = True
        else:
            connection_header = self._request.headers.get("Connection")
            if connection_header is not None:
                connection_header = connection_header.lower()
            if self._request.supports_http_1_1():
                disconnect = connection_header == "close"
            elif ("Content-Length" in self._request.headers
                    or self._request.method in ("HEAD", "GET")):
                disconnect = connection_header != "keep-alive"
            else:
                disconnect = True
        self._clear_request_state()
        if disconnect:
            self.close()
            return
        # Turn Nagle's algorithm back on, leaving the stream in its
        # default state for the next request.
        self.stream.set_nodelay(False)
        self._finish_future.set_result(None)

    def _parse_headers(self, data):
        data = native_str(data.decode('latin1'))
        eol = data.find("\r\n")
        start_line = data[:eol]
        try:
            headers = httputil.HTTPHeaders.parse(data[eol:])
        except ValueError:
            # probably form split() if there was no ':' in the line
            raise _BadRequestException("Malformed HTTP headers")
        return start_line, headers

    def _make_request(self, start_line, headers):
        try:
            method, uri, version = start_line.split(" ")
        except ValueError:
            raise _BadRequestException("Malformed HTTP request line")
        if not version.startswith("HTTP/"):
            raise _BadRequestException("Malformed HTTP version in HTTP Request-Line")
        # HTTPRequest wants an IP, not a full socket address
        if self.address_family in (socket.AF_INET, socket.AF_INET6):
            remote_ip = self.address[0]
        else:
            # Unix (or other) socket; fake the remote address
            remote_ip = '0.0.0.0'

        protocol = self.protocol

        # xheaders can override the defaults
        if self.xheaders:
            # Squid uses X-Forwarded-For, others use X-Real-Ip
            ip = headers.get("X-Forwarded-For", remote_ip)
            ip = ip.split(',')[-1].strip()
            ip = headers.get("X-Real-Ip", ip)
            if netutil.is_valid_ip(ip):
                remote_ip = ip
            # AWS uses X-Forwarded-Proto
            proto_header = headers.get(
                "X-Scheme", headers.get("X-Forwarded-Proto", self.protocol))
            if proto_header in ("http", "https"):
                protocol = proto_header

        return httputil.HTTPServerRequest(
            connection=self, method=method, uri=uri, version=version,
            headers=headers, remote_ip=remote_ip, protocol=protocol)

    def _read_body(self, headers):
        content_length = headers.get("Content-Length")
        if content_length:
            content_length = int(content_length)
            if content_length > self.stream.max_buffer_size:
                raise _BadRequestException("Content-Length too long")
            if headers.get("Expect") == "100-continue":
                self.stream.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
            return self.stream.read_bytes(content_length)
        return None

    def _parse_body(self, request):
        if self._request.method in ("POST", "PATCH", "PUT"):
            httputil.parse_body_arguments(
                self._request.headers.get("Content-Type", ""), request.body,
                self._request.body_arguments, self._request.files)

            for k, v in self._request.body_arguments.items():
                self._request.arguments.setdefault(k, []).extend(v)
