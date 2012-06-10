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

"""Data structures representing SPDY frames, serialization/deserialization
routines, and miscellaneous utilities.
"""

from __future__ import absolute_import, division, with_statement

from struct import calcsize, pack, unpack

from tornado import gen
from tornado.c_zlib import Compressor, Decompressor
from tornado.escape import to_unicode, utf8
from tornado.spdyutil import SPDYParseException, SPDYStreamParseException
from tornado.util import b, BytesIO


_ZLIB_DICT = b(
"optionsgetheadpostputdeletetraceacceptaccept-charsetaccept-encodingaccept-" \
"languageauthorizationexpectfromhostif-modified-sinceif-matchif-none-matchi" \
"f-rangeif-unmodifiedsincemax-forwardsproxy-authorizationrangerefererteuser" \
"-agent10010120020120220320420520630030130230330430530630740040140240340440" \
"5406407408409410411412413414415416417500501502503504505accept-rangesageeta" \
"glocationproxy-authenticatepublicretry-afterservervarywarningwww-authentic" \
"ateallowcontent-basecontent-encodingcache-controlconnectiondatetrailertran" \
"sfer-encodingupgradeviawarningcontent-languagecontent-lengthcontent-locati" \
"oncontent-md5content-rangecontent-typeetagexpireslast-modifiedset-cookieMo" \
"ndayTuesdayWednesdayThursdayFridaySaturdaySundayJanFebMarAprMayJunJulAugSe" \
"pOctNovDecchunkedtext/htmlimage/pngimage/jpgimage/gifapplication/xmlapplic" \
"ation/xhtmltext/plainpublicmax-agecharset=iso-8859-1utf-8gzipdeflateHTTP/1" \
".1statusversionurl\0")


class ZLibContext(object):
    """Per-stream compression context"""

    def __init__(self):
        self.compress = Compressor(-1, _ZLIB_DICT)
        self.decompress = Decompressor(_ZLIB_DICT)


class FrameType:
    DATA = 0
    CONTROL = 1

class ControlFrameType:
    SYN_STREAM = 1
    SYN_REPLY = 2
    RST_STREAM = 3
    SETTINGS = 4
    NOOP = 5
    PING = 6
    GOAWAY = 7
    HEADERS = 8

class StatusCode:
    PROTOCOL_ERROR = 1
    INVALID_STREAM = 2
    REFUSED_STREAM = 3
    UNSUPPORTED_VERSION = 4
    CANCEL = 5
    INTERNAL_ERROR = 6
    FLOW_CONTROL_ERROR = 7

class SettingID:
    UPLOAD_BANDWIDTH = 1
    DOWNLOAD_BANDWIDTH = 2
    ROUND_TRIP_TIME = 3
    MAX_CONCURRENT_STREAMS = 4
    CURRENT_CWND = 5
    DOWNLOAD_RETRANS_RATE = 6
    INITIAL_WINDOW_SIZE = 7

class _SynStreamFlag:
    FIN = 0x1
    UNIDIRECTIONAL = 0x2

class _SynReplyFlag:
    FIN = 0x1

class _DataFlag:
    FIN = 0x1

class _SettingsFlag:
    CLEAR_PREVIOUSLY_PERSISTED_SETTINGS = 0x1

class _SettingsValueFlag:
    PERSIST_VALUE = 0x1
    PERSISTED = 0x2


STATUS_CODE_MESSAGES = {
    StatusCode.PROTOCOL_ERROR: "Protocol error",
    StatusCode.INVALID_STREAM: "Invalid stream ID",
    StatusCode.REFUSED_STREAM: "Stream refused",
    StatusCode.UNSUPPORTED_VERSION: "Unsupported SPDY version",
    StatusCode.CANCEL: "Stream canceled",
    StatusCode.INTERNAL_ERROR: "Server encountered an internal error",
    StatusCode.FLOW_CONTROL_ERROR: "Flow control protocol violated",
}


class AttrCmp(object):
    def __eq__(self, rhs):
        return self.__dict__ == rhs.__dict__

    def __ne__(self, rhs):
        return not (self == rhs)


class DataFrame(AttrCmp):
    """
    +----------------------------------+
    |C|       Stream-ID (31)           |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |               Data               |
    +----------------------------------+
    """

    def __init__(self, stream_id, data=b(''), finished=False):
        self.type = FrameType.DATA
        self.stream_id = stream_id
        self.data = data
        self.finished = finished

    def serialize(self, context):
        if len(self.data) > 0xffffff:
            raise SPDYParseException("Data too large")
        return pack('!II', self.stream_id, _serialize_flags([self.finished])<<24|len(self.data))+self.data


class ControlFrame(AttrCmp):
    """
    +----------------------------------+
    |C| Version (15)    | Type (16)    |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |               Data               |
    +----------------------------------+
    """

    def __init__(self, control_type, data, version=2):
        self.type = FrameType.CONTROL
        self.control_type = control_type
        self.version = version
        self.data = data

    def serialize(self, context):
        data, flags = self.data.serialize(context)
        if len(data) > 0xffffff:
            raise SPDYParseException("Control frame too large")
        return pack('!HHI', self.version|self.type<<15, self.control_type, _serialize_flags(flags)<<24|len(data))+data


def SynStreamFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.SYN_STREAM, _SynStreamFrame(*args, **kwargs))

class _SynStreamFrame(AttrCmp):
    """
    +----------------------------------+
    |1|       2          |       1     |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |X|          Stream-ID (31)        |
    +----------------------------------+
    |X|  Associated-To-Stream-ID (31)  |
    +----------------------------------+
    |Pri (2)| X (14)  |                |
    +------------------                |
    |     Name/value header block      |
    |             ...                  |
    """

    def __init__(self, stream_id, associated_to_stream_id=0, priority=0, headers=None, finished=False, unidirectional=False):
        self.stream_id = stream_id
        self.associated_to_stream_id = associated_to_stream_id
        self.priority = priority
        self.headers = headers or {}
        self.finished = finished
        self.unidirectional = unidirectional

    def serialize(self, context):
        if self.priority > 3:
            raise SPDYParseException("Priority out of range")
        return pack('!IIH', self.stream_id, self.associated_to_stream_id, self.priority<<14)+_serialize_headers(self.headers, context), [self.finished, self.unidirectional]


def SynReplyFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.SYN_REPLY, _SynReplyFrame(*args, **kwargs))

class _SynReplyFrame(AttrCmp):
    """
    +----------------------------------+
    |1|        2        |        2     |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |X|          Stream-ID (31)        |
    +----------------------------------+
    | X (16)        |                  |
    +----------------                  |
    |     Name/value header block      |
    |              ...                 |
    """

    def __init__(self, stream_id, headers=None, finished=False):
        self.stream_id = stream_id
        self.headers = headers or {}
        self.finished = finished

    def serialize(self, context):
        return pack('!IH', self.stream_id, 0)+_serialize_headers(self.headers, context), [self.finished]


def RstStreamFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.RST_STREAM, _RstStreamFrame(*args, **kwargs))

class _RstStreamFrame(AttrCmp):
    """
    +-------------------------------+
    |1|       2        |      3     |
    +-------------------------------+
    | Flags (8)  |         8        |
    +-------------------------------+
    |X|          Stream-ID (31)     |
    +-------------------------------+
    |          Status code (32)     |
    +-------------------------------+
    """

    def __init__(self, stream_id, status_code):
        self.stream_id = stream_id
        self.status_code = status_code

    def serialize(self, context):
        return pack('!II', self.stream_id, self.status_code), []


def SettingsFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.SETTINGS, _SettingsFrame(*args, **kwargs))

class _SettingsFrame(AttrCmp):
    """
    +----------------------------------+
    |1|       2          |       4     |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |       Number of entries (32)     |
    +----------------------------------+
    |          ID/Value Pairs          |
    |             ...                  |
    """

    def __init__(self, settings, clear_previously_persisted_settings=False):
        self.settings = settings
        self.clear_previously_persisted_settings = clear_previously_persisted_settings

    def serialize(self, context):
        if len(self.settings) > 0xffffffff:
            raise SPDYParseException("Too many settings")
        data = pack('!I', len(self.settings))
        for id, setting in self.settings.iteritems():
            data += pack('<I', id)[:3]+setting.serialize()
        return data, [self.clear_previously_persisted_settings]


class Setting(AttrCmp):
    """
    +----------------------------------+
    |    ID (24)        | ID_Flags (8) |
    +----------------------------------+
    |          Value (32)              |
    +----------------------------------+
    """

    def __init__(self, value, persist_value=False, persisted=False):
        self.value = value
        self.persist_value = persist_value
        self.persisted = persisted

    def serialize(self):
        return pack('!BI', _serialize_flags([self.persist_value, self.persisted]), self.value)


def NoopFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.NOOP, _NoopFrame(*args, **kwargs))

class _NoopFrame(AttrCmp):
    """
    +----------------------------------+
    |1|       2          |       5     |
    +----------------------------------+
    | 0          |    0                |
    +----------------------------------+
    """

    def __init__(self):
        self.flags = []

    def serialize(self, context):
        return b(''), []


def PingFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.PING, _PingFrame(*args, **kwargs))

class _PingFrame(AttrCmp):
    """
    +----------------------------------+
    |1|       2          |       6     |
    +----------------------------------+
    | 0         |     4                |
    +----------------------------------|
    |            ID (32)               |
    +----------------------------------+
    """

    def __init__(self, id):
        self.id = id

    def serialize(self, context):
        return pack('!I', self.id), []


def GoawayFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.GOAWAY, _GoawayFrame(*args, **kwargs))

class _GoawayFrame(AttrCmp):
    """
    +----------------------------------+
    |1|       2          |       7     |
    +----------------------------------+
    | 0         |     4                |
    +----------------------------------|
    |X|  Last-good-stream-ID (31)      |
    +----------------------------------+
    """

    def __init__(self, last_good_stream_id):
        self.last_good_stream_id = last_good_stream_id

    def serialize(self, context):
        return pack('!I', self.last_good_stream_id), []


def HeadersFrame(*args, **kwargs):
    return ControlFrame(ControlFrameType.HEADERS, _HeadersFrame(*args, **kwargs))

class _HeadersFrame(AttrCmp):
    """
    +----------------------------------+
    |C|     2           |      8       |
    +----------------------------------+
    | Flags (8)  |  Length (24)        |
    +----------------------------------+
    |X|          Stream-ID (31)        |
    +----------------------------------+
    |  Unused (16)      |              |
    |--------------------              |
    | Name/value header block          |
    +----------------------------------+
    """

    def __init__(self, stream_id, headers):
        self.stream_id = stream_id
        self.headers = headers

    def serialize(self, context):
        return pack('!IH', self.stream_id, 0)+_serialize_headers(self.headers, context), []


def _serialize_headers(headers, context):
    """
    +------------------------------------+
    | Number of name/value pairs (16)    |
    +------------------------------------+
    |     Length of name (16)            |
    +------------------------------------+
    |           Name (string)            |
    +------------------------------------+
    |     Length of value (16)           |
    +------------------------------------+
    |          Value (string)            |
    +------------------------------------+
    |           (repeats)                |
    """

    data = b('')
    count = 0
    for key, values in headers.iteritems():
        value = b('\0').join([utf8(v) for v in values if v])
        if key and value:
            key = utf8(key.lower())
            if len(key) > 0xffff:
                raise SPDYParseException("Header name too long")
            if len(value) > 0xffff:
                raise SPDYParseException("Header value too long")
            data += pack('!H', len(key))+key+pack('!H', len(value))+value
            count += 1
    if count > 0xffff:
        raise SPDYParseException("Too many headers")
    return context.compress(pack('!H', count)+data)

def _serialize_flags(flags):
    mask = 0
    for i in range(len(flags)):
        if flags[i]:
            mask |= 1<<i
    return mask

def _read_unpack(stream, format, callback):
    stream.read_bytes(calcsize(format), lambda data: callback(unpack(format, data)))

def _consume(buffer, format):
    return unpack(format, buffer.read(calcsize(format)))

def _parse_headers(data, context):
    block = BytesIO(context.decompress(data.read()))
    count, = _consume(block, '!H')
    headers = {}
    for i in range(count):
        key = block.read(_consume(block, '!H')[0])
        if len(key) == 0:
            raise SPDYParseException("Zero-length header name")
        value = block.read(_consume(block, '!H')[0])
        if len(value) == 0:
            raise SPDYParseException("No header values")
        values = []
        for v in value.split(b('\0')):
            if len(v) == 0:
                raise SPDYParseException("Zero-length header value")
            try:
                values.append(to_unicode(v))
            except UnicodeDecodeError:
                raise SPDYParseException("Invalid UTF-8 in header value")
        try:
            key = to_unicode(key).lower()
        except UnicodeDecodeError:
            raise SPDYParseException("Invalid UTF-8 in header name")
        if key in headers:
            raise SPDYParseException("Duplicate header name")
        headers[to_unicode(key)] = values
    return headers

@gen.engine
def parse_frame(stream, context, callback):
    """A SPDY frame parser that reads from a non-blocking stream.

    :arg IOStream stream: the non-blocking stream to read from

    :arg ZLibContext context: compression context for this frame

    """
    parts = yield gen.Task(_read_unpack, stream, '!II')
    flags = parts[1]>>24
    bytes = yield gen.Task(stream.read_bytes, parts[1]&0xffffff)
    data = BytesIO(bytes)
    stream_id = None
    try:
        if parts[0] & 1<<31:
            version = parts[0]>>16&0x7fff
            type = parts[0]&0xffff
            if type == ControlFrameType.SYN_STREAM:
                stream_id, associated_to_stream_id, last = _consume(data, '!IIH')
                priority = last>>14
                frame = ControlFrame(ControlFrameType.SYN_STREAM,
                                     _SynStreamFrame(stream_id=stream_id,
                                                     associated_to_stream_id=associated_to_stream_id,
                                                     priority=priority,
                                                     headers=_parse_headers(data, context),
                                                     finished=bool(flags&_SynStreamFlag.FIN),
                                                     unidirectional=bool(flags&_SynStreamFlag.UNIDIRECTIONAL)),
                                     version=version)
            elif type == ControlFrameType.SYN_REPLY:
                stream_id, unused = _consume(data, '!IH')
                frame = ControlFrame(ControlFrameType.SYN_REPLY,
                                     _SynReplyFrame(stream_id, _parse_headers(data, context), finished=bool(flags&_SynReplyFlag.FIN)),
                                     version=version)
            elif type == ControlFrameType.RST_STREAM:
                stream_id, status_code = _consume(data, '!II')
                frame = ControlFrame(ControlFrameType.RST_STREAM, _RstStreamFrame(stream_id, status_code), version=version)
            elif type == ControlFrameType.HEADERS:
                stream_id, unused = _consume(data, '!IH')
                frame = ControlFrame(ControlFrameType.HEADERS, _HeadersFrame(stream_id, _parse_headers(data, context)), version=version)
            elif type == ControlFrameType.SETTINGS:
                count, = _consume(data, '!I')
                settings = {}
                for i in range(count):
                    first, = _consume(data, '<I')
                    id = first&0xffffff
                    setting_flags = first>>24
                    value, = _consume(data, '!I')
                    settings[id] = Setting(value,
                                           persist_value=bool(setting_flags&_SettingsValueFlag.PERSIST_VALUE),
                                           persisted=bool(setting_flags&_SettingsValueFlag.PERSISTED))
                frame = ControlFrame(ControlFrameType.SETTINGS,
                                     _SettingsFrame(settings,
                                                    clear_previously_persisted_settings=bool(flags&_SettingsFlag.CLEAR_PREVIOUSLY_PERSISTED_SETTINGS)),
                                     version=version)
            elif type == ControlFrameType.NOOP:
                frame = ControlFrame(ControlFrameType.NOOP, _NoopFrame(), version=version)
            elif type == ControlFrameType.PING:
                id, = _consume(data, '!I')
                frame = ControlFrame(ControlFrameType.PING, _PingFrame(id), version=version)
            elif type == ControlFrameType.GOAWAY:
                last_good_stream_id, = _consume(data, '!I')
                frame = ControlFrame(ControlFrameType.GOAWAY, _GoawayFrame(last_good_stream_id), version=version)
            else:
                raise SPDYParseException("Invalid control frame type: %i" % type)
        else:
            stream_id = parts[0]
            frame = DataFrame(stream_id, data.read(), finished=bool(flags&_DataFlag.FIN))
    except SPDYParseException, e:
        if stream_id is not None:
            raise SPDYStreamParseException(stream_id, e.msg)
        raise
    callback(frame)
