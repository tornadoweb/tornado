#!/usr/bin/env python


from __future__ import absolute_import, division, print_function, with_statement
from tornado import httpclient, simple_httpclient, netutil
from tornado.escape import json_decode, utf8, _unicode, recursive_unicode, native_str
from tornado.httpserver import HTTPServer
from tornado.httputil import HTTPHeaders
from tornado.iostream import IOStream
from tornado.log import gen_log
from tornado.netutil import ssl_options_to_context, Resolver
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, AsyncHTTPSTestCase, AsyncTestCase, ExpectLog
from tornado.test.util import unittest
from tornado.util import u, bytes_type
from tornado.web import Application, RequestHandler, asynchronous
from contextlib import closing
import datetime
import os
import shutil
import socket
import ssl
import sys
import tempfile


class HandlerBaseTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return Application([('/', self.__class__.Handler)])

    def fetch_json(self, *args, **kwargs):
        response = self.fetch(*args, **kwargs)
        response.rethrow()
        return json_decode(response.body)


class HelloWorldRequestHandler(RequestHandler):
    def initialize(self, protocol="http"):
        self.expected_protocol = protocol

    def get(self):
        if self.request.protocol != self.expected_protocol:
            raise Exception("unexpected protocol")
        self.finish("Hello world")

    def post(self):
        self.finish("Got %d bytes in POST" % len(self.request.body))


# In pre-1.0 versions of openssl, SSLv23 clients always send SSLv2
# ClientHello messages, which are rejected by SSLv3 and TLSv1
# servers.  Note that while the OPENSSL_VERSION_INFO was formally
# introduced in python3.2, it was present but undocumented in
# python 2.7
skipIfOldSSL = unittest.skipIf(
    getattr(ssl, 'OPENSSL_VERSION_INFO', (0, 0)) < (1, 0),
    "old version of ssl module and/or openssl")


class BaseSSLTest(AsyncHTTPSTestCase):
    def get_app(self):
        return Application([('/', HelloWorldRequestHandler,
                             dict(protocol="https"))])


class SSLTestMixin(object):
    def get_ssl_options(self):
        return dict(ssl_version=self.get_ssl_version(),
                    **AsyncHTTPSTestCase.get_ssl_options())

    def get_ssl_version(self):
        raise NotImplementedError()

    def test_ssl(self):
        response = self.fetch('/')
        self.assertEqual(response.body, b"Hello world")

    def test_large_post(self):
        response = self.fetch('/',
                              method='POST',
                              body='A' * 5000)
        self.assertEqual(response.body, b"Got 5000 bytes in POST")

    def test_non_ssl_request(self):
        # Make sure the server closes the connection when it gets a non-ssl
        # connection, rather than waiting for a timeout or otherwise
        # misbehaving.
        with ExpectLog(gen_log, '(SSL Error|uncaught exception)'):
            self.http_client.fetch(self.get_url("/").replace('https:', 'http:'),
                                   self.stop,
                                   request_timeout=3600,
                                   connect_timeout=3600)
            response = self.wait()
        self.assertEqual(response.code, 599)

# Python's SSL implementation differs significantly between versions.
# For example, SSLv3 and TLSv1 throw an exception if you try to read
# from the socket before the handshake is complete, but the default
# of SSLv23 allows it.


class SSLv23Test(BaseSSLTest, SSLTestMixin):
    def get_ssl_version(self):
        return ssl.PROTOCOL_SSLv23


@skipIfOldSSL
class SSLv3Test(BaseSSLTest, SSLTestMixin):
    def get_ssl_version(self):
        return ssl.PROTOCOL_SSLv3


@skipIfOldSSL
class TLSv1Test(BaseSSLTest, SSLTestMixin):
    def get_ssl_version(self):
        return ssl.PROTOCOL_TLSv1


@unittest.skipIf(not hasattr(ssl, 'SSLContext'), 'ssl.SSLContext not present')
class SSLContextTest(BaseSSLTest, SSLTestMixin):
    def get_ssl_options(self):
        context = ssl_options_to_context(
            AsyncHTTPSTestCase.get_ssl_options(self))
        assert isinstance(context, ssl.SSLContext)
        return context


class BadSSLOptionsTest(unittest.TestCase):
    def test_missing_arguments(self):
        application = Application()
        self.assertRaises(KeyError, HTTPServer, application, ssl_options={
            "keyfile": "/__missing__.crt",
        })

    def test_missing_key(self):
        """A missing SSL key should cause an immediate exception."""

        application = Application()
        module_dir = os.path.dirname(__file__)
        existing_certificate = os.path.join(module_dir, 'test.crt')

        self.assertRaises(ValueError, HTTPServer, application, ssl_options={
                          "certfile": "/__mising__.crt",
                          })
        self.assertRaises(ValueError, HTTPServer, application, ssl_options={
                          "certfile": existing_certificate,
                          "keyfile": "/__missing__.key"
                          })

        # This actually works because both files exist
        HTTPServer(application, ssl_options={
                   "certfile": existing_certificate,
                   "keyfile": existing_certificate
                   })


class MultipartTestHandler(RequestHandler):
    def post(self):
        self.finish({"header": self.request.headers["X-Header-Encoding-Test"],
                     "argument": self.get_argument("argument"),
                     "filename": self.request.files["files"][0].filename,
                     "filebody": _unicode(self.request.files["files"][0]["body"]),
                     })


class RawRequestHTTPConnection(simple_httpclient._HTTPConnection):
    def set_request(self, request):
        self.__next_request = request

    def _on_connect(self):
        self.stream.write(self.__next_request)
        self.__next_request = None
        self.stream.read_until(b"\r\n\r\n", self._on_headers)

# This test is also called from wsgi_test


class HTTPConnectionTest(AsyncHTTPTestCase):
    def get_handlers(self):
        return [("/multipart", MultipartTestHandler),
                ("/hello", HelloWorldRequestHandler)]

    def get_app(self):
        return Application(self.get_handlers())

    def raw_fetch(self, headers, body):
        with closing(Resolver(io_loop=self.io_loop)) as resolver:
            with closing(SimpleAsyncHTTPClient(self.io_loop,
                                               resolver=resolver)) as client:
                conn = RawRequestHTTPConnection(
                    self.io_loop, client,
                    httpclient._RequestProxy(
                        httpclient.HTTPRequest(self.get_url("/")),
                        dict(httpclient.HTTPRequest._DEFAULTS)),
                    None, self.stop,
                    1024 * 1024, resolver)
                conn.set_request(
                    b"\r\n".join(headers +
                                 [utf8("Content-Length: %d\r\n" % len(body))]) +
                    b"\r\n" + body)
                response = self.wait()
                response.rethrow()
                return response

    def test_multipart_form(self):
        # Encodings here are tricky:  Headers are latin1, bodies can be
        # anything (we use utf8 by default).
        response = self.raw_fetch([
            b"POST /multipart HTTP/1.0",
            b"Content-Type: multipart/form-data; boundary=1234567890",
            b"X-Header-encoding-test: \xe9",
        ],
            b"\r\n".join([
                b"Content-Disposition: form-data; name=argument",
                b"",
                u("\u00e1").encode("utf-8"),
                b"--1234567890",
                u('Content-Disposition: form-data; name="files"; filename="\u00f3"').encode("utf8"),
                b"",
                u("\u00fa").encode("utf-8"),
                b"--1234567890--",
                b"",
            ]))
        data = json_decode(response.body)
        self.assertEqual(u("\u00e9"), data["header"])
        self.assertEqual(u("\u00e1"), data["argument"])
        self.assertEqual(u("\u00f3"), data["filename"])
        self.assertEqual(u("\u00fa"), data["filebody"])

    def test_100_continue(self):
        # Run through a 100-continue interaction by hand:
        # When given Expect: 100-continue, we get a 100 response after the
        # headers, and then the real response after the body.
        stream = IOStream(socket.socket(), io_loop=self.io_loop)
        stream.connect(("localhost", self.get_http_port()), callback=self.stop)
        self.wait()
        stream.write(b"\r\n".join([b"POST /hello HTTP/1.1",
                                   b"Content-Length: 1024",
                                   b"Expect: 100-continue",
                                   b"Connection: close",
                                   b"\r\n"]), callback=self.stop)
        self.wait()
        stream.read_until(b"\r\n\r\n", self.stop)
        data = self.wait()
        self.assertTrue(data.startswith(b"HTTP/1.1 100 "), data)
        stream.write(b"a" * 1024)
        stream.read_until(b"\r\n", self.stop)
        first_line = self.wait()
        self.assertTrue(first_line.startswith(b"HTTP/1.1 200"), first_line)
        stream.read_until(b"\r\n\r\n", self.stop)
        header_data = self.wait()
        headers = HTTPHeaders.parse(native_str(header_data.decode('latin1')))
        stream.read_bytes(int(headers["Content-Length"]), self.stop)
        body = self.wait()
        self.assertEqual(body, b"Got 1024 bytes in POST")
        stream.close()


class EchoHandler(RequestHandler):
    def get(self):
        self.write(recursive_unicode(self.request.arguments))

    def post(self):
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

        self.check_type('header_key', list(self.request.headers.keys())[0], str)
        self.check_type('header_value', list(self.request.headers.values())[0], str)

        self.check_type('cookie_key', list(self.request.cookies.keys())[0], str)
        self.check_type('cookie_value', list(self.request.cookies.values())[0].value, str)
        # secure cookies

        self.check_type('arg_key', list(self.request.arguments.keys())[0], str)
        self.check_type('arg_value', list(self.request.arguments.values())[0][0], bytes_type)

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


class HTTPServerTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([("/echo", EchoHandler),
                            ("/typecheck", TypeCheckHandler),
                            ("//doubleslash", EchoHandler),
                            ])

    def test_query_string_encoding(self):
        response = self.fetch("/echo?foo=%C3%A9")
        data = json_decode(response.body)
        self.assertEqual(data, {u("foo"): [u("\u00e9")]})

    def test_empty_query_string(self):
        response = self.fetch("/echo?foo=&foo=")
        data = json_decode(response.body)
        self.assertEqual(data, {u("foo"): [u(""), u("")]})

    def test_empty_post_parameters(self):
        response = self.fetch("/echo", method="POST", body="foo=&bar=")
        data = json_decode(response.body)
        self.assertEqual(data, {u("foo"): [u("")], u("bar"): [u("")]})

    def test_types(self):
        headers = {"Cookie": "foo=bar"}
        response = self.fetch("/typecheck?foo=bar", headers=headers)
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck", method="POST", body="foo=bar", headers=headers)
        data = json_decode(response.body)
        self.assertEqual(data, {})

    def test_double_slash(self):
        # urlparse.urlsplit (which tornado.httpserver used to use
        # incorrectly) would parse paths beginning with "//" as
        # protocol-relative urls.
        response = self.fetch("//doubleslash")
        self.assertEqual(200, response.code)
        self.assertEqual(json_decode(response.body), {})

    def test_malformed_body(self):
        # parse_qs is pretty forgiving, but it will fail on python 3
        # if the data is not utf8.  On python 2 parse_qs will work,
        # but then the recursive_unicode call in EchoHandler will
        # fail.
        if str is bytes_type:
            return
        with ExpectLog(gen_log, 'Invalid x-www-form-urlencoded body'):
            response = self.fetch(
                '/echo', method="POST",
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                body=b'\xe9')
        self.assertEqual(200, response.code)
        self.assertEqual(b'{}', response.body)


class HTTPServerRawTest(AsyncHTTPTestCase):
    def get_app(self):
        return Application([
            ('/echo', EchoHandler),
        ])

    def setUp(self):
        super(HTTPServerRawTest, self).setUp()
        self.stream = IOStream(socket.socket())
        self.stream.connect(('localhost', self.get_http_port()), self.stop)
        self.wait()

    def tearDown(self):
        self.stream.close()
        super(HTTPServerRawTest, self).tearDown()

    def test_empty_request(self):
        self.stream.close()
        self.io_loop.add_timeout(datetime.timedelta(seconds=0.001), self.stop)
        self.wait()

    def test_malformed_first_line(self):
        with ExpectLog(gen_log, '.*Malformed HTTP request line'):
            self.stream.write(b'asdf\r\n\r\n')
            # TODO: need an async version of ExpectLog so we don't need
            # hard-coded timeouts here.
            self.io_loop.add_timeout(datetime.timedelta(seconds=0.01),
                                     self.stop)
            self.wait()

    def test_malformed_headers(self):
        with ExpectLog(gen_log, '.*Malformed HTTP headers'):
            self.stream.write(b'GET / HTTP/1.0\r\nasdf\r\n\r\n')
            self.io_loop.add_timeout(datetime.timedelta(seconds=0.01),
                                     self.stop)
            self.wait()


class XHeaderTest(HandlerBaseTestCase):
    class Handler(RequestHandler):
        def get(self):
            self.write(dict(remote_ip=self.request.remote_ip,
                            remote_protocol=self.request.protocol))

    def get_httpserver_options(self):
        return dict(xheaders=True)

    def test_ip_headers(self):
        self.assertEqual(self.fetch_json("/")["remote_ip"], "127.0.0.1")

        valid_ipv4 = {"X-Real-IP": "4.4.4.4"}
        self.assertEqual(
            self.fetch_json("/", headers=valid_ipv4)["remote_ip"],
            "4.4.4.4")

        valid_ipv4_list = {"X-Forwarded-For": "127.0.0.1, 4.4.4.4"}
        self.assertEqual(
            self.fetch_json("/", headers=valid_ipv4_list)["remote_ip"],
            "4.4.4.4")

        valid_ipv6 = {"X-Real-IP": "2620:0:1cfe:face:b00c::3"}
        self.assertEqual(
            self.fetch_json("/", headers=valid_ipv6)["remote_ip"],
            "2620:0:1cfe:face:b00c::3")

        valid_ipv6_list = {"X-Forwarded-For": "::1, 2620:0:1cfe:face:b00c::3"}
        self.assertEqual(
            self.fetch_json("/", headers=valid_ipv6_list)["remote_ip"],
            "2620:0:1cfe:face:b00c::3")

        invalid_chars = {"X-Real-IP": "4.4.4.4<script>"}
        self.assertEqual(
            self.fetch_json("/", headers=invalid_chars)["remote_ip"],
            "127.0.0.1")

        invalid_chars_list = {"X-Forwarded-For": "4.4.4.4, 5.5.5.5<script>"}
        self.assertEqual(
            self.fetch_json("/", headers=invalid_chars_list)["remote_ip"],
            "127.0.0.1")

        invalid_host = {"X-Real-IP": "www.google.com"}
        self.assertEqual(
            self.fetch_json("/", headers=invalid_host)["remote_ip"],
            "127.0.0.1")

    def test_scheme_headers(self):
        self.assertEqual(self.fetch_json("/")["remote_protocol"], "http")

        https_scheme = {"X-Scheme": "https"}
        self.assertEqual(
            self.fetch_json("/", headers=https_scheme)["remote_protocol"],
            "https")

        https_forwarded = {"X-Forwarded-Proto": "https"}
        self.assertEqual(
            self.fetch_json("/", headers=https_forwarded)["remote_protocol"],
            "https")

        bad_forwarded = {"X-Forwarded-Proto": "unknown"}
        self.assertEqual(
            self.fetch_json("/", headers=bad_forwarded)["remote_protocol"],
            "http")


class SSLXHeaderTest(AsyncHTTPSTestCase, HandlerBaseTestCase):
    def get_app(self):
        return Application([('/', XHeaderTest.Handler)])

    def get_httpserver_options(self):
        output = super(SSLXHeaderTest, self).get_httpserver_options()
        output['xheaders'] = True
        return output

    def test_request_without_xprotocol(self):
        self.assertEqual(self.fetch_json("/")["remote_protocol"], "https")

        http_scheme = {"X-Scheme": "http"}
        self.assertEqual(
            self.fetch_json("/", headers=http_scheme)["remote_protocol"], "http")

        bad_scheme = {"X-Scheme": "unknown"}
        self.assertEqual(
            self.fetch_json("/", headers=bad_scheme)["remote_protocol"], "https")


class ManualProtocolTest(HandlerBaseTestCase):
    class Handler(RequestHandler):
        def get(self):
            self.write(dict(protocol=self.request.protocol))

    def get_httpserver_options(self):
        return dict(protocol='https')

    def test_manual_protocol(self):
        self.assertEqual(self.fetch_json('/')['protocol'], 'https')


@unittest.skipIf(not hasattr(socket, 'AF_UNIX') or sys.platform == 'cygwin',
                 "unix sockets not supported on this platform")
class UnixSocketTest(AsyncTestCase):
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
        self.sockfile = os.path.join(self.tmpdir, "test.sock")
        sock = netutil.bind_unix_socket(self.sockfile)
        app = Application([("/hello", HelloWorldRequestHandler)])
        self.server = HTTPServer(app, io_loop=self.io_loop)
        self.server.add_socket(sock)
        self.stream = IOStream(socket.socket(socket.AF_UNIX), io_loop=self.io_loop)
        self.stream.connect(self.sockfile, self.stop)
        self.wait()

    def tearDown(self):
        self.stream.close()
        self.server.stop()
        shutil.rmtree(self.tmpdir)
        super(UnixSocketTest, self).tearDown()

    def test_unix_socket(self):
        self.stream.write(b"GET /hello HTTP/1.0\r\n\r\n")
        self.stream.read_until(b"\r\n", self.stop)
        response = self.wait()
        self.assertEqual(response, b"HTTP/1.0 200 OK\r\n")
        self.stream.read_until(b"\r\n\r\n", self.stop)
        headers = HTTPHeaders.parse(self.wait().decode('latin1'))
        self.stream.read_bytes(int(headers["Content-Length"]), self.stop)
        body = self.wait()
        self.assertEqual(body, b"Hello world")

    def test_unix_socket_bad_request(self):
        # Unix sockets don't have remote addresses so they just return an
        # empty string.
        with ExpectLog(gen_log, "Malformed HTTP request from"):
            self.stream.write(b"garbage\r\n\r\n")
            self.stream.read_until_close(self.stop)
            response = self.wait()
        self.assertEqual(response, b"")


class KeepAliveTest(AsyncHTTPTestCase):
    """Tests various scenarios for HTTP 1.1 keep-alive support.

    These tests don't use AsyncHTTPClient because we want to control
    connection reuse and closing.
    """
    def get_app(self):
        class HelloHandler(RequestHandler):
            def get(self):
                self.finish('Hello world')

        class LargeHandler(RequestHandler):
            def get(self):
                # 512KB should be bigger than the socket buffers so it will
                # be written out in chunks.
                self.write(''.join(chr(i % 256) * 1024 for i in range(512)))

        class FinishOnCloseHandler(RequestHandler):
            @asynchronous
            def get(self):
                self.flush()

            def on_connection_close(self):
                # This is not very realistic, but finishing the request
                # from the close callback has the right timing to mimic
                # some errors seen in the wild.
                self.finish('closed')

        return Application([('/', HelloHandler),
                            ('/large', LargeHandler),
                            ('/finish_on_close', FinishOnCloseHandler)])

    def setUp(self):
        super(KeepAliveTest, self).setUp()
        self.http_version = b'HTTP/1.1'

    def tearDown(self):
        # We just closed the client side of the socket; let the IOLoop run
        # once to make sure the server side got the message.
        self.io_loop.add_timeout(datetime.timedelta(seconds=0.001), self.stop)
        self.wait()

        if hasattr(self, 'stream'):
            self.stream.close()
        super(KeepAliveTest, self).tearDown()

    # The next few methods are a crude manual http client
    def connect(self):
        self.stream = IOStream(socket.socket(), io_loop=self.io_loop)
        self.stream.connect(('localhost', self.get_http_port()), self.stop)
        self.wait()

    def read_headers(self):
        self.stream.read_until(b'\r\n', self.stop)
        first_line = self.wait()
        self.assertTrue(first_line.startswith(self.http_version + b' 200'), first_line)
        self.stream.read_until(b'\r\n\r\n', self.stop)
        header_bytes = self.wait()
        headers = HTTPHeaders.parse(header_bytes.decode('latin1'))
        return headers

    def read_response(self):
        headers = self.read_headers()
        self.stream.read_bytes(int(headers['Content-Length']), self.stop)
        body = self.wait()
        self.assertEqual(b'Hello world', body)

    def close(self):
        self.stream.close()
        del self.stream

    def test_two_requests(self):
        self.connect()
        self.stream.write(b'GET / HTTP/1.1\r\n\r\n')
        self.read_response()
        self.stream.write(b'GET / HTTP/1.1\r\n\r\n')
        self.read_response()
        self.close()

    def test_request_close(self):
        self.connect()
        self.stream.write(b'GET / HTTP/1.1\r\nConnection: close\r\n\r\n')
        self.read_response()
        self.stream.read_until_close(callback=self.stop)
        data = self.wait()
        self.assertTrue(not data)
        self.close()

    # keepalive is supported for http 1.0 too, but it's opt-in
    def test_http10(self):
        self.http_version = b'HTTP/1.0'
        self.connect()
        self.stream.write(b'GET / HTTP/1.0\r\n\r\n')
        self.read_response()
        self.stream.read_until_close(callback=self.stop)
        data = self.wait()
        self.assertTrue(not data)
        self.close()

    def test_http10_keepalive(self):
        self.http_version = b'HTTP/1.0'
        self.connect()
        self.stream.write(b'GET / HTTP/1.0\r\nConnection: keep-alive\r\n\r\n')
        self.read_response()
        self.stream.write(b'GET / HTTP/1.0\r\nConnection: keep-alive\r\n\r\n')
        self.read_response()
        self.close()

    def test_pipelined_requests(self):
        self.connect()
        self.stream.write(b'GET / HTTP/1.1\r\n\r\nGET / HTTP/1.1\r\n\r\n')
        self.read_response()
        self.read_response()
        self.close()

    def test_pipelined_cancel(self):
        self.connect()
        self.stream.write(b'GET / HTTP/1.1\r\n\r\nGET / HTTP/1.1\r\n\r\n')
        # only read once
        self.read_response()
        self.close()

    def test_cancel_during_download(self):
        self.connect()
        self.stream.write(b'GET /large HTTP/1.1\r\n\r\n')
        self.read_headers()
        self.stream.read_bytes(1024, self.stop)
        self.wait()
        self.close()

    def test_finish_while_closed(self):
        self.connect()
        self.stream.write(b'GET /finish_on_close HTTP/1.1\r\n\r\n')
        self.read_headers()
        self.close()
