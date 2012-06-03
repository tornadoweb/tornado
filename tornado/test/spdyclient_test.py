from tornado.simple_httpclient import TCPConnectionException
from tornado.spdyclient import AsyncSPDYClient
from tornado.spdyserver import SPDYServer
from tornado.spdysession import SPDYSessionException
from tornado.spdyutil.v2 import parse_frame, ControlFrame, ControlFrameType, DataFrame, GoawayFrame, HeadersFrame, PingFrame, RstStreamFrame, Setting, SettingsFrame, StatusCode, SynReplyFrame, SynStreamFrame, _SynStreamFrame, ZLibContext
from tornado.stack_context import StackContext
from tornado.test.httpclient_test import HTTPClientCommonTestCase
from tornado.tcpserver import TCPServer
from tornado.testing import AsyncSPDYTestCase, AsyncSSLTestCase, LogTrapTestCase
from tornado.util import b
from tornado import gen, netutil

import contextlib
import ssl
import time


class SPDYClientCommonTestCase(HTTPClientCommonTestCase, AsyncSPDYTestCase):
    # Chunked encoding is unavailable in SPDY
    def test_chunked(self):
        return

    def test_chunked_close(self):
        return

del HTTPClientCommonTestCase


reply_headers = {'status': ['200'], 'version': ['HTTP/1.1']}

class SPDYClientTestCase(AsyncSPDYTestCase, LogTrapTestCase):
    def get_server(self):
        self.frames = []
        def handler(conn, address, server):
            def reader(callback):
                def cb_wrapper(frame):
                    self.frames.append(frame)
                    callback(frame)
                parse_frame(conn, self.context, cb_wrapper)
            def writer(frame):
                conn.write(frame.serialize(self.context))
            gen.engine(self.handler)(gen.Task(reader), writer)
        return TCPServer(handler, io_loop=self.io_loop)

    def get_app(self):
        return None

    def fetch(self, path='/', push=False, **kwargs):
        self.pushed = []
        def push_callback(response):
            self.pushed.append(response)
        self.context = ZLibContext()
        response = AsyncSPDYTestCase.fetch(self, path, push_callback=(push_callback if push else None), **kwargs)
        self.http_client.reset()
        return response

    @contextlib.contextmanager
    def catch_exc(self):
        self.exc = None
        try:
            yield
        except SPDYSessionException, exc:
            self.exc = exc

    def assertReset(self, status_code, error=True, **kwargs):
        with StackContext(self.catch_exc):
            self.fetch(**kwargs)
        if error:
            self.assertTrue(self.exc)
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.RST_STREAM)
        self.assertEqual(frame.data.status_code, status_code)

    def test_push(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1, finished=True))
            writer(DataFrame(stream_id=1, finished=True))
        self.handler = handler
        response = self.fetch(push=True)

        self.assertEqual(response.request.url, self.get_url('/'))
        self.assertEqual(self.pushed[0].associated_to_url, self.get_url('/'))
        self.assertEqual(self.pushed[0].request.url, self.get_url('/pushed'))
        self.assertEqual(self.pushed[0].request.method, 'GET')

        self.assertEqual(response.headers, {'Status': '200', 'Version': 'HTTP/1.1'})
        self.assertEqual(self.pushed[0].headers, {'Url': self.get_url('/pushed'), 'Status': '200'})

    def test_push_multiple_interleaved(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/one')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(SynStreamFrame(stream_id=4, headers={'url': [self.get_url('/two')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))

            writer(DataFrame(stream_id=1, data=b('a')))
            writer(DataFrame(stream_id=2, data=b('b')))
            writer(DataFrame(stream_id=4, data=b('c')))

            writer(DataFrame(stream_id=4, finished=True))
            writer(DataFrame(stream_id=2, finished=True))
            writer(DataFrame(stream_id=1, finished=True))
        self.handler = handler
        response = self.fetch(push=True)

        self.assertEqual(response.request.url, self.get_url('/'))
        self.assertEqual(response.body, b('a'))
        self.assertEqual(self.pushed[0].request.url, self.get_url('/two'))
        self.assertEqual(self.pushed[0].body, b('c'))
        self.assertEqual(self.pushed[1].request.url, self.get_url('/one'))
        self.assertEqual(self.pushed[1].body, b('b'))

    def test_push_multiple_sequential(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/one')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(DataFrame(stream_id=2, data=b('b')))
            writer(DataFrame(stream_id=2, finished=True))
            writer(DataFrame(stream_id=1, data=b('a')))

            writer(SynStreamFrame(stream_id=4, headers={'url': [self.get_url('/two')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(DataFrame(stream_id=4, data=b('c')))
            writer(DataFrame(stream_id=4, finished=True))
            writer(DataFrame(stream_id=1, finished=True))
        self.handler = handler
        response = self.fetch(push=True)

        self.assertEqual(response.request.url, self.get_url('/'))
        self.assertEqual(response.body, b('a'))
        self.assertEqual(self.pushed[0].request.url, self.get_url('/one'))
        self.assertEqual(self.pushed[0].body, b('b'))
        self.assertEqual(self.pushed[1].request.url, self.get_url('/two'))
        self.assertEqual(self.pushed[1].body, b('c'))

    def test_push_before_reply(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(DataFrame(stream_id=2, data=b('b'), finished=True))
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(DataFrame(stream_id=1, data=b('a'), finished=True))
        self.handler = handler
        response = self.fetch(push=True)

        self.assertEqual(response.request.url, self.get_url('/'))
        self.assertEqual(response.body, b('a'))
        self.assertEqual(self.pushed[0].request.url, self.get_url('/pushed'))
        self.assertEqual(self.pushed[0].body, b('b'))

    def test_push_data_after_closing_originating(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(DataFrame(stream_id=1, data=b('a'), finished=True))
            writer(DataFrame(stream_id=2, data=b('b'), finished=True))
        self.handler = handler
        self.pushed = []
        def push_callback(response):
            self.pushed.append(response)
            self.stop()
        self.context = ZLibContext()
        response = AsyncSPDYTestCase.fetch(self, '/', push_callback=push_callback)
        self.wait()

        self.assertEqual(response.request.url, self.get_url('/'))
        self.assertEqual(response.body, b('a'))
        self.assertEqual(self.pushed[0].request.url, self.get_url('/pushed'))
        self.assertEqual(self.pushed[0].body, b('b'))

    def test_push_stream_after_closing_originating(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        with StackContext(self.catch_exc):
            self.fetch(push=True)
        self.wait()
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.RST_STREAM)
        self.assertEqual(frame.data.status_code, StatusCode.INVALID_STREAM)

    def test_push_reply(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(SynReplyFrame(stream_id=2))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_unsupported_version(self):
        def handler(reader, writer):
            yield reader
            writer(ControlFrame(ControlFrameType.SYN_STREAM, _SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1), version=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.UNSUPPORTED_VERSION, error=False, push=True)

    def test_push_missing_unidirectional_flag(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_missing_url_header(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_existing_stream(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=1, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_existing_pushed_stream(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/one')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/two')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_odd_stream_id(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=3, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_zero_stream_id(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=0, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False, push=True)

    def test_push_missing_associated_to_stream_id(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False, push=True)

    def test_push_unknown_associated_to_stream_id(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=3))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False, push=True)

    def test_push_pushed_associated_to_stream_id(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/one')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            writer(SynStreamFrame(stream_id=4, headers={'url': [self.get_url('/two')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=2))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR, error=False, push=True)

    def test_push_no_callback(self):
        def handler(reader, writer):
            yield reader
            writer(SynStreamFrame(stream_id=2, headers={'url': [self.get_url('/pushed')], 'status': ['200']}, unidirectional=True, associated_to_stream_id=1))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.CANCEL, error=False, push=False)

    def test_stream_priority(self):
        def handler(reader, writer):
            yield reader
            self.stop()
        self.handler = handler
        self.fetch(priority=2)
        self.assertEqual(self.frames[0].data.priority, 2)

    def test_reply_unknown_stream(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=3))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False)

    def test_double_reply(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_reply_missing_header(self):
        for key in reply_headers:
            def handler(reader, writer):
                yield reader
                headers = reply_headers.copy()
                headers.pop(key, None)
                writer(SynReplyFrame(stream_id=1, headers=headers))
                yield reader
                self.stop()
            self.handler = handler
            self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_reply_finished(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        response = self.fetch()
        self.assertFalse(response.body)

    def test_reset_raises(self):
        def handler(reader, writer):
            yield reader
            writer(RstStreamFrame(stream_id=3, status_code=StatusCode.FLOW_CONTROL_ERROR))
            writer(RstStreamFrame(stream_id=1, status_code=StatusCode.INTERNAL_ERROR))
            yield gen.Task(self.io_loop.add_timeout, time.time()+1)
            self.stop()
        self.handler = handler
        with StackContext(self.catch_exc):
            self.fetch()
        self.assertTrue(self.exc)

    def test_settings(self):
        return # TODO expose settings
        def handler(reader, writer):
            yield reader
            writer(SettingsFrame(settings={1: Setting(1), 4: Setting(4, persist_value=True)}))
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        self.fetch()

        def handler(reader, writer):
            yield reader
            yield reader
            writer(SettingsFrame(settings={4: Setting(5, persist_value=True), 6: Setting(6, persist_value=True)}))
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        self.fetch()

        frame = self.frames[-2]
        self.assertEqual(frame.control_type, ControlFrameType.SETTINGS)
        self.assertEqual(frame.data.settings.keys(), [4])
        self.assertEqual(frame.data.settings[4].value, 4)
        self.assertEqual(frame.data.settings[4].persisted, True)
        self.assertEqual(frame.data.settings[4].persist_value, False)

        def handler(reader, writer):
            yield reader
            yield reader
            writer(SettingsFrame(settings={2: Setting(2, persist_value=True)}, clear_previously_persisted_settings=True))
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        self.fetch()

        frame = self.frames[-2]
        self.assertEqual(frame.control_type, ControlFrameType.SETTINGS)
        self.assertEqual(frame.data.settings.keys(), [4, 6])
        self.assertEqual(frame.data.settings[4].value, 5)

        def handler(reader, writer):
            yield reader
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        self.fetch()

        frame = self.frames[-2]
        self.assertEqual(frame.control_type, ControlFrameType.SETTINGS)
        self.assertEqual(frame.data.settings.keys(), [2])
        self.assertEqual(frame.data.settings[2].value, 2)

    def test_ping(self):
        def handler(reader, writer):
            yield reader
            writer(PingFrame(id=2))
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers, finished=True))
        self.handler = handler
        self.fetch()

        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.PING)
        self.assertEqual(frame.data.id, 2)

    def test_goaway(self):
        def handler(reader, writer):
            for i in range(4):
                yield reader
            writer(GoawayFrame(last_good_stream_id=3))
            self.stop()
        self.handler = handler
        for i in range(4):
            self.http_client.fetch(self.get_url('/%i'%i), self.stop)
        self.context = ZLibContext()
        self.wait(timeout=5)

        def handler(reader, writer):
            for i in range(2):
                yield reader
            self.stop()
        self.handler = handler
        self.context = ZLibContext()
        self.wait(timeout=5)

        urls = ['/2', '/3']
        frames = self.frames[-len(urls):]
        for i in range(len(urls)):
            self.assertEqual(frames[i].control_type, ControlFrameType.SYN_STREAM)
            self.assertEqual(frames[i].data.headers['url'][0], urls[i])

    def test_headers(self):
        def handler(reader, writer):
            yield reader
            headers = reply_headers.copy()
            headers['a'] = ['1']
            writer(SynReplyFrame(stream_id=1, headers=headers))
            writer(HeadersFrame(stream_id=1, headers={'b': ['2']}))
            writer(DataFrame(stream_id=1, finished=True))
        self.handler = handler
        response = self.fetch()
        self.assertEqual(response.headers, {'Status': '200', 'Version': 'HTTP/1.1', 'A': '1', 'B': '2'})

    def test_headers_duplicate(self):
        def handler(reader, writer):
            yield reader
            headers = reply_headers.copy()
            headers['a'] = ['1']
            writer(SynReplyFrame(stream_id=1, headers=headers))
            writer(HeadersFrame(stream_id=1, headers={'a': ['2']}))
            writer(DataFrame(stream_id=1, finished=True))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_headers_unknown_stream(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(HeadersFrame(stream_id=3, headers={'a': ['2'], 'b': ['1']}))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False)

    def test_headers_before_reply(self):
        def handler(reader, writer):
            yield reader
            writer(HeadersFrame(stream_id=1, headers={'a': ['2'], 'b': ['1']}))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_data(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(DataFrame(stream_id=1, data=b('abc')))
            writer(DataFrame(stream_id=1, data=b('def'), finished=True))
        self.handler = handler
        self.fetch()

    def test_data_unknown_stream(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(DataFrame(stream_id=3, data=b('abc')))
            yield reader
            self.stop()
        self.handler = handler
        self.assertReset(StatusCode.INVALID_STREAM, error=False)

    def test_data_empty(self):
        def handler(reader, writer):
            yield reader
            writer(SynReplyFrame(stream_id=1, headers=reply_headers))
            writer(DataFrame(stream_id=1, finished=True))
        self.handler = handler
        response = self.fetch()
        self.assertFalse(response.body)

    def test_request_timeout(self):
        def handler(reader, writer):
            yield reader
        self.handler = handler
        start = time.time()
        try:
            response = self.fetch(request_timeout=0.1)
        except TCPConnectionException, e:
            self.assertTrue(0.099 < time.time()-start < 0.2)
            self.assertEqual(str(e), "Timeout")
        else:
            self.fail()

    def test_default_spdy_shared_connection(self):
        def handler(reader, writer):
            yield reader
            yield reader
            self.stop()
        self.handler = handler
        self.http_client.fetch(self.get_url('/'), None)
        self.http_client.fetch(self.get_url('/'), None)
        self.context = ZLibContext()
        self.wait(timeout=5)
        self.assertEqual(self.frames[-1].control_type, ControlFrameType.SYN_STREAM)
        self.assertEqual(self.frames[-2].control_type, ControlFrameType.SYN_STREAM)


class KeepAliveTimeoutTestCase(AsyncSPDYTestCase, LogTrapTestCase):
    def get_client(self):
        return AsyncSPDYClient(io_loop=self.io_loop, force_instance=True, default_spdy=True, keep_alive_timeout=0.1)

    def get_server(self):
        def handler(conn, address, server):
            gen.engine(self.handler)(conn)
        return TCPServer(handler, io_loop=self.io_loop)

    def get_app(self):
        return None

    def test_keep_alive_timeout(self):
        return # FIXME
        conns = []
        def handler(conn):
            conns.append(conn)
            self.stop()
        self.handler = handler
        self.fetch('/')
        time.sleep(0.2)
        self.fetch('/')
        self.assertNotEqual(conns[0], conns[1])


class SPDYClientSPDYNPNServerTestCase(AsyncSSLTestCase, LogTrapTestCase):
    def get_ssl_version(self):
        return ssl.PROTOCOL_TLSv1

    def get_server_side(self):
        return True

    def get_client(self):
        return AsyncSPDYClient(io_loop=self.io_loop, force_instance=True)

    def get_server(self):
        return SPDYServer(self.get_app(), io_loop=self.io_loop, **self.get_server_options())

    def get_app(self):
        self.frames = []
        def handler(conn, address, server):
            def reader(callback):
                def cb_wrapper(frame):
                    self.frames.append(frame)
                    callback(frame)
                parse_frame(conn, self.context, cb_wrapper)
            def writer(frame):
                conn.write(frame.serialize(self.context))
            gen.engine(self.handler)(gen.Task(reader), writer)
        return handler

    def test_spdy_shared_connection(self):
        return # FIXME
        def handler(reader, writer):
            yield reader
            yield reader
            self.stop()
        self.handler = handler
        self.http_client.fetch(self.get_url('/'), None, ssl_version=ssl.PROTOCOL_TLSv1)
        self.http_client.fetch(self.get_url('/'), None, ssl_version=ssl.PROTOCOL_TLSv1)
        self.context = ZLibContext()
        self.wait(timeout=5)
        self.assertEqual(self.frames[-1].control_type, ControlFrameType.SYN_STREAM)
        self.assertEqual(self.frames[-2].control_type, ControlFrameType.SYN_STREAM)


class SPDYClientHTTPNPNServerTestCase(AsyncSSLTestCase, LogTrapTestCase):
    def get_ssl_version(self):
        return ssl.PROTOCOL_TLSv1

    def get_client(self):
        return AsyncSPDYClient(io_loop=self.io_loop, force_instance=True)

    def get_app(self):
        return lambda conn, address, server: self.handler(conn)

    def test_http_different_connection(self):
        return # FIXME
        conns = []
        def handler(conn):
            conns.append(conn)
            if len(conns) == 2:
                self.stop()
        self.handler = handler
        self.http_client.fetch(self.get_url('/'), None)
        self.http_client.fetch(self.get_url('/'), None)
        self.wait(timeout=5)
        self.assertNotEqual(conns[0], conns[1])

if not netutil.SUPPORTS_NPN:
    del SPDYClientSPDYNPNServerTestCase
    del SPDYClientHTTPNPNServerTestCase
