#!/usr/bin/env python
#
# Copyright 2011 Facebook
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

"""SPDY protocol utility code."""

from struct import unpack

from tornado import stack_context

DEFAULT_SPDY_VERSION = 2

FRAME_HEADER_LEN = 8

SYN_STREAM = 1
SYN_REPLY = 2
RST_STREAM = 3
SETTINGS = 4
NOOP = 5
PING = 6
GOAWAY = 7
HEADERS = 8
WINDOW_UPDATE = 9

def _bitmask(length, split, mask=0):
    invert = 1 if mask == 0 else 0
    b = str(mask)*split + str(invert)*(length-split)
    return int(b, 2)

_first_bit = _bitmask(8, 1, 1)
_last_15_bits = _bitmask(16, 1, 0)
_last_31_bits = _bitmask(32, 1, 0)

def _parse_ushort(data):
    return unpack(">H", data)[0]

def _parse_uint(data):
    return unpack(">I", data)[0]

class Frame(object):
    def __init__(self, conn, flags):
        self.conn = conn
        self.flags = flags

    def _on_body(self, data):
        raise NotImplementedError()

class ControlFrame(Frame):
    def __init__(self, conn, flags, stream_id):
        super(ControlFrame, self).__init__(conn, flags)

        self.stream_id = stream_id

class DataFrame(Frame):
    pass

class SyncStream(ControlFrame):
    pass

class SyncReply(ControlFrame):
    pass

class RstStream(ControlFrame):
    pass

class Settings(ControlFrame):
    pass

class Noop(ControlFrame):
    pass

class Ping(ControlFrame):
    pass

class GoAway(ControlFrame):
    pass

class Headers(ControlFrame):
    pass

class WindowUpdate(ControlFrame):
    pass

FRAME_TYPES = {
    SYN_STREAM: SyncStream,
    SYN_REPLY: SyncReply,
    RST_STREAM: RstStream,
    SETTINGS: Settings,
    NOOP: Noop,
    PING: Ping,
    GOAWAY: GoAway,
    HEADERS: Headers,
    WINDOW_UPDATE: WindowUpdate
}

class SPDYProtocolError(Exception):
    pass

class SPDYConnection(object):
    """Handles a connection to an SPDY client, executing SPDY frames.

    We parse SPDY frames, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, request_callback, no_keep_alive=False, xheaders=False, protocol=None,
                 server_side=True, version=DEFAULT_SPDY_VERSION):
        self.stream = stream
        self.address = address
        # Save the socket's address family now so we know how to
        # interpret self.address even after the stream is closed
        # and its socket attribute replaced with None.
        self.address_family = stream.socket.family
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self.protocol = protocol

        self.server_side = server_side
        self.version = version

        self._frame_callback = stack_context.wrap(self._on_frame_header)
        self.stream.read_bytes(FRAME_HEADER_LEN, self._frame_callback)

    def _on_frame_header(self, chunk):
        #first bit: control or data frame?
        control_frame = (chunk[0] & _first_bit == _first_bit)

        if control_frame:
            #second byte (and rest of first, after the first bit): spdy version
            spdy_version = _parse_ushort(chunk[0:2]) & _last_15_bits
            if spdy_version != self.version:
                raise SPDYProtocolError("incorrect SPDY version")

            #third and fourth byte: frame type
            frame_type = _parse_ushort(chunk[2:4])
            if not frame_type in FRAME_TYPES:
                raise SPDYProtocolError("invalid frame type: {0}".format(frame_type))

            #fifth byte: flags
            flags = chunk[4]

            #sixth, seventh and eighth bytes: length
            frame_length = _parse_uint("\0" + chunk[5:8])

            frame_cls = FRAME_TYPES[frame_type]

            if not frame_cls:
                raise SPDYProtocolError("unimplemented frame type: {0}".format(frame_type))

            frame = frame_cls(self, flags)
        else:
            #first four bytes, except the first bit: stream_id
            stream_id = _parse_uint(chunk[0:4]) & _last_31_bits

            #fifth byte: flags
            flags = chunk[4]

            #sixth, seventh and eighth bytes: length
            frame_length = _parse_uint("\0" + chunk[5:8])

            frame = DataFrame(self, flags, stream_id)

        frame_callback = stack_context.wrap(frame._on_body)

        self.stream.read_bytes(frame_length, frame_callback)