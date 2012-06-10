#!/usr/bin/env python


from __future__ import absolute_import, division, with_statement
from tornado import gen
from tornado.spdyutil import SPDYParseException
from tornado.spdyutil.v2 import parse_frame, ControlFrame, ControlFrameType, DataFrame, GoawayFrame, HeadersFrame, NoopFrame, _NoopFrame, _parse_headers, PingFrame, RstStreamFrame, Setting, SettingID, SettingsFrame, StatusCode, SynStreamFrame, SynReplyFrame, ZLibContext
from tornado.util import b, BytesIO

from struct import pack
import unittest


class ByteStream(object):
    def __init__(self, buffer):
        self.buffer = BytesIO(buffer)

    def read_bytes(self, num, callback):
        callback(self.buffer.read(num))


class UtilTestCase(unittest.TestCase):
    @gen.engine
    def assertSerialized(self, frame):
        context = ZLibContext()
        self.assertEqual(frame, (yield gen.Task(parse_frame, ByteStream(frame.serialize(context)), context)))

    def assertRaisesParseException(self, headers):
        context = ZLibContext()
        self.assertRaises(SPDYParseException, _parse_headers, BytesIO(self.serialize_headers(headers, context)), context)

    def serialize_headers(self, headers, context):
        data = b('')
        count = 0
        for key, values in headers:
            value = b('\0').join([b(v) for v in values])
            key = b(key).lower()
            data += pack('!H', len(key))+key+pack('!H', len(value))+value
            count += 1
        return context.compress(pack('!H', count)+data)

    def test_data(self):
        self.assertSerialized(DataFrame(stream_id=1))
        self.assertSerialized(DataFrame(stream_id=1, data=b('abcdef'), finished=True))

    def test_control_frame(self):
        self.assertSerialized(ControlFrame(ControlFrameType.NOOP, _NoopFrame(), version=3))

    def test_syn_stream(self):
        self.assertSerialized(SynStreamFrame(stream_id=1))
        self.assertSerialized(SynStreamFrame(stream_id=1, associated_to_stream_id=2, priority=3, finished=True, unidirectional=True, headers={'a': ['1']}))

    def test_syn_reply(self):
        self.assertSerialized(SynReplyFrame(stream_id=1))
        self.assertSerialized(SynReplyFrame(stream_id=1, finished=True, headers={'a': ['1']}))

    def test_rst_stream(self):
        self.assertSerialized(RstStreamFrame(stream_id=1, status_code=StatusCode.PROTOCOL_ERROR))

    def test_settings(self):
        self.assertSerialized(SettingsFrame(settings={}, clear_previously_persisted_settings=True))
        self.assertSerialized(SettingsFrame(settings={SettingID.DOWNLOAD_BANDWIDTH: Setting(5), SettingID.ROUND_TRIP_TIME: Setting(8, persist_value=True, persisted=True)}))

    def test_noop(self):
        self.assertSerialized(NoopFrame())

    def test_ping(self):
        self.assertSerialized(PingFrame(id=1))

    def test_goaway(self):
        self.assertSerialized(GoawayFrame(last_good_stream_id=1))

    @gen.engine
    def test_headers(self):
        frame = HeadersFrame(stream_id=1, headers={
            'a': ['1'],
            'b': ['2','3'],
            u'\u00e9': [u'\u00e9'],
            '': ['2'],
            'c': ['', ''],
            'd': [],
        })
        result_headers = {
            'a': ['1'],
            'b': ['2','3'],
            u'\u00e9': [u'\u00e9'],
        }
        context = ZLibContext()
        self.assertEqual(result_headers, (yield gen.Task(parse_frame, ByteStream(frame.serialize(context)), context)).data.headers)

    def test_zero_length_header_name(self):
        self.assertRaisesParseException([('', ['a'])])

    def test_no_header_values(self):
        self.assertRaisesParseException([('a', [])])

    def test_zero_length_header_value(self):
        self.assertRaisesParseException([('a', ['b',''])])

    def test_duplicate_header_name(self):
        self.assertRaisesParseException([('a', ['b']), ('a', ['c'])])
