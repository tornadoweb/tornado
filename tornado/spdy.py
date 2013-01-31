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

"""

SPDY protocol utility code.

SPDY Protocol - Draft 3
http://www.chromium.org/spdy/spdy-protocol/spdy-protocol-draft3
"""

import logging
from struct import unpack

from tornado import stack_context
from tornado._zlib_stream import Inflater, Deflater

spdy_log = logging.getLogger("tornado.spdy")

DEFAULT_SPDY_VERSION = 2

DEFAULT_HEADER_ENCODING = 'UTF-8'

FRAME_HEADER_LEN = 8

# Note that full length control frames (16MB) can be large for implementations running on resource-limited hardware.
# In such cases, implementations MAY limit the maximum length frame supported. However,
# all implementations MUST be able to receive control frames of at least 8192 octets in length.
MAX_FRAME_LEN = 16 * 1024 * 1024
MIN_FRAME_LEN = 8 * 1024

TYPE_SYN_STREAM     = 1
TYPE_SYN_REPLY      = 2
TYPE_RST_STREAM     = 3
TYPE_SETTINGS       = 4
TYPE_NOOP           = 5
TYPE_PING           = 6
TYPE_GOAWAY         = 7
TYPE_HEADERS        = 8
TYPE_WINDOW_UPDATE  = 9
TYPE_CREDENTIAL     = 10

ERR_PROTOCOL_ERROR        = 1   # This is a generic error, and should only be used if a more specific error is not available.
ERR_INVALID_STREAM        = 2   # This is returned when a frame is received for a stream which is not active.
ERR_REFUSED_STREAM        = 3   # Indicates that the stream was refused before any processing has been done on the stream.
ERR_UNSUPPORTED_VERSION   = 4   # Indicates that the recipient of a stream does not support the SPDY version requested.
ERR_CANCEL                = 5   # Used by the creator of a stream to indicate that the stream is no longer needed.
ERR_INTERNAL_ERROR        = 6   # This is a generic error which can be used when the implementation has internally failed,
                                # not due to anything in the protocol.
ERR_FLOW_CONTROL_ERROR    = 7   # The endpoint detected that its peer violated the flow control protocol.
ERR_STREAM_IN_USE         = 8   # The endpoint received a SYN_REPLY for a stream already open.
ERR_STREAM_ALREADY_CLOSED = 9   # The endpoint received a data or SYN_REPLY frame for a stream which is half closed.
ERR_INVALID_CREDENTIALS   = 10  # The server received a request for a resource whose origin does not have valid credentials in the client certificate vector.
ERR_FRAME_TOO_LARGE       = 11  # The endpoint received a frame which this implementation could not support.
                                # If FRAME_TOO_LARGE is sent for a SYN_STREAM, HEADERS, or SYN_REPLY frame
                                # without fully processing the compressed portion of those frames,
                                # then the compression state will be out-of-sync with the other endpoint.
                                # In this case, senders of FRAME_TOO_LARGE MUST close the session.

FLAG_FIN            = 0x01  # marks this frame as the last frame to be transmitted on this stream
                            # and puts the sender in the half-closed (Section 2.3.6) state.
FLAG_UNIDIRECTIONAL = 0x02  # a stream created with this flag puts the recipient in the half-closed (Section 2.3.6) state.

def _bitmask(length, split, mask=0):
    invert = 1 if mask == 0 else 0
    b = str(mask)*split + str(invert)*(length-split)
    return int(b, 2)

_first_bit = _bitmask(8, 1, 1)
_first_2_bits = _bitmask(8, 2, 1)
_first_3_bits = _bitmask(8, 3, 1)
_last_15_bits = _bitmask(16, 1, 0)
_last_31_bits = _bitmask(32, 1, 0)

def _parse_ushort(data):
    return unpack(">H", data)[0]

def _parse_uint(data):
    return unpack(">I", data)[0]

class SPDYProtocolError(Exception):
    def __init__(self, err_msg, status_code=0):
        super(SPDYProtocolError, self).__init__(err_msg)

        self.status_code = status_code

class Frame(object):
    def __init__(self, conn, flags):
        self.conn = conn
        self.flags = flags

    def _on_body(self, data):
        raise NotImplementedError()

class ControlFrame(Frame):
    """
    +----------------------------------+
    |C| Version(15bits) | Type(16bits) |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |               Data               |
    +----------------------------------+
    """
    def __init__(self, conn, flags):
        super(ControlFrame, self).__init__(conn, flags)

    def _parse_headers(self, compressed_chunk):
        headers = {}

        if len(compressed_chunk) > self.conn.max_frame_size:
            raise SPDYProtocolError("The SYN_STREAM frame too large", ERR_FRAME_TOO_LARGE)

        chunk = self.conn.inflater.decompress(compressed_chunk)

        len_size = 4 if self.conn.version >= 3 else 2

        num_pairs = _parse_uint(chunk[0:len_size])

        pos = len_size

        for _ in xrange(num_pairs):
            len = _parse_uint(chunk[pos:pos+len_size])

            if len == 0:
                raise SPDYProtocolError("The length of header name must be greater than zero", ERR_PROTOCOL_ERROR)

            pos += len_size

            name = chunk[pos:pos+len].decode(self.conn.header_encoding)
            pos += len

            len = _parse_uint(chunk[pos:pos+len_size])
            pos += len_size

            values = chunk[pos:pos+len].decode(self.conn.header_encoding).split('\0') if len else []

            headers[name] = values

        return headers

class DataFrame(Frame):
    """
    +----------------------------------+
    |C|       Stream-ID (31bits)       |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |               Data               |
    +----------------------------------+
    """
    pass

class SyncStream(ControlFrame):
    """
    +------------------------------------+
    |1|    version    |         1        |
    +------------------------------------+
    |  Flags (8)  |  Length (24 bits)    |
    +------------------------------------+
    |X|           Stream-ID (31bits)     |
    +------------------------------------+
    |X| Associated-To-Stream-ID (31bits) |
    +------------------------------------+
    | Pri|Unused | Slot |                |
    +-------------------+                |
    | Number of Name/Value pairs (int32) |   <+
    +------------------------------------+    |
    |     Length of name (int32)         |    | This section is the "Name/Value
    +------------------------------------+    | Header Block", and is compressed.
    |           Name (string)            |    |
    +------------------------------------+    |
    |     Length of value  (int32)       |    |
    +------------------------------------+    |
    |          Value   (string)          |    |
    +------------------------------------+    |
    |           (repeats)                |   <+
    """
    def _on_body(self, chunk):
        self.stream_id = _parse_uint(chunk[0:4]) & _last_31_bits
        self.assoc_stream_id = _parse_uint(chunk[4:8]) & _last_31_bits
        self.priority = chunk[8] & (_first_3_bits if self.conn.version >= 3 else _first_2_bits)
        self.slot = chunk[9] if self.conn.version >= 3 else 0

        try:
            self.headers = self._parse_headers(chunk[10:])
        except SPDYProtocolError, ex:
            spdy_log.warn(ex.message)

            self.conn.reset_stream(self.stream_id, ex.status_code)
            self.conn.read_next_frame()

class SyncReply(ControlFrame):
    pass

class RstStream(ControlFrame):
    def __init__(self, conn, stream_id, status_code):
        super(RstStream, self).__init__(conn, 0)

        self.stream_id = stream_id
        self.status_code = status_code

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

class Credential(ControlFrame):
    pass

FRAME_TYPES = {
    TYPE_SYN_STREAM: SyncStream,
    TYPE_SYN_REPLY: SyncReply,
    TYPE_RST_STREAM: RstStream,
    TYPE_SETTINGS: Settings,
    TYPE_NOOP: Noop,
    TYPE_PING: Ping,
    TYPE_GOAWAY: GoAway,
    TYPE_HEADERS: Headers,
    TYPE_WINDOW_UPDATE: WindowUpdate,
    TYPE_CREDENTIAL: Credential,
}

class SPDYConnection(object):
    """Handles a connection to an SPDY client, executing SPDY frames.

    We parse SPDY frames, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, request_callback, no_keep_alive=False, xheaders=False, protocol=None,
                 server_side=True, version=None, max_frame_len=None, min_frame_len=None, header_encoding=None):
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
        self.version = version or DEFAULT_SPDY_VERSION
        self.max_frame_len = max_frame_len or MAX_FRAME_LEN
        self.min_frame_len = min_frame_len or MIN_FRAME_LEN
        self.header_encoding = header_encoding or DEFAULT_HEADER_ENCODING

        self.deflater = Deflater(version)
        self.inflater = Inflater(version)

        self._frame_callback = stack_context.wrap(self._on_frame_header)
        self.read_next_frame()

    def read_next_frame(self):
        self.stream.read_bytes(FRAME_HEADER_LEN, self._frame_callback)

    def _on_frame_header(self, chunk):
        #first bit: control or data frame?
        control_frame = (chunk[0] & _first_bit == _first_bit)

        try:
            if control_frame:
                #second byte (and rest of first, after the first bit): spdy version
                spdy_version = _parse_ushort(chunk[0:2]) & _last_15_bits

                #third and fourth byte: frame type
                frame_type = _parse_ushort(chunk[2:4])

                #fifth byte: flags
                flags = chunk[4]

                #sixth, seventh and eighth bytes: length
                frame_length = _parse_uint("\0" + chunk[5:8])

                frame_cls = FRAME_TYPES[frame_type]

                if spdy_version != self.version:
                    raise SPDYProtocolError("incorrect SPDY version")

                if not frame_type in FRAME_TYPES:
                    raise SPDYProtocolError("invalid frame type: {0}".format(frame_type))

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
        except SPDYProtocolError as ex:
            spdy_log.warn(ex.message)

            conn = self

            skip_frame_callback = stack_context.wrap(lambda data: conn.read_next_frame())

            self.stream.read_bytes(frame_length, skip_frame_callback)

    def reset_stream(self, stream_id, status_code):
        self.send_frame(RstStream(self, stream_id, status_code))

    def send_frame(self, frame):
        pass