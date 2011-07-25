#!/usr/bin/env python

from tornado import httpclient, simple_httpclient, netutil
from tornado.escape import json_decode, utf8, _unicode, recursive_unicode
from tornado.httpserver import HTTPServer
from tornado.httputil import HTTPHeaders
from tornado.iostream import IOStream
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase, AsyncTestCase
from tornado.util import b, bytes_type
from tornado.web import Application, RequestHandler
import os
import shutil
import socket
import tempfile

try:
    import ssl
except ImportError:
    ssl = None

class HelloWorldRequestHandler(RequestHandler):
    def initialize(self, protocol="http"):
        self.expected_protocol = protocol

    def get(self):
        assert self.request.protocol == self.expected_protocol
        self.finish("Hello world")

    def post(self):
        self.finish("Got %d bytes in POST" % len(self.request.body))

class SSLTest(AsyncHTTPTestCase, LogTrapTestCase):
    def setUp(self):
        super(SSLTest, self).setUp()
        # Replace the client defined in the parent class.
        # Some versions of libcurl have deadlock bugs with ssl,
        # so always run these tests with SimpleAsyncHTTPClient.
        self.http_client = SimpleAsyncHTTPClient(io_loop=self.io_loop,
                                                 force_instance=True)

    def get_app(self):
        return Application([('/', HelloWorldRequestHandler, 
                             dict(protocol="https"))])

    def get_httpserver_options(self):
        # Testing keys were generated with:
        # openssl req -new -keyout tornado/test/test.key -out tornado/test/test.crt -nodes -days 3650 -x509
        test_dir = os.path.dirname(__file__)
        return dict(ssl_options=dict(
                certfile=os.path.join(test_dir, 'test.crt'),
                keyfile=os.path.join(test_dir, 'test.key')))

    def fetch(self, path, **kwargs):
        self.http_client.fetch(self.get_url(path).replace('http', 'https'),
                               self.stop,
                               validate_cert=False,
                               **kwargs)
        return self.wait()

    def test_ssl(self):
        response = self.fetch('/')
        self.assertEqual(response.body, b("Hello world"))

    def test_large_post(self):
        response = self.fetch('/',
                              method='POST',
                              body='A'*5000)
        self.assertEqual(response.body, b("Got 5000 bytes in POST"))

    def test_non_ssl_request(self):
        # Make sure the server closes the connection when it gets a non-ssl
        # connection, rather than waiting for a timeout or otherwise
        # misbehaving.
        self.http_client.fetch(self.get_url("/"), self.stop,
                               request_timeout=3600,
                               connect_timeout=3600)
        response = self.wait()
        self.assertEqual(response.code, 599)

if ssl is None:
    del SSLTest

class MultipartTestHandler(RequestHandler):
    def post(self):
        self.finish({"header": self.request.headers["X-Header-Encoding-Test"],
                     "argument": self.get_argument("argument"),
                     "filename": self.request.files["files"][0]["filename"],
                     "filebody": _unicode(self.request.files["files"][0]["body"]),
                     })

class RawRequestHTTPConnection(simple_httpclient._HTTPConnection):
    def set_request(self, request):
        self.__next_request = request

    def _on_connect(self, parsed):
        self.stream.write(self.__next_request)
        self.__next_request = None
        self.stream.read_until(b("\r\n\r\n"), self._on_headers)

class HTTPConnectionTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([("/multipart", MultipartTestHandler)])

    def raw_fetch(self, headers, body):
        conn = RawRequestHTTPConnection(self.io_loop, self.http_client,
                                        httpclient.HTTPRequest(self.get_url("/")),
                                        self.stop, 1024*1024)
        conn.set_request(
            b("\r\n").join(headers +
                           [utf8("Content-Length: %d\r\n" % len(body))]) +
            b("\r\n") + body)
        response = self.wait()
        response.rethrow()
        return response

    def test_multipart_form(self):
        # Encodings here are tricky:  Headers are latin1, bodies can be
        # anything (we use utf8 by default).
        response = self.raw_fetch([
                b("POST /multipart HTTP/1.0"),
                b("Content-Type: multipart/form-data; boundary=1234567890"),
                b("X-Header-encoding-test: \xe9"),
                ],
                                  b("\r\n").join([
                    b("Content-Disposition: form-data; name=argument"),
                    b(""),
                    u"\u00e1".encode("utf-8"),
                    b("--1234567890"),
                    u'Content-Disposition: form-data; name="files"; filename="\u00f3"'.encode("utf8"),
                    b(""),
                    u"\u00fa".encode("utf-8"),
                    b("--1234567890--"),
                    b(""),
                    ]))
        data = json_decode(response.body)
        self.assertEqual(u"\u00e9", data["header"])
        self.assertEqual(u"\u00e1", data["argument"])
        self.assertEqual(u"\u00f3", data["filename"])
        self.assertEqual(u"\u00fa", data["filebody"])

class EchoHandler(RequestHandler):
    def get(self):
        self.write(recursive_unicode(self.request.arguments))

class TypeCheckHandler(RequestHandler):
    def prepare(self):
        self.errors = {}
        fields = [
            ('method', str),
            ('uri', str),
            ('version', str),
            ('remote_ip', str),
            ('protocol', str),
            ('host', str),
            ('path', str),
            ('query', str),
            ]
        for field, expected_type in fields:
            self.check_type(field, getattr(self.request, field), expected_type)

        self.check_type('header_key', self.request.headers.keys()[0], str)
        self.check_type('header_value', self.request.headers.values()[0], str)

        self.check_type('arg_key', self.request.arguments.keys()[0], str)
        self.check_type('arg_value', self.request.arguments.values()[0][0], bytes_type)

    def post(self):
        self.check_type('body', self.request.body, bytes_type)
        self.write(self.errors)

    def get(self):
        self.write(self.errors)

    def check_type(self, name, obj, expected_type):
        actual_type = type(obj)
        if expected_type != actual_type:
            self.errors[name] = "expected %s, got %s" % (expected_type, 
                                                         actual_type)

class HTTPServerTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([("/echo", EchoHandler),
                            ("/typecheck", TypeCheckHandler),
                            ])

    def test_query_string_encoding(self):
        response = self.fetch("/echo?foo=%C3%A9")
        data = json_decode(response.body)
        self.assertEqual(data, {u"foo": [u"\u00e9"]})

    def test_types(self):
        response = self.fetch("/typecheck?foo=bar")
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck", method="POST", body="foo=bar")
        data = json_decode(response.body)
        self.assertEqual(data, {})

class UnixSocketTest(AsyncTestCase, LogTrapTestCase):
    """HTTPServers can listen on Unix sockets too.

    Why would you want to do this?  Nginx can proxy to backends listening
    on unix sockets, for one thing (and managing a namespace for unix
    sockets can be easier than managing a bunch of TCP port numbers).

    Unfortunately, there's no way to specify a unix socket in a url for
    an HTTP client, so we have to test this by hand.
    """
    def setUp(self):
        super(UnixSocketTest, self).setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        super(UnixSocketTest, self).tearDown()

    def test_unix_socket(self):
        sockfile = os.path.join(self.tmpdir, "test.sock")
        sock = netutil.bind_unix_socket(sockfile)
        app = Application([("/hello", HelloWorldRequestHandler)])
        server = HTTPServer(app, io_loop=self.io_loop)
        server.add_socket(sock)
        stream = IOStream(socket.socket(socket.AF_UNIX), io_loop=self.io_loop)
        stream.connect(sockfile, self.stop)
        self.wait()
        stream.write(b("GET /hello HTTP/1.0\r\n\r\n"))
        stream.read_until(b("\r\n"), self.stop)
        response = self.wait()
        self.assertEqual(response, b("HTTP/1.0 200 OK\r\n"))
        stream.read_until(b("\r\n\r\n"), self.stop)
        headers = HTTPHeaders.parse(self.wait().decode('latin1'))
        stream.read_bytes(int(headers["Content-Length"]), self.stop)
        body = self.wait()
        self.assertEqual(body, b("Hello world"))
