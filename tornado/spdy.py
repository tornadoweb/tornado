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


1. SPDY Protocol - Draft 2
    http://www.chromium.org/spdy/spdy-protocol/spdy-protocol-draft2

2. SPDY Protocol - Draft 3
    http://www.chromium.org/spdy/spdy-protocol/spdy-protocol-draft3
"""

import logging
import socket
import time
import numbers
import functools
from struct import pack, unpack

from tornado.httputil import HTTPHeaders, parse_body_arguments
from tornado.httpserver import HTTPServer, HTTPRequest
from tornado.iostream import StreamClosedError
from tornado.util import bytes_type

try:
    from tornado._zlib_stream import Inflater, Deflater
except ImportError:
    from tornado.c_zlib import Compressor, Decompressor

    class Deflater(Compressor):
        def __init__(self, version, level):
            Compressor.__init__(self, level, HEADER_ZLIB_DICT_2 if version == 2 else HEADER_ZLIB_DICT_3)

        def compress(self, chunk):
            return self.__call__(chunk)

    class Inflater(Decompressor):
        def __init__(self, version):
            Decompressor.__init__(self, HEADER_ZLIB_DICT_2 if version == 2 else HEADER_ZLIB_DICT_3)

        def decompress(self, chunk):
            return self.__call__(chunk)

spdy_log = logging.getLogger("tornado.spdy")

SPDY_VERSION_AUTO = 0
SPDY_VERSION_2 = 2
SPDY_VERSION_3 = 3

DEFAULT_HEADER_ENCODING = 'UTF-8'
DEFAULT_HEADER_COMPRESS_LEVEL = -1

FRAME_HEADER_LEN = 8

# Note that full length control frames (16MB) can be large for implementations running on resource-limited hardware.
# In such cases, implementations MAY limit the maximum length frame supported. However,
# all implementations MUST be able to receive control frames of at least 8192 octets in length.
MAX_FRAME_LEN = 16 * 1024 * 1024
MIN_FRAME_LEN = 8 * 1024

TYPE_SYN_STREAM = 1
TYPE_SYN_REPLY = 2
TYPE_RST_STREAM = 3
TYPE_SETTINGS = 4
TYPE_NOOP = 5
TYPE_PING = 6
TYPE_GOAWAY = 7
TYPE_HEADERS = 8
TYPE_WINDOW_UPDATE = 9
TYPE_CREDENTIAL = 10

PRI_LOWEST = 'lowest'
PRI_LOW = 'low'
PRI_HIGH = 'high'
PRI_HIGHEST = 'highest'

PRIORITIES = {
    2: {
        PRI_LOWEST: 0,
        PRI_LOW: 1,
        PRI_HIGH: 2,
        PRI_HIGHEST: 3
    },
    3: {
        PRI_LOWEST: 0,
        PRI_LOW: 3,
        PRI_HIGH: 5,
        PRI_HIGHEST: 7
    }
}


def _priority(pri, version):
    if isinstance(pri, numbers.Number):
        return pri

    return PRIORITIES[version][str(pri)]

ERR_PROTOCOL_ERROR = 1          # This is a generic error, and should only be used if a more specific error is not available.
ERR_INVALID_STREAM = 2          # This is returned when a frame is received for a stream which is not active.
ERR_REFUSED_STREAM = 3          # Indicates that the stream was refused before any processing has been done on the stream.
ERR_UNSUPPORTED_VERSION = 4     # Indicates that the recipient of a stream does not support the SPDY version requested.
ERR_CANCEL = 5                  # Used by the creator of a stream to indicate that the stream is no longer needed.
ERR_INTERNAL_ERROR = 6          # This is a generic error which can be used when the implementation has internally failed,
                                # not due to anything in the protocol.
ERR_FLOW_CONTROL_ERROR = 7      # The endpoint detected that its peer violated the flow control protocol.
ERR_STREAM_IN_USE = 8           # The endpoint received a SYN_REPLY for a stream already open.
ERR_STREAM_ALREADY_CLOSED = 9   # The endpoint received a data or SYN_REPLY frame for a stream which is half closed.
ERR_INVALID_CREDENTIALS = 10    # The server received a request for a resource whose origin does not have valid credentials in the client certificate vector.
ERR_FRAME_TOO_LARGE = 11        # The endpoint received a frame which this implementation could not support.
                                # If FRAME_TOO_LARGE is sent for a SYN_STREAM, HEADERS, or SYN_REPLY frame
                                # without fully processing the compressed portion of those frames,
                                # then the compression state will be out-of-sync with the other endpoint.
                                # In this case, senders of FRAME_TOO_LARGE MUST close the session.

FLAG_FIN = 0x01                 # marks this frame as the last frame to be transmitted on this stream
                                # and puts the sender in the half-closed (Section 2.3.6) state.
FLAG_UNIDIRECTIONAL = 0x02      # a stream created with this flag puts the recipient in the half-closed (Section 2.3.6) state.

FLAG_SETTINGS_CLEAR_PREVIOUSLY_PERSISTED_SETTINGS = 0x01 # When set, the client should clear any previously persisted SETTINGS ID/Value pairs.

SETTINGS_UPLOAD_BANDWIDTH = 1                # allows the sender to send its expected upload bandwidth on this channel.
SETTINGS_DOWNLOAD_BANDWIDTH = 2              # allows the sender to send its expected download bandwidth on this channel.
SETTINGS_ROUND_TRIP_TIME = 3                 # allows the sender to send its expected round-trip-time on this channel.
SETTINGS_MAX_CONCURRENT_STREAMS = 4          # allows the sender to inform the remote endpoint the maximum number of concurrent streams which it will allow.
SETTINGS_CURRENT_CWND = 5                    # allows the sender to inform the remote endpoint of the current CWND value.
SETTINGS_DOWNLOAD_RETRANS_RATE = 6           # downstream byte retransmission rate in percentage
SETTINGS_INITIAL_WINDOW_SIZE = 7             # initial window size in bytes
SETTINGS_CLIENT_CERTIFICATE_VECTOR_SIZE = 8  # allows the server to inform the client if the new size of the client certificate vector.

FLAG_SETTINGS_PERSIST_VALUE = 0x01
FLAG_SETTINGS_PERSISTED = 0x02

IGNORE_ALL_STREAMS = 0

GOAWAY_STATUS_OK = 0                # This is a normal session teardown.
GOAWAY_STATUS_PROTOCOL_ERROR = 1    # This is a generic error, and should only be used if a more specific error is not available.
GOAWAY_STATUS_INTERNAL_ERROR = 2    # This is a generic error which can be used when the implementation has internally failed, not due to anything in the protocol.

WINDOW_SIZE_MAX = 0x7fffffff
WINDOW_SIZE_DEFAULT = 65536

HEADER_ZLIB_DICT_2 =\
"optionsgetheadpostputdeletetraceacceptaccept-charsetaccept-encodingaccept-"\
"languageauthorizationexpectfromhostif-modified-sinceif-matchif-none-matchi"\
"f-rangeif-unmodifiedsincemax-forwardsproxy-authorizationrangerefererteuser"\
"-agent10010120020120220320420520630030130230330430530630740040140240340440"\
"5406407408409410411412413414415416417500501502503504505accept-rangesageeta"\
"glocationproxy-authenticatepublicretry-afterservervarywarningwww-authentic"\
"ateallowcontent-basecontent-encodingcache-controlconnectiondatetrailertran"\
"sfer-encodingupgradeviawarningcontent-languagecontent-lengthcontent-locati"\
"oncontent-md5content-rangecontent-typeetagexpireslast-modifiedset-cookieMo"\
"ndayTuesdayWednesdayThursdayFridaySaturdaySundayJanFebMarAprMayJunJulAugSe"\
"pOctNovDecchunkedtext/htmlimage/pngimage/jpgimage/gifapplication/xmlapplic"\
"ation/xhtmltext/plainpublicmax-agecharset=iso-8859-1utf-8gzipdeflateHTTP/1"\
".1statusversionurl\0"

HEADER_ZLIB_DICT_3 =\
"\x00\x00\x00\x07\x6f\x70\x74\x69\x6f\x6e\x73\x00\x00\x00\x04\x68"\
"\x65\x61\x64\x00\x00\x00\x04\x70\x6f\x73\x74\x00\x00\x00\x03\x70"\
"\x75\x74\x00\x00\x00\x06\x64\x65\x6c\x65\x74\x65\x00\x00\x00\x05"\
"\x74\x72\x61\x63\x65\x00\x00\x00\x06\x61\x63\x63\x65\x70\x74\x00"\
"\x00\x00\x0e\x61\x63\x63\x65\x70\x74\x2d\x63\x68\x61\x72\x73\x65"\
"\x74\x00\x00\x00\x0f\x61\x63\x63\x65\x70\x74\x2d\x65\x6e\x63\x6f"\
"\x64\x69\x6e\x67\x00\x00\x00\x0f\x61\x63\x63\x65\x70\x74\x2d\x6c"\
"\x61\x6e\x67\x75\x61\x67\x65\x00\x00\x00\x0d\x61\x63\x63\x65\x70"\
"\x74\x2d\x72\x61\x6e\x67\x65\x73\x00\x00\x00\x03\x61\x67\x65\x00"\
"\x00\x00\x05\x61\x6c\x6c\x6f\x77\x00\x00\x00\x0d\x61\x75\x74\x68"\
"\x6f\x72\x69\x7a\x61\x74\x69\x6f\x6e\x00\x00\x00\x0d\x63\x61\x63"\
"\x68\x65\x2d\x63\x6f\x6e\x74\x72\x6f\x6c\x00\x00\x00\x0a\x63\x6f"\
"\x6e\x6e\x65\x63\x74\x69\x6f\x6e\x00\x00\x00\x0c\x63\x6f\x6e\x74"\
"\x65\x6e\x74\x2d\x62\x61\x73\x65\x00\x00\x00\x10\x63\x6f\x6e\x74"\
"\x65\x6e\x74\x2d\x65\x6e\x63\x6f\x64\x69\x6e\x67\x00\x00\x00\x10"\
"\x63\x6f\x6e\x74\x65\x6e\x74\x2d\x6c\x61\x6e\x67\x75\x61\x67\x65"\
"\x00\x00\x00\x0e\x63\x6f\x6e\x74\x65\x6e\x74\x2d\x6c\x65\x6e\x67"\
"\x74\x68\x00\x00\x00\x10\x63\x6f\x6e\x74\x65\x6e\x74\x2d\x6c\x6f"\
"\x63\x61\x74\x69\x6f\x6e\x00\x00\x00\x0b\x63\x6f\x6e\x74\x65\x6e"\
"\x74\x2d\x6d\x64\x35\x00\x00\x00\x0d\x63\x6f\x6e\x74\x65\x6e\x74"\
"\x2d\x72\x61\x6e\x67\x65\x00\x00\x00\x0c\x63\x6f\x6e\x74\x65\x6e"\
"\x74\x2d\x74\x79\x70\x65\x00\x00\x00\x04\x64\x61\x74\x65\x00\x00"\
"\x00\x04\x65\x74\x61\x67\x00\x00\x00\x06\x65\x78\x70\x65\x63\x74"\
"\x00\x00\x00\x07\x65\x78\x70\x69\x72\x65\x73\x00\x00\x00\x04\x66"\
"\x72\x6f\x6d\x00\x00\x00\x04\x68\x6f\x73\x74\x00\x00\x00\x08\x69"\
"\x66\x2d\x6d\x61\x74\x63\x68\x00\x00\x00\x11\x69\x66\x2d\x6d\x6f"\
"\x64\x69\x66\x69\x65\x64\x2d\x73\x69\x6e\x63\x65\x00\x00\x00\x0d"\
"\x69\x66\x2d\x6e\x6f\x6e\x65\x2d\x6d\x61\x74\x63\x68\x00\x00\x00"\
"\x08\x69\x66\x2d\x72\x61\x6e\x67\x65\x00\x00\x00\x13\x69\x66\x2d"\
"\x75\x6e\x6d\x6f\x64\x69\x66\x69\x65\x64\x2d\x73\x69\x6e\x63\x65"\
"\x00\x00\x00\x0d\x6c\x61\x73\x74\x2d\x6d\x6f\x64\x69\x66\x69\x65"\
"\x64\x00\x00\x00\x08\x6c\x6f\x63\x61\x74\x69\x6f\x6e\x00\x00\x00"\
"\x0c\x6d\x61\x78\x2d\x66\x6f\x72\x77\x61\x72\x64\x73\x00\x00\x00"\
"\x06\x70\x72\x61\x67\x6d\x61\x00\x00\x00\x12\x70\x72\x6f\x78\x79"\
"\x2d\x61\x75\x74\x68\x65\x6e\x74\x69\x63\x61\x74\x65\x00\x00\x00"\
"\x13\x70\x72\x6f\x78\x79\x2d\x61\x75\x74\x68\x6f\x72\x69\x7a\x61"\
"\x74\x69\x6f\x6e\x00\x00\x00\x05\x72\x61\x6e\x67\x65\x00\x00\x00"\
"\x07\x72\x65\x66\x65\x72\x65\x72\x00\x00\x00\x0b\x72\x65\x74\x72"\
"\x79\x2d\x61\x66\x74\x65\x72\x00\x00\x00\x06\x73\x65\x72\x76\x65"\
"\x72\x00\x00\x00\x02\x74\x65\x00\x00\x00\x07\x74\x72\x61\x69\x6c"\
"\x65\x72\x00\x00\x00\x11\x74\x72\x61\x6e\x73\x66\x65\x72\x2d\x65"\
"\x6e\x63\x6f\x64\x69\x6e\x67\x00\x00\x00\x07\x75\x70\x67\x72\x61"\
"\x64\x65\x00\x00\x00\x0a\x75\x73\x65\x72\x2d\x61\x67\x65\x6e\x74"\
"\x00\x00\x00\x04\x76\x61\x72\x79\x00\x00\x00\x03\x76\x69\x61\x00"\
"\x00\x00\x07\x77\x61\x72\x6e\x69\x6e\x67\x00\x00\x00\x10\x77\x77"\
"\x77\x2d\x61\x75\x74\x68\x65\x6e\x74\x69\x63\x61\x74\x65\x00\x00"\
"\x00\x06\x6d\x65\x74\x68\x6f\x64\x00\x00\x00\x03\x67\x65\x74\x00"\
"\x00\x00\x06\x73\x74\x61\x74\x75\x73\x00\x00\x00\x06\x32\x30\x30"\
"\x20\x4f\x4b\x00\x00\x00\x07\x76\x65\x72\x73\x69\x6f\x6e\x00\x00"\
"\x00\x08\x48\x54\x54\x50\x2f\x31\x2e\x31\x00\x00\x00\x03\x75\x72"\
"\x6c\x00\x00\x00\x06\x70\x75\x62\x6c\x69\x63\x00\x00\x00\x0a\x73"\
"\x65\x74\x2d\x63\x6f\x6f\x6b\x69\x65\x00\x00\x00\x0a\x6b\x65\x65"\
"\x70\x2d\x61\x6c\x69\x76\x65\x00\x00\x00\x06\x6f\x72\x69\x67\x69"\
"\x6e\x31\x30\x30\x31\x30\x31\x32\x30\x31\x32\x30\x32\x32\x30\x35"\
"\x32\x30\x36\x33\x30\x30\x33\x30\x32\x33\x30\x33\x33\x30\x34\x33"\
"\x30\x35\x33\x30\x36\x33\x30\x37\x34\x30\x32\x34\x30\x35\x34\x30"\
"\x36\x34\x30\x37\x34\x30\x38\x34\x30\x39\x34\x31\x30\x34\x31\x31"\
"\x34\x31\x32\x34\x31\x33\x34\x31\x34\x34\x31\x35\x34\x31\x36\x34"\
"\x31\x37\x35\x30\x32\x35\x30\x34\x35\x30\x35\x32\x30\x33\x20\x4e"\
"\x6f\x6e\x2d\x41\x75\x74\x68\x6f\x72\x69\x74\x61\x74\x69\x76\x65"\
"\x20\x49\x6e\x66\x6f\x72\x6d\x61\x74\x69\x6f\x6e\x32\x30\x34\x20"\
"\x4e\x6f\x20\x43\x6f\x6e\x74\x65\x6e\x74\x33\x30\x31\x20\x4d\x6f"\
"\x76\x65\x64\x20\x50\x65\x72\x6d\x61\x6e\x65\x6e\x74\x6c\x79\x34"\
"\x30\x30\x20\x42\x61\x64\x20\x52\x65\x71\x75\x65\x73\x74\x34\x30"\
"\x31\x20\x55\x6e\x61\x75\x74\x68\x6f\x72\x69\x7a\x65\x64\x34\x30"\
"\x33\x20\x46\x6f\x72\x62\x69\x64\x64\x65\x6e\x34\x30\x34\x20\x4e"\
"\x6f\x74\x20\x46\x6f\x75\x6e\x64\x35\x30\x30\x20\x49\x6e\x74\x65"\
"\x72\x6e\x61\x6c\x20\x53\x65\x72\x76\x65\x72\x20\x45\x72\x72\x6f"\
"\x72\x35\x30\x31\x20\x4e\x6f\x74\x20\x49\x6d\x70\x6c\x65\x6d\x65"\
"\x6e\x74\x65\x64\x35\x30\x33\x20\x53\x65\x72\x76\x69\x63\x65\x20"\
"\x55\x6e\x61\x76\x61\x69\x6c\x61\x62\x6c\x65\x4a\x61\x6e\x20\x46"\
"\x65\x62\x20\x4d\x61\x72\x20\x41\x70\x72\x20\x4d\x61\x79\x20\x4a"\
"\x75\x6e\x20\x4a\x75\x6c\x20\x41\x75\x67\x20\x53\x65\x70\x74\x20"\
"\x4f\x63\x74\x20\x4e\x6f\x76\x20\x44\x65\x63\x20\x30\x30\x3a\x30"\
"\x30\x3a\x30\x30\x20\x4d\x6f\x6e\x2c\x20\x54\x75\x65\x2c\x20\x57"\
"\x65\x64\x2c\x20\x54\x68\x75\x2c\x20\x46\x72\x69\x2c\x20\x53\x61"\
"\x74\x2c\x20\x53\x75\x6e\x2c\x20\x47\x4d\x54\x63\x68\x75\x6e\x6b"\
"\x65\x64\x2c\x74\x65\x78\x74\x2f\x68\x74\x6d\x6c\x2c\x69\x6d\x61"\
"\x67\x65\x2f\x70\x6e\x67\x2c\x69\x6d\x61\x67\x65\x2f\x6a\x70\x67"\
"\x2c\x69\x6d\x61\x67\x65\x2f\x67\x69\x66\x2c\x61\x70\x70\x6c\x69"\
"\x63\x61\x74\x69\x6f\x6e\x2f\x78\x6d\x6c\x2c\x61\x70\x70\x6c\x69"\
"\x63\x61\x74\x69\x6f\x6e\x2f\x78\x68\x74\x6d\x6c\x2b\x78\x6d\x6c"\
"\x2c\x74\x65\x78\x74\x2f\x70\x6c\x61\x69\x6e\x2c\x74\x65\x78\x74"\
"\x2f\x6a\x61\x76\x61\x73\x63\x72\x69\x70\x74\x2c\x70\x75\x62\x6c"\
"\x69\x63\x70\x72\x69\x76\x61\x74\x65\x6d\x61\x78\x2d\x61\x67\x65"\
"\x3d\x67\x7a\x69\x70\x2c\x64\x65\x66\x6c\x61\x74\x65\x2c\x73\x64"\
"\x63\x68\x63\x68\x61\x72\x73\x65\x74\x3d\x75\x74\x66\x2d\x38\x63"\
"\x68\x61\x72\x73\x65\x74\x3d\x69\x73\x6f\x2d\x38\x38\x35\x39\x2d"\
"\x31\x2c\x75\x74\x66\x2d\x2c\x2a\x2c\x65\x6e\x71\x3d\x30\x2e"


def _bitmask(length, split, mask=0):
    invert = 1 if mask == 0 else 0
    b = str(mask) * split + str(invert) * (length-split)
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


def _pack_ushort(num):
    return pack(">H", num)


def _pack_uint(num):
    return pack(">I", num)


class SPDYProtocolError(Exception):
    def __init__(self, err_msg, status_code=None):
        super(SPDYProtocolError, self).__init__(err_msg)

        self.status_code = status_code


class SPDYStream(object):
    def __init__(self, conn, id, pri=None, headers=None, finished=True):
        self.conn = conn
        self.id = id
        self.priority = _priority(pri, conn.version)
        self.headers = headers
        self.finished = finished

        self.data = ""
        self.frames = []
        self.window_size = conn.get_setting(SETTINGS_INITIAL_WINDOW_SIZE)

    def close(self):
        self.data = None

        self.conn.close_stream(self)

    def recv(self, chunk, fin):
        self.data += chunk

        if fin:
            self.finished = True
            self.conn.parse_stream(self)

    def send(self, frame, callback=None):
        self.frames.append((frame, callback))

        self.conn.send_next_frame()


class Frame(object):
    def __init__(self, conn, flags):
        self.conn = conn
        self.flags = flags

    @property
    def fin(self):
        return FLAG_FIN == (self.flags & FLAG_FIN)

    @property
    def unidirectional(self):
        return FLAG_UNIDIRECTIONAL == (self.flags & FLAG_UNIDIRECTIONAL)

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
    def __init__(self, conn, flags, frame_type):
        super(ControlFrame, self).__init__(conn, flags)

        self.frame_type = frame_type

    def _parse_headers(self, compressed_chunk):
        headers = {}

        chunk = self.conn.inflater.decompress(compressed_chunk)

        len_size = 4 if self.conn.version >= 3 else 2

        _parse_num = _parse_uint if self.conn.version >= 3 else _parse_ushort

        num_pairs = _parse_num(chunk[0:len_size])

        pos = len_size

        for _ in xrange(num_pairs):
            len = _parse_num(chunk[pos:pos + len_size])

            if len == 0:
                raise SPDYProtocolError("The length of header name must be greater than zero", ERR_PROTOCOL_ERROR)

            pos += len_size

            name = chunk[pos:pos + len].decode(self.conn.header_encoding)
            pos += len

            len = _parse_num(chunk[pos:pos + len_size])
            pos += len_size

            values = chunk[pos:pos + len].decode(self.conn.header_encoding).split('\0') if len else []
            pos += len

            headers[name] = values

        return headers

    def _pack_headers(self, headers):
        _pack_num = _pack_uint if self.conn.version >= 3 else _pack_ushort

        chunk = _pack_num(len(headers))

        for name, value in headers:
            chunk += _pack_num(len(name)) + name + _pack_num(len(value)) + value

        compressed_chunk = self.conn.deflater.compress(chunk)

        return compressed_chunk

    def _pack_frame(self, chunk):
        return _pack_ushort(self.conn.version | 0x8000) + _pack_ushort(self.frame_type) + \
               _pack_uint(self.flags << 24 | len(chunk)) + chunk


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
    def __init__(self, conn, flags, stream_id, chunk=''):
        super(DataFrame, self).__init__(conn, flags)

        self.stream_id = stream_id
        self.chunk = chunk

    def _on_body(self, chunk):
        self.chunk = chunk

        self.conn.streams[self.stream_id].recv(chunk, self.fin)

    def pack(self):
        return _pack_uint(self.stream_id) + _pack_uint(self.flags << 24 | len(self.chunk)) + self.chunk


class SyncStream(ControlFrame):
    """
    The SYN_STREAM control frame allows the sender to asynchronously create a stream between the endpoints.

    SPDY v2
    +----------------------------------+
    |1|       2       |       1        |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |X|          Stream-ID (31bits)    |
    +----------------------------------+
    |X|Associated-To-Stream-ID (31bits)|
    +----------------------------------+
    | Pri | Unused    |                |
    +------------------                |
    |     Name/value header block      |
    |             ...                  |

    +------------------------------------+
    | Number of Name/Value pairs (int16) |
    +------------------------------------+
    |     Length of name (int16)         |
    +------------------------------------+
    |           Name (string)            |
    +------------------------------------+
    |     Length of value  (int16)       |
    +------------------------------------+
    |          Value   (string)          |
    +------------------------------------+
    |           (repeats)                |

    SDPY v3
    +------------------------------------+
    |1|   version     |          8       |
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
    def __init__(self, conn, flags):
        super(SyncStream, self).__init__(conn, flags, TYPE_SYN_STREAM)

    def _on_body(self, chunk):
        self.stream_id = _parse_uint(chunk[0:4]) & _last_31_bits

        if self.conn.last_good_stream_id is not None and \
                (self.conn.last_good_stream_id == IGNORE_ALL_STREAMS or self.stream_id > self.conn.last_good_stream_id):
            spdy_log.info("ignore SYN_STREAM #%d frame since the session has been closed at #%d.",
                          self.stream_id, self.conn.last_good_stream_id)
        else:
            self.assoc_stream_id = _parse_uint(chunk[4:8]) & _last_31_bits

            if self.conn.version >= 3:
                self.priority = (ord(chunk[8]) & _first_3_bits) >> 5
                self.slot = ord(chunk[9])
            else:
                self.priority = (ord(chunk[8]) & _first_2_bits) >> 6
                self.slot = 0

            try:
                self.headers = self._parse_headers(chunk[10:])

                stream = SPDYStream(self.conn, self.stream_id, self.priority, self.headers, self.fin)

                self.conn.add_stream(stream)
            except SPDYProtocolError, ex:
                spdy_log.warn(ex.message)

                self.conn.reset_stream(self.stream_id, ex.status_code)


class SyncReply(ControlFrame):
    """
    SYN_REPLY indicates the acceptance of a stream creation by the recipient of a SYN_STREAM frame.

    SPDY v2
    +----------------------------------+
    |1|        2        |        2     |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |X|          Stream-ID (31bits)    |
    +----------------------------------+
    | Unused        |                  |
    +----------------                  |
    |     Name/value header block      |
    |              ...                 |

    +------------------------------------+
    | Number of Name/Value pairs (int16) |
    +------------------------------------+
    |     Length of name (int16)         |
    +------------------------------------+
    |           Name (string)            |
    +------------------------------------+
    |     Length of value  (int16)       |
    +------------------------------------+
    |          Value   (string)          |
    +------------------------------------+
    |           (repeats)                |


    SPDY v3
    +------------------------------------+
    |1|   version     |          8       |
    +------------------------------------+
    |  Flags (8)  |  Length (24 bits)    |
    +------------------------------------+
    |X|           Stream-ID (31bits)     |
    +------------------------------------+
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
    def __init__(self, conn, stream_id, headers, finished):
        super(SyncReply, self).__init__(conn, FLAG_UNIDIRECTIONAL if finished else 0, TYPE_SYN_REPLY)

        self.stream_id = stream_id
        self.headers = headers

    def pack(self):
        chunk = _pack_uint(self.stream_id) + \
                ('' if self.conn.version >= 3 else _pack_ushort(0)) + \
                self._pack_headers(self.headers)

        return self._pack_frame(chunk)


class RstStream(ControlFrame):
    """
    The RST_STREAM frame allows for abnormal termination of a stream.

    +----------------------------------+
    |1|   version    |         3       |
    +----------------------------------+
    | Flags (8)  |         8           |
    +----------------------------------+
    |X|          Stream-ID (31bits)    |
    +----------------------------------+
    |          Status code             |
    +----------------------------------+
    """
    def __init__(self, conn, stream_id, status_code):
        super(RstStream, self).__init__(conn, 0, TYPE_RST_STREAM)

        self.stream_id = stream_id
        self.status_code = status_code

    def pack(self):
        chunk = _pack_uint(self.stream_id) + _pack_uint(self.status_code)

        return self._pack_frame(chunk)


class Settings(ControlFrame):
    """
    A SETTINGS frame contains a set of id/value pairs for communicating configuration data about how the two endpoints may communicate.

    +----------------------------------+
    |1|       2          |       4     |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |         Number of entries        |
    +----------------------------------+
    |          ID/Value Pairs          |
    |             ...                  |

    Each ID/value pair is as follows:

    SPDY v2
    +----------------------------------+
    |    ID (24 bits)   | ID_Flags (8) |
    +----------------------------------+
    |          Value (32 bits)         |
    +----------------------------------+

    SPDY v3
    +----------------------------------+
    | Flags(8) |      ID (24 bits)     |
    +----------------------------------+
    |          Value (32 bits)         |
    +----------------------------------+
    """
    def __init__(self, conn, flags=0, settings={}):
        super(Settings, self).__init__(conn, flags, TYPE_SETTINGS)

        self.settings = settings

    def _on_body(self, chunk):
        num = _parse_uint(chunk[0:4])
        pos = 4

        for i in range(num):
            id_and_flags = _parse_uint(chunk[pos:pos + 4])
            value = _parse_uint(chunk[pos + 4:pos + 8])
            pos += 8

            if self.conn.version >= 3:
                id = id_and_flags & 0xFFFFFF
                flags = id_and_flags >> 24
            else:
                id = id_and_flags >> 8
                flags = id_and_flags & 0xFF

            self.conn.set_setting(id, flags, value)

    def pack(self):
        chunk = _pack_uint(len(self.settings))

        for id, (flags, value) in self.settings.items():
            if self.conn.version >= 3:
                id_and_flags = (flags << 24) | id
            else:
                id_and_flags = (id << 8) | flags

            chunk += _pack_uint(id_and_flags) + _pack_uint(value)

        return self._pack_frame(chunk)

class Noop(ControlFrame):
    """
    The NOOP control frame is a no-operation frame.

    +----------------------------------+
    |1|       2          |       5     |
    +----------------------------------+
    | 0 (Flags)  |    0 (Length)       |
    +----------------------------------+
    """
    def __init__(self, conn, flags):
        super(Noop, self).__init__(conn, flags, TYPE_NOOP)

    def _on_body(self, chunk):
        assert len(chunk) == 0

        # just ignore it


class Ping(ControlFrame):
    """
    The PING control frame is a mechanism for measuring a minimal round-trip time from the sender.

    +----------------------------------+
    |1|       2          |       6     |
    +----------------------------------+
    | 0 (flags) |     4 (length)       |
    +----------------------------------|
    |            32-bit ID             |
    +----------------------------------+
    """
    def __init__(self, conn, flags=0, id=None):
        super(Ping, self).__init__(conn, flags, TYPE_PING)

        self.id = id

    def _on_body(self, chunk):
        assert len(chunk) == 4

        self.id = _parse_uint(chunk[0:4])

        self.conn.pong(self.id)

    def pack(self):
        chunk = _pack_uint(self.id)

        return self._pack_frame(chunk)


class GoAway(ControlFrame):
    """
    The GOAWAY control frame is a mechanism to tell the remote side of the connection to stop creating streams on this session.

    +----------------------------------+
    |1|   version    |         7       |
    +----------------------------------+
    | 0 (flags) |     8 (length)       |
    +----------------------------------|
    |X|  Last-good-stream-ID (31 bits) |
    +----------------------------------+
    |          Status code             | <- SPDY v3 only
    +----------------------------------+
    """
    def __init__(self, conn, flags=0, last_good_stream_id=IGNORE_ALL_STREAMS):
        super(GoAway, self).__init__(conn, flags, TYPE_GOAWAY)

        self.last_good_stream_id = last_good_stream_id

    def _on_body(self, chunk):
        assert len(chunk) == (8 if self.conn.version >= 3 else 4)

        self.last_good_stream_id = _parse_uint(chunk[0:4]) & _last_31_bits

        self.status = _parse_uint(chunk[4:8]) if self.conn.version >= 3 else GOAWAY_STATUS_OK

        self.conn.last_good_stream_id = self.last_good_stream_id

    def pack(self):
        chunk = _pack_uint(self.last_good_stream_id)

        return self._pack_frame(chunk)


class Headers(ControlFrame):
    """
    This frame augments a stream with additional headers.

    SPDY v2

    +----------------------------------+
    |C|     2           |      8       |
    +----------------------------------+
    | Flags (8)  |  Length (24 bits)   |
    +----------------------------------+
    |X|          Stream-ID (31bits)    |
    +----------------------------------+
    |  Unused (16 bits) |              |
    |--------------------              |
    | Name/value header block          |
    +----------------------------------+

    +------------------------------------+
    | Number of Name/Value pairs (int16) |
    +------------------------------------+
    |     Length of name (int16)         |
    +------------------------------------+
    |           Name (string)            |
    +------------------------------------+
    |     Length of value  (int16)       |
    +------------------------------------+
    |          Value   (string)          |
    +------------------------------------+
    |           (repeats)                |


    SPDY v3

    +------------------------------------+
    |1|   version     |          8       |
    +------------------------------------+
    | Flags (8)  |   Length (24 bits)    |
    +------------------------------------+
    |X|          Stream-ID (31bits)      |
    +------------------------------------+
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
    def __init__(self, conn, flags):
        super(Headers, self).__init__(conn, flags, TYPE_HEADERS)

    def _on_body(self, chunk):
        self.stream_id = _parse_uint(chunk[0:4]) & _last_31_bits

        stream = self.conn.streams.get(self.stream_id, None)

        if stream:
            self.headers = self._parse_headers(chunk[4:] if self.conn.version >= 3 else chunk[6:])

            stream.headers.update(self.headers)
            stream.finished = self.fin

            if stream.finished:
                self.conn.parse_stream(stream)
        else:
            spdy_log.warn("ignore an invalid HEADERS frame for #%d stream" % self.stream_id)


class WindowUpdate(ControlFrame):
    """
    The WINDOW_UPDATE control frame is used to implement per stream flow control in SPDY.

    +----------------------------------+
    |1|   version    |         9       |
    +----------------------------------+
    | 0 (flags) |     8 (length)       |
    +----------------------------------+
    |X|     Stream-ID (31-bits)        |
    +----------------------------------+
    |X|  Delta-Window-Size (31-bits)   |
    +----------------------------------+
    """
    def __init__(self, conn, flags=0, stream_id=None, delta_window_size=None):
        super(WindowUpdate, self).__init__(conn, flags, TYPE_WINDOW_UPDATE)

        self.stream_id = stream_id
        self.delta_window_size = delta_window_size

    def _on_body(self, chunk):
        assert len(chunk) == 8

        self.stream_id = _parse_uint(chunk[0:4]) & _last_31_bits
        self.delta_window_size = _parse_uint(chunk[0:4]) & _last_31_bits

        stream = self.conn.streams.get(self.stream_id, None)

        if stream:
            stream.window_size += self.delta_window_size

            if stream.window_size > WINDOW_SIZE_MAX:
                self.conn.reset_stream(self.stream_id, ERR_FLOW_CONTROL_ERROR)

    def pack(self):
        chunk = _pack_uint(self.stream_id) + _pack_uint(self.delta_window_size)

        return self._pack_frame(chunk)


class Credential(ControlFrame):
    def __init__(self, conn, flags):
        super(Credential, self).__init__(conn, flags, TYPE_CREDENTIAL)

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


class SPDYRequest(HTTPRequest):
    def __init__(self, stream, *args, **kwds):
        HTTPRequest.__init__(self, *args, **kwds)

        self.stream = stream
        self.replied = False

    def write(self, chunk, callback=None):
        assert isinstance(chunk, bytes_type)

        if not self.replied:
            idx = chunk.find('\r\n\r\n')

            lines = chunk[:idx].split('\r\n')
            version, status_code, reason = lines.pop(0).split(' ')
            status = "%s %s" % (status_code, reason)

            if self.version >= 3:
                headers = [[':status', status], [':version', version]]
            else:
                headers = [['status', status], ['version', version]]

            headers += [(name.lower(), value) for name, value in [line.split(': ') for line in lines]]

            chunk = chunk[idx + 4:]

            reply_frame = SyncReply(self.connection, self.stream.id, headers, len(chunk) == 0)

            self.stream.send(reply_frame)

            self.replied = True

        data_frame = DataFrame(self.connection, 0, self.stream.id, chunk)

        self.stream.send(data_frame, callback)

    def finish(self):
        if self.stream.frames and isinstance(self.stream.frames[-1][0], DataFrame):
            self.stream.frames[-1][0].flags |= FLAG_FIN
        else:
            data_frame = DataFrame(self.connection, FLAG_FIN, self.stream.id)

            self.stream.send(data_frame, self.stream.close)

        self._finish_time = time.time()


class SPDYConnection(object):
    """Handles a connection to an SPDY client, executing SPDY frames.

    We parse SPDY frames, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, request_callback, no_keep_alive=False, xheaders=False, protocol=None,
                 server_side=True, version=None, max_frame_len=None, min_frame_len=None, header_encoding=None,
                 compress_level=None):
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
        self.version = version or SPDY_VERSION_AUTO
        self.max_frame_len = max_frame_len or MAX_FRAME_LEN
        self.min_frame_len = min_frame_len or MIN_FRAME_LEN
        self.header_encoding = header_encoding or DEFAULT_HEADER_ENCODING
        self.compress_level = compress_level or DEFAULT_HEADER_COMPRESS_LEVEL

        self.settings = {}
        self.settings_limit = {
            SETTINGS_MAX_CONCURRENT_STREAMS: (FLAG_SETTINGS_PERSIST_VALUE, 100),
            SETTINGS_INITIAL_WINDOW_SIZE: (0, WINDOW_SIZE_DEFAULT),
        }
        self.streams = {}
        self.priority_streams = [[] for i in range(7)]
        self.control_frames = []
        self.sending = False
        self.last_good_stream_id = None
        self.ping_id = 0
        self.ping_callbacks = {}

        self.read_next_frame()

    @property
    def deflater(self):
        """
        Because header blocks are generally small, implementors may want to reduce the window-size of
        the compression engine from the default 15bits (a 32KB window) to more like 11bits (a 2KB window).
        """
        if not hasattr(self, '_deflater'):
            self._deflater = Deflater(self.version, self.compress_level)

        return self._deflater

    @property
    def inflater(self):
        if not hasattr(self, '_inflater'):
            self._inflater = Inflater(self.version)

        return self._inflater

    def get_setting(self, id):
        return self.settings[id][1] if id in self.settings else self.settings_limit[id][1]

    def set_setting(self, id, flags, value):
        if id in self.settings_limit and value > self.settings_limit[id][1]:
            value = self.settings_limit[id][1]

            frame = Settings(self, settings={
                id: self.settings_limit[id]
            })

            self.send_control_frame(frame)

        self.settings[id] = (flags, value)

    def ping(self, callback):
        frame = Ping(self, self.ping_id)

        self.send_control_frame(frame)

        self.ping_callbacks[self.ping_id] = (callback, time.time())

        self.ping_id += 2

    def pong(self, id):
        if (id % 2) == 1:
            frame = Ping(self, id)

            self.send_control_frame(frame)
        else:
            if id in self.ping_callbacks:
                callback, ts = self.ping_callbacks.pop(id)

                callback(time.time() - ts)

    def close(self):
        last_good_stream_id = max(self.streams.keys()) if self.streams else 0

        frame = GoAway(self, last_good_stream_id=last_good_stream_id)

        self.send_control_frame(frame)

        self.last_good_stream_id = IGNORE_ALL_STREAMS

    def read_next_frame(self):
        try:
            self.stream.read_bytes(FRAME_HEADER_LEN, self._on_frame_header)
        except StreamClosedError:
            pass  # TODO close all the streams

    def _on_frame_header(self, chunk):
        #first bit: control or data frame?
        control_frame = (ord(chunk[0]) & _first_bit == _first_bit)

        try:
            if control_frame:
                #second byte (and rest of first, after the first bit): spdy version
                spdy_version = _parse_ushort(chunk[0:2]) & _last_15_bits

                #third and fourth byte: frame type
                frame_type = _parse_ushort(chunk[2:4])

                #fifth byte: flags
                flags = ord(chunk[4])

                #sixth, seventh and eighth bytes: length
                frame_length = _parse_uint("\0" + chunk[5:8])

                frame_cls = FRAME_TYPES[frame_type]

                if self.version == SPDY_VERSION_AUTO:
                    spdy_log.info("auto switch to the SPDY v%d" % spdy_version)

                    self.version = spdy_version

                if spdy_version != self.version:
                    raise SPDYProtocolError("incorrect SPDY version")

                if not frame_type in FRAME_TYPES:
                    raise SPDYProtocolError("invalid frame type: {0}".format(frame_type))

                if frame_length > self.max_frame_len:
                    raise SPDYProtocolError("The SYN_STREAM frame too large", ERR_FRAME_TOO_LARGE)

                if not frame_cls:
                    raise SPDYProtocolError("unimplemented frame type: {0}".format(frame_type))

                frame = frame_cls(self, flags)
            else:
                #first four bytes, except the first bit: stream_id
                stream_id = _parse_uint(chunk[0:4]) & _last_31_bits

                #fifth byte: flags
                flags = ord(chunk[4])

                #sixth, seventh and eighth bytes: length
                frame_length = _parse_uint("\0" + chunk[5:8])

                frame = DataFrame(self, flags, stream_id)

                if stream_id not in self.streams:
                    raise SPDYProtocolError("invalid stream for %d bytes data" % frame_length, ERR_INVALID_STREAM)

            def wrapper(conn, chunk):
                try:
                    frame._on_body(chunk)
                finally:
                    conn.read_next_frame()

            self.stream.read_bytes(frame_length, functools.partial(wrapper, self))
        except SPDYProtocolError as ex:
            spdy_log.warn(ex.message)

            if ex.status_code:
                self.reset_stream(stream_id, ex.status_code)

            self.stream.read_bytes(frame_length, self.read_next_frame)

    def set_close_callback(self, callback):
        # TODO ignore the close callback
        pass

    def add_stream(self, stream):
        if stream.id in self.streams:
            self.reset_stream(stream.id, ERR_PROTOCOL_ERROR)
        else:
            self.streams[stream.id] = stream
            self.priority_streams[stream.priority].append(stream)

            if stream.finished:
                self.parse_stream(stream)

    def parse_stream(self, stream):
        try:
            if self.version >= 3:
                scheme = stream.headers.pop(u':scheme')[0]
                version = stream.headers.pop(u':version')[0]
                method = stream.headers.pop(u':method')[0]
                path = stream.headers.pop(u':path')[0]
                host = stream.headers.pop(u':host')[0]
            else:
                scheme = stream.headers.pop(u'scheme')[0]
                version = stream.headers.pop(u'version')[0]
                method = stream.headers.pop(u'method')[0]
                path = stream.headers.pop(u'url')[0]
                host = None
        except KeyError:
            pass  # TODO reply with a HTTP 400 BAD REQUEST reply.

        # HTTPRequest wants an IP, not a full socket address
        if self.address_family in (socket.AF_INET, socket.AF_INET6):
            remote_ip = self.address[0]
        else:
            # Unix (or other) socket; fake the remote address
            remote_ip = '0.0.0.0'

        headers = HTTPHeaders()

        for name, values in stream.headers.items():
            for value in values:
                headers.add(name, value)

        request = SPDYRequest(method=method, uri=path, version=version, headers=headers, body=stream.data,
                              remote_ip=remote_ip, protocol=self.protocol, host=host, connection=self, stream=stream)

        if method in ("POST", "PATCH", "PUT"):
            parse_body_arguments(
                request.headers.get("Content-Type", ""), stream.data,
                request.arguments, request.files)

        if self.version >= 3:
            frame = WindowUpdate(self, stream_id=stream.id, delta_window_size=len(stream.data))

            stream.send(frame)

        stream.data = ''

        self.request_callback(request)

    def close_stream(self, stream):
        try:
            self.priority_streams[stream.priority].remove(stream)
        except ValueError:
            pass

    def reset_stream(self, stream_id, status_code):
        if stream_id in self.streams:
            self.streams[stream_id].close()

        frame = RstStream(self, stream_id, status_code)

        self.send_control_frame(frame)

    def send_control_frame(self, frame, callback=None):
        assert isinstance(frame, ControlFrame)

        self.control_frames.append((frame, callback))

        self.send_next_frame()

    def get_next_frame(self):
        if self.control_frames:
            return self.control_frames.pop(0)

        for i in range(len(self.priority_streams)):
            streams = self.priority_streams[-(i + 1)]

            for stream in streams:
                if len(stream.frames) > 0:
                    return stream.frames.pop(0)

        return None, None

    def send_next_frame(self):
        if not self.sending:
            frame, callback = self.get_next_frame()

            if frame:
                conn = self

                def wrapper():
                    conn.sending = False

                    try:
                        if hasattr(frame, 'stream_id') and frame.fin and frame.stream_id in self.streams:
                            self.streams[frame.stream_id].close()

                        if callback:
                            callback()
                    finally:
                        conn.send_next_frame()

                self.sending = True

                self.stream.write(frame.pack(), wrapper)

                return frame

        self.sending = False

        return None


class SPDYServer(HTTPServer):
    def __init__(self, request_callback, no_keep_alive=False, io_loop=None,
                 xheaders=False, ssl_options=None, protocol=None, spdy_options=None, **kwargs):
        HTTPServer.__init__(self, request_callback=request_callback, no_keep_alive=no_keep_alive, io_loop=io_loop,
                            xheaders=xheaders, ssl_options=ssl_options, protocol=protocol, **kwargs)

        self.spdy_options = spdy_options or {}

    def handle_stream(self, stream, address):
        SPDYConnection(stream, address, self.request_callback,
                       self.no_keep_alive, self.xheaders, self.protocol,
                       server_side=True, version=self.spdy_options.get('version'),
                       max_frame_len=self.spdy_options.get('max_frame_len'),
                       min_frame_len=self.spdy_options.get('min_frame_len'),
                       header_encoding=self.spdy_options.get('header_encoding'),
                       compress_level=self.spdy_options.get('compress_level'))