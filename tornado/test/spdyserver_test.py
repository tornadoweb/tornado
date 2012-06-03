from tornado import gen
from tornado.simple_httpclient import QueuedAsyncHTTPClient
from tornado.spdyserver.v2 import SPDYServerProtocol, _SPDYServerSession
from tornado.spdyutil.v2 import parse_frame, ControlFrame, ControlFrameType, DataFrame, FrameType, HeadersFrame, PingFrame, StatusCode, SynReplyFrame, SynStreamFrame, _SynStreamFrame, ZLibContext
from tornado.tcpserver import TCPServer
from tornado.test.httpserver_test import HTTPServerTest
from tornado.testing import AsyncSPDYTestCase, LogTrapTestCase
from tornado.util import b


class Client(QueuedAsyncHTTPClient):
    def initialize(self, handler, npn_protocols=None, **kwargs):
        QueuedAsyncHTTPClient.initialize(self, handler, **kwargs)

class SPDYServerCommonTestCase(HTTPServerTest):
    pass

del HTTPServerTest


# TODO test pushed streams are closed when originating stream is reset

fetch_headers = {'method': ['GET'], 'scheme': ['https'], 'url': ['/'], 'version': ['HTTP/1.1']}

class SPDYServerBaseTestCase(AsyncSPDYTestCase, LogTrapTestCase):
    def get_app(self):
        self.server = None
        def app(request):
            self.request = request
            if self.server:
                return self.server(request.connection)
        return app

    def get_client(self):
        self.frames = []
        @gen.engine
        def handler(request, release_callback, final_callback):
            conn, address = yield gen.Task(self.http_client._http_connect, request)
            def reader(callback):
                def cb_wrapper(frame):
                    self.frames.append(frame)
                    callback(frame)
                parse_frame(conn, self.context, cb_wrapper)
            def writer(frame):
                conn.write(frame.serialize(self.context))
            gen.engine(self.client)(gen.Task(reader), writer)
        return Client(handler=handler, io_loop=self.io_loop, force_instance=True)

    def fetch(self, **kwargs):
        self.context = ZLibContext()
        response = AsyncSPDYTestCase.fetch(self, '/', **kwargs)
        return response

    def assertReset(self, status_code):
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.RST_STREAM)
        self.assertEqual(frame.data.status_code, status_code)


class SPDYServerTestCase(SPDYServerBaseTestCase):
    def test_preamble(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            conn.write_preamble(200, headers=[('key', 'one'), ('key', 'two')], finished=True)
        self.server = server
        self.fetch()
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.SYN_REPLY)
        self.assertEqual(frame.data.headers['status'], ['200 OK'])
        self.assertEqual(frame.data.headers['version'], ['HTTP/1.1'])
        self.assertEqual(frame.data.headers['key'], ['one','two'])
        self.assertTrue(frame.data.finished)

    def test_data(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            yield reader
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            conn.write_preamble(200)
            conn.write(b('body'), finished=True)
        self.server = server
        self.fetch()
        frame = self.frames[-1]
        self.assertEqual(frame.type, FrameType.DATA)
        self.assertEqual(frame.data, b('body'))
        self.assertTrue(frame.finished)

    def test_request(self):
        def client(reader, writer):
            headers = fetch_headers.copy()
            headers['key-word'] = ['one', 'two']
            writer(SynStreamFrame(stream_id=1, headers=headers, priority=2))
            writer(DataFrame(stream_id=1, data=b('a')))
            writer(DataFrame(stream_id=1, data=b('b'), finished=True))
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            conn.write_preamble(200, finished=True)
        self.server = server
        self.fetch(priority=2)
        self.assertEqual(self.request.body, b('ab'))
        self.assertEqual(self.request.uri, '/')
        self.assertEqual(self.request.headers, {'Key-Word': 'one,two', 'Method': 'GET', 'Scheme': 'https', 'Url': '/', 'Version': 'HTTP/1.1'})
        self.assertEqual(self.request.method, 'GET')
        self.assertEqual(self.request.framing, 'spdy/2')
        self.assertEqual(self.request.priority, 2)

    def test_data_unknown_stream(self):
        def client(reader, writer):
            writer(DataFrame(stream_id=1))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.INVALID_STREAM)

    def test_stream_unsupported_version(self):
        def client(reader, writer):
            writer(ControlFrame(ControlFrameType.SYN_STREAM, _SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True), version=1))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.UNSUPPORTED_VERSION)

    def test_request_existing_stream(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_request_stream_id_zero(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=0, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.INVALID_STREAM)

    def test_request_stream_id_even(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=2, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_request_missing_header(self):
        for key in fetch_headers:
            def client(reader, writer):
                headers = fetch_headers.copy()
                headers.pop(key, None)
                writer(SynStreamFrame(stream_id=1, headers=headers, finished=True))
                yield reader
                self.stop()
            self.client = client
            self.fetch()
            frame = self.frames[-1]
            self.assertEqual(frame.data.headers['status'][0].split()[0], '400')

    def test_reply_raises(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers))
            writer(SynReplyFrame(stream_id=1))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_headers(self):
        def client(reader, writer):
            headers = fetch_headers.copy()
            headers['a'] = ['1']
            writer(SynStreamFrame(stream_id=1, headers=headers))
            writer(HeadersFrame(stream_id=1, headers={'b': ['2']}))
            writer(DataFrame(stream_id=1, finished=True))
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            conn.write_preamble(200, finished=True)
        self.server = server
        self.fetch()
        self.assertEqual(self.request.headers, {'A': '1', 'B': '2', 'Method': 'GET', 'Scheme': 'https', 'Url': '/', 'Version': 'HTTP/1.1'})

    def test_headers_duplicate(self):
        def client(reader, writer):
            headers = fetch_headers.copy()
            headers['a'] = ['1']
            writer(SynStreamFrame(stream_id=1, headers=headers))
            writer(HeadersFrame(stream_id=1, headers={'a': ['2']}))
            writer(DataFrame(stream_id=1, finished=True))
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            conn.write_preamble(200, finished=True)
        self.server = server
        self.fetch()
        self.assertReset(StatusCode.PROTOCOL_ERROR)

    def test_headers_unknown_stream(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers))
            writer(HeadersFrame(stream_id=3, headers={'a': ['2'], 'b': ['1']}))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.assertReset(StatusCode.INVALID_STREAM)

    def test_handler_exception(self):
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        def server(conn):
            raise Exception()
        self.server = server
        self.fetch()
        self.assertReset(StatusCode.INTERNAL_ERROR)

    def test_ping(self):
        def client(reader, writer):
            writer(PingFrame(id=1))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.PING)
        self.assertEqual(frame.data.id, 1)


class KeepAliveTimeoutTestCase(SPDYServerBaseTestCase):
    def get_server_options(self):
        return dict(keep_alive_timeout=10)

    def test_keep_alive_timeout(self):
        conns = []
        def server(conn):
            conns.append(conn.stream.session)
            conn.write_preamble(200, finished=True)
        self.server = server
        def client(reader, writer):
            writer(SynStreamFrame(stream_id=1, headers=fetch_headers, finished=True))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        self.fetch()
        self.assertNotEqual(conns[0], conns[1])


class SPDYTestServerProtocol(SPDYServerProtocol):
    def __call__(self, stream, address, server):
        SPDYTestServerSession(stream, address, self, server.io_loop).listen()

class SPDYTestServerSession(_SPDYServerSession):
    def _handle_ping(self, frame):
        raise Exception()

class SPDYServerNonstreamErrorTestCase(SPDYServerBaseTestCase):
    def get_server(self):
        return TCPServer(SPDYTestServerProtocol(self.get_app(), **self.get_server_options()), io_loop=self.io_loop)

    def test_nonstream_error(self):
        def client(reader, writer):
            writer(PingFrame(id=1))
            yield reader
            self.stop()
        self.client = client
        self.fetch()
        frame = self.frames[-1]
        self.assertEqual(frame.control_type, ControlFrameType.GOAWAY)
