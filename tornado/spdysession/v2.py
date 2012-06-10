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

from tornado import gen
from tornado import stack_context
from tornado.escape import native_str
from tornado.httputil import HTTPHeaders
from tornado.spdysession import ResetStreamException, SPDYSessionException
from tornado.spdyutil import SPDYParseException, SPDYStreamParseException
from tornado.spdyutil.v2 import ControlFrameType, DataFrame, FrameType, GoawayFrame, parse_frame, RstStreamFrame, STATUS_CODE_MESSAGES, StatusCode, ZLibContext
from tornado.util import BytesIO, GzipDecompressor

import logging
import time


_DATA_FRAME_MAX_LENGTH = 0xffffff # 24 bits

class SPDYSession(object):
    """Accepts incoming SPDY frames and delegates to handlers. Implements logic
    common to both client and server endpoints. Should only be touched by those
    implementing custom non-HTTP protocols using SPDY framing.

    """
    def __init__(self, conn, address, keep_alive_timeout, io_loop):
        self.conn = conn
        self.keep_alive_timeout = keep_alive_timeout
        self.io_loop = io_loop
        self.streams = {}
        self.context = ZLibContext()
        self.timeout = None
        self.local_goaway = False
        self.remote_goaway = False
        self.last_good_stream_id = 0

    def _local_close_stream(self, stream):
        stream.local_closed = True
        if stream.remote_closed:
            self._close_stream(stream)

    def _remote_close_stream(self, stream):
        stream.remote_closed = True
        if stream.local_closed:
            self._close_stream(stream)

    def _close_stream(self, stream):
        if stream.timeout:
            self.io_loop.remove_timeout(stream.timeout)
        del self.streams[stream.id]
        if stream.close_callback:
            stream.close_callback()

    def _merge_headers(self, stream, spdy_headers, use_callback=True):
        stream.headers = stream.headers or HTTPHeaders()
        for name, values in spdy_headers.iteritems():
            name = HTTPHeaders.normalize_name(name)
            if name in stream.headers:
                raise ResetStreamException(stream.id, StatusCode.PROTOCOL_ERROR)
            for value in values:
                stream.headers.add(name, native_str(value))

    def _reset_stream(self, stream_id, status_code, error=True):
        message = STATUS_CODE_MESSAGES[status_code]
        logging.warning("Stream %i reset with status code: %i (%s)" % (stream_id, status_code, message))
        self.write(RstStreamFrame(stream_id, status_code=status_code))
        stream = self.streams.get(stream_id)
        if stream:
            self._close_stream(stream)
            for associated_stream in stream.associated_streams:
                self._close_stream(associated_stream)
            if error and stream.callback:
                with stream.callback.restore():
                    raise SPDYSessionException(message)

    def _get_stream(self, stream_id, exists, pushed=None, error=True):
        if stream_id == 0:
            raise ResetStreamException(stream_id, StatusCode.INVALID_STREAM, error)
        if pushed == (stream_id % 2 != 0):
            raise ResetStreamException(stream_id, StatusCode.PROTOCOL_ERROR, error)
        stream = self.streams.get(stream_id)
        if stream and not exists:
            raise ResetStreamException(stream_id, StatusCode.PROTOCOL_ERROR, error)
        if not stream and exists:
            raise ResetStreamException(stream_id, StatusCode.INVALID_STREAM, error)
        return stream

    def add_stream(self, request, callback, associated_to_stream_id=None, timeout=None, release_callback=None):
        associated_to_stream = self.streams[associated_to_stream_id] if associated_to_stream_id else None
        stream = SPDYStream(self.stream_counter, self, associated_to_stream=associated_to_stream, request=request, callback=callback, timeout=timeout, release_callback=release_callback)
        self.stream_counter = (self.stream_counter+2)%0xffffffff # wrap after 32 bits
        self.streams[stream.id] = stream
        if self.timeout is not None:
            self.io_loop.remove_timeout(self.timeout)
            self.timeout = None
        return stream

    def _handle_data(self, frame):
        pass

    def _handle_syn_stream(self, frame):
        pass

    def _handle_syn_reply(self, frame):
        pass

    def _handle_headers(self, frame):
        pass

    def _handle_settings(self, frame):
        pass

    def _handle_noop(self, frame):
        pass

    def _handle_ping(self, frame):
        pass

    def _handle_goaway(self, frame):
        pass

    def send_goaway(self):
        self.local_goaway = True
        self.write(GoawayFrame(last_good_stream_id=self.last_good_stream_id))

    def write(self, frame, callback=None):
        """Writes a frame of output to the stream."""
        if not self.conn.closed():
            self.conn.write(frame.serialize(self.context), stack_context.wrap(callback))

    @gen.engine
    def write_data(self, stream_id, data, finished=False, callback=None):
        callback = stack_context.wrap(callback)
        done = not data
        body = BytesIO(data)
        while not done:
            chunk = body.read(_DATA_FRAME_MAX_LENGTH)
            done = len(chunk) < _DATA_FRAME_MAX_LENGTH
            yield gen.Task(self.write, DataFrame(stream_id, chunk, finished=done and finished))
        if callback:
            callback()

    @gen.engine
    def listen(self):
        with stack_context.NullContext():
            while True:
                if len(self.streams) == 0 and self.timeout is None:
                    self.timeout = self.io_loop.add_timeout(time.time() + self.keep_alive_timeout, self.conn.close)
                while True:
                    try:
                        frame = yield gen.Task(parse_frame, self.conn, self.context)
                    except SPDYStreamParseException, e:
                        logging.warn("Received invalid SPDY frame on stream %i" % e.stream_id)
                        self._reset_stream(e.stream_id, StatusCode.PROTOCOL_ERROR)
                    except SPDYParseException:
                        logging.warn("Received invalid SPDY non-stream frame")
                        self.send_goaway()
                    else:
                        break
                try:
                    try:
                        if frame.type == FrameType.DATA:
                            stream = self._get_stream(frame.stream_id, exists=True)
                            data = frame.data
                            if stream.decompressor:
                                data = stream.decompressor(data)
                            stream.body.append(data)
                            self._handle_data(frame)
                            stream.data_received = True
                            if frame.finished and stream.id in self.streams:
                                self._finish_stream(stream)
                            continue
                    except ResetStreamException:
                        raise
                    except Exception:
                        logging.error("Uncaught exception while handling data frame on stream %i" % frame.stream_id)
                        raise ResetStreamException(frame.stream_id, StatusCode.INTERNAL_ERROR)
                    try:
                        if frame.control_type == ControlFrameType.SYN_STREAM:
                            if frame.version != 2:
                                raise ResetStreamException(frame.data.stream_id, StatusCode.UNSUPPORTED_VERSION, error=False)
                            if self.local_goaway:
                                raise ResetStreamException(frame.data.stream_id, StatusCode.CANCEL, error=False)
                            self.last_good_stream_id = frame.data.stream_id
                            self._get_stream(frame.data.stream_id, exists=False)
                            stream = SPDYStream(frame.data.stream_id, self)
                            self.streams[stream.id] = stream
                            if frame.data.unidirectional:
                                associated_to_stream = self._get_stream(frame.data.associated_to_stream_id, exists=True, pushed=False)
                                stream.associated_to_stream = associated_to_stream
                                associated_to_stream.associated_streams.append(stream)
                            stream.priority = frame.data.priority
                            self._merge_headers(stream, frame.data.headers, use_callback=False)
                            self._handle_syn_stream(frame)
                            if frame.data.finished and stream.id in self.streams:
                                self._finish_stream(stream)
                        elif frame.version != 2:
                            continue
                        if frame.control_type == ControlFrameType.SYN_REPLY:
                            stream = self._get_stream(frame.data.stream_id, exists=True, pushed=False)
                            if stream.headers is not None:
                                raise ResetStreamException(frame.data.stream_id, StatusCode.PROTOCOL_ERROR)
                            self._merge_headers(stream, frame.data.headers)
                            if 'gzip' in stream.headers.get('Content-Encoding', []):
                                stream.decompressor = GzipDecompressor()
                            self._handle_syn_reply(frame)
                            if frame.data.finished and stream.id in self.streams:
                                self._finish_stream(stream)
                        elif frame.control_type == ControlFrameType.RST_STREAM:
                            raise ResetStreamException(frame.data.stream_id, frame.data.status_code)
                        elif frame.control_type == ControlFrameType.HEADERS:
                            stream = self._get_stream(frame.data.stream_id, exists=True)
                            if stream.headers is None:
                                self._reset_stream(frame.data.stream_id, StatusCode.PROTOCOL_ERROR)
                            elif stream.associated_to_stream is None or stream.data_received:
                                self._merge_headers(stream, frame.data.headers)
                            self._handle_headers(frame)
                    except ResetStreamException:
                        raise
                    except Exception:
                        logging.error("Uncaught exception while handling control frame type %i on stream %i" % (frame.control_type, frame.data.stream_id))
                        raise ResetStreamException(frame.stream_id if frame.type == FrameType.DATA else frame.data.stream_id, StatusCode.INTERNAL_ERROR)
                    try:
                        if frame.control_type == ControlFrameType.SETTINGS:
                            self._handle_settings(frame)
                        elif frame.control_type == ControlFrameType.NOOP:
                            self._handle_noop(frame)
                        elif frame.control_type == ControlFrameType.PING:
                            self._handle_ping(frame)
                        elif frame.control_type == ControlFrameType.GOAWAY:
                            self._handle_goaway(frame)
                    except ResetStreamException:
                        raise
                    except Exception:
                        logging.error("Uncaught exception while handling non-stream control frame type %i" % frame.control_type)
                        self.send_goaway()
                except ResetStreamException, e:
                    self._reset_stream(e.stream_id, e.status_code, error=e.error)


class SPDYStream(object):
    def __init__(self, id, session, callback=None, local_closed=False, request=None, associated_to_stream=None, timeout=None, release_callback=None):
        self.id = id
        self.session = session
        self.callback = callback
        self.local_closed = local_closed
        self.remote_closed = False
        self.headers = None
        self.body = []
        self.start_time = time.time()
        self.request = request
        self.associated_streams = []
        self.associated_to_stream = associated_to_stream
        self.timeout = timeout
        self.decompressor = None
        self.close_callback = None
        self.release_callback = release_callback
        self.data_received = False
