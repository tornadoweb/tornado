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

from tornado.concurrent import Future
from tornado.escape import native_str
from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado.log import gen_log
from tornado import stack_context


class HTTP1Connection(object):
    """Handles a connection to an HTTP client, executing HTTP requests.

    We parse HTTP headers and bodies, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, delegate, no_keep_alive=False,
                 protocol=None):
        self.stream = stream
        self.address = address
        # Save the socket's address family now so we know how to
        # interpret self.address even after the stream is closed
        # and its socket attribute replaced with None.
        self.address_family = stream.socket.family
        self.delegate = delegate
        self.no_keep_alive = no_keep_alive
        if protocol:
            self.protocol = protocol
        elif isinstance(stream, iostream.SSLIOStream):
            self.protocol = "https"
        else:
            self.protocol = "http"
        self._disconnect_on_finish = False
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
                request_delegate = self.delegate.start_request(self)
                self._finish_future = Future()
                start_line, headers = self._parse_headers(header_data)
                self._disconnect_on_finish = not self._can_keep_alive(
                    start_line, headers)
                request_delegate.headers_received(start_line, headers)
                body_future = self._read_body(headers)
                if body_future is not None:
                    request_delegate.data_received((yield body_future))
                request_delegate.finish()
                yield self._finish_future
            except httputil.BadRequestException as e:
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

    def _can_keep_alive(self, start_line, headers):
        if self.no_keep_alive:
            return False
        connection_header = headers.get("Connection")
        if connection_header is not None:
            connection_header = connection_header.lower()
        if start_line.endswith("HTTP/1.1"):
            return connection_header != "close"
        elif ("Content-Length" in headers
              or start_line.startswith(("HEAD ", "GET "))):
            return connection_header == "keep-alive"
        return False

    def _finish_request(self):
        self._clear_request_state()
        if self._disconnect_on_finish:
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
            raise httputil.BadRequestException("Malformed HTTP headers")
        return start_line, headers

    def _read_body(self, headers):
        content_length = headers.get("Content-Length")
        if content_length:
            content_length = int(content_length)
            if content_length > self.stream.max_buffer_size:
                raise httputil.BadRequestException("Content-Length too long")
            if headers.get("Expect") == "100-continue":
                self.stream.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
            return self.stream.read_bytes(content_length)
        return None
