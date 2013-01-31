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

try:
    from tornado._zlib_stream import Inflater, Deflater
except ImportError:
    from tornado.c_zlib import Compressor, Decompressor

    class Deflater(Compressor):
        def __init__(self, version, level):
            super(Deflater, self).__init__(level, HEADER_ZLIB_DICT_2 if version == 2 else HEADER_ZLIB_DICT_3)

        def compress(self, chunk):
            return self.__call__(chunk)

    class Inflater(Decompressor):
        def __init__(self, version):
            super(Inflater, self).__init__(HEADER_ZLIB_DICT_2 if version == 2 else HEADER_ZLIB_DICT_3)

        def decompress(self, chunk):
            return self.__call__(chunk)

spdy_log = logging.getLogger("tornado.spdy")

DEFAULT_SPDY_VERSION = 2

DEFAULT_HEADER_ENCODING = 'UTF-8'
DEFAULT_HEADER_COMPRESS_LEVEL = -1

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
".1statusversionurl"

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
        self.version = version or DEFAULT_SPDY_VERSION
        self.max_frame_len = max_frame_len or MAX_FRAME_LEN
        self.min_frame_len = min_frame_len or MIN_FRAME_LEN
        self.header_encoding = header_encoding or DEFAULT_HEADER_ENCODING
        self.compress_level = compress_level or DEFAULT_HEADER_COMPRESS_LEVEL

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