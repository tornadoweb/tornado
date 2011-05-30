from tornado.escape import json_decode, utf8, to_unicode, recursive_unicode, native_str
from tornado.iostream import IOStream
from tornado.testing import LogTrapTestCase, AsyncHTTPTestCase
from tornado.util import b, bytes_type
from tornado.web import RequestHandler, _O, authenticated, Application, asynchronous, url

import binascii
import logging
import re
import socket
import tornado.ioloop

class CookieTestRequestHandler(RequestHandler):
    # stub out enough methods to make the secure_cookie functions work
    def __init__(self):
        # don't call super.__init__
        self._cookies = {}
        self.application = _O(settings=dict(cookie_secret='0123456789'))

    def get_cookie(self, name):
        return self._cookies.get(name)

    def set_cookie(self, name, value, expires_days=None):
        self._cookies[name] = value

class SecureCookieTest(LogTrapTestCase):
    def test_round_trip(self):
        handler = CookieTestRequestHandler()
        handler.set_secure_cookie('foo', b('bar'))
        self.assertEqual(handler.get_secure_cookie('foo'), b('bar'))

    def test_cookie_tampering_future_timestamp(self):
        handler = CookieTestRequestHandler()
        # this string base64-encodes to '12345678'
        handler.set_secure_cookie('foo', binascii.a2b_hex(b('d76df8e7aefc')))
        cookie = handler._cookies['foo']
        match = re.match(b(r'12345678\|([0-9]+)\|([0-9a-f]+)'), cookie)
        assert match
        timestamp = match.group(1)
        sig = match.group(2)
        self.assertEqual(handler._cookie_signature('foo', '12345678',
                                                   timestamp), sig)
        # shifting digits from payload to timestamp doesn't alter signature
        # (this is not desirable behavior, just confirming that that's how it
        # works)
        self.assertEqual(
            handler._cookie_signature('foo', '1234', b('5678') + timestamp),
            sig)
        # tamper with the cookie
        handler._cookies['foo'] = utf8('1234|5678%s|%s' % (timestamp, sig))
        # it gets rejected
        assert handler.get_secure_cookie('foo') is None

class CookieTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class SetCookieHandler(RequestHandler):
            def get(self):
                # Try setting cookies with different argument types
                # to ensure that everything gets encoded correctly
                self.set_cookie("str", "asdf")
                self.set_cookie("unicode", u"qwer")
                self.set_cookie("bytes", b("zxcv"))

        class GetCookieHandler(RequestHandler):
            def get(self):
                self.write(self.get_cookie("foo"))

        return Application([
                ("/set", SetCookieHandler),
                ("/get", GetCookieHandler)])

    def test_set_cookie(self):
        response = self.fetch("/set")
        self.assertEqual(response.headers.get_list("Set-Cookie"),
                         ["str=asdf; Path=/",
                          "unicode=qwer; Path=/",
                          "bytes=zxcv; Path=/"])

    def test_get_cookie(self):
        response = self.fetch("/get", headers={"Cookie": "foo=bar"})
        self.assertEqual(response.body, b("bar"))

class AuthRedirectRequestHandler(RequestHandler):
    def initialize(self, login_url):
        self.login_url = login_url

    def get_login_url(self):
        return self.login_url

    @authenticated
    def get(self):
        # we'll never actually get here because the test doesn't follow redirects
        self.send_error(500)

class AuthRedirectTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/relative', AuthRedirectRequestHandler,
                             dict(login_url='/login')),
                            ('/absolute', AuthRedirectRequestHandler,
                             dict(login_url='http://example.com/login'))])

    def test_relative_auth_redirect(self):
        self.http_client.fetch(self.get_url('/relative'), self.stop,
                               follow_redirects=False)
        response = self.wait()
        self.assertEqual(response.code, 302)
        self.assertEqual(response.headers['Location'], '/login?next=%2Frelative')

    def test_absolute_auth_redirect(self):
        self.http_client.fetch(self.get_url('/absolute'), self.stop,
                               follow_redirects=False)
        response = self.wait()
        self.assertEqual(response.code, 302)
        self.assertTrue(re.match(
            'http://example.com/login\?next=http%3A%2F%2Flocalhost%3A[0-9]+%2Fabsolute',
            response.headers['Location']), response.headers['Location'])


class ConnectionCloseHandler(RequestHandler):
    def initialize(self, test):
        self.test = test

    @asynchronous
    def get(self):
        self.test.on_handler_waiting()

    def on_connection_close(self):
        self.test.on_connection_close()

class ConnectionCloseTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/', ConnectionCloseHandler, dict(test=self))])

    def test_connection_close(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        s.connect(("localhost", self.get_http_port()))
        self.stream = IOStream(s, io_loop=self.io_loop)
        self.stream.write(b("GET / HTTP/1.0\r\n\r\n"))
        self.wait()

    def on_handler_waiting(self):
        logging.info('handler waiting')
        self.stream.close()

    def on_connection_close(self):
        logging.info('connection closed')
        self.stop()

class EchoHandler(RequestHandler):
    def get(self, path):
        # Type checks: web.py interfaces convert argument values to
        # unicode strings (by default, but see also decode_argument).
        # In httpserver.py (i.e. self.request.arguments), they're left
        # as bytes.  Keys are always native strings.
        for key in self.request.arguments:
            assert type(key) == str, repr(key)
            for value in self.request.arguments[key]:
                assert type(value) == bytes_type, repr(value)
            for value in self.get_arguments(key):
                assert type(value) == unicode, repr(value)
        assert type(path) == unicode, repr(path)
        self.write(dict(path=path,
                        args=recursive_unicode(self.request.arguments)))

class RequestEncodingTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([("/(.*)", EchoHandler)])

    def test_question_mark(self):
        # Ensure that url-encoded question marks are handled properly
        self.assertEqual(json_decode(self.fetch('/%3F').body),
                         dict(path='?', args={}))
        self.assertEqual(json_decode(self.fetch('/%3F?%3F=%3F').body),
                         dict(path='?', args={'?': ['?']}))

    def test_path_encoding(self):
        # Path components and query arguments should be decoded the same way
        self.assertEqual(json_decode(self.fetch('/%C3%A9?arg=%C3%A9').body),
                         {u"path":u"\u00e9",
                          u"args": {u"arg": [u"\u00e9"]}})

class TypeCheckHandler(RequestHandler):
    def prepare(self):
        self.errors = {}

        self.check_type('status', self.get_status(), int)

        # get_argument is an exception from the general rule of using
        # type str for non-body data mainly for historical reasons.
        self.check_type('argument', self.get_argument('foo'), unicode)

        self.check_type('cookie_key', self.cookies.keys()[0], str)
        self.check_type('cookie_value', self.cookies.values()[0].value, str)
        # secure cookies
    
        self.check_type('xsrf_token', self.xsrf_token, bytes_type)
        self.check_type('xsrf_form_html', self.xsrf_form_html(), str)

        self.check_type('reverse_url', self.reverse_url('typecheck', 'foo'), str)

        self.check_type('request_summary', self._request_summary(), str)

    def get(self, path_component):
        # path_component uses type unicode instead of str for consistency
        # with get_argument()
        self.check_type('path_component', path_component, unicode)
        self.write(self.errors)

    def post(self, path_component):
        self.check_type('path_component', path_component, unicode)
        self.write(self.errors)

    def check_type(self, name, obj, expected_type):
        actual_type = type(obj)
        if expected_type != actual_type:
            self.errors[name] = "expected %s, got %s" % (expected_type,
                                                         actual_type)

class DecodeArgHandler(RequestHandler):
    def decode_argument(self, value, name=None):
        assert type(value) == bytes_type, repr(value)
        # use self.request.arguments directly to avoid recursion
        if 'encoding' in self.request.arguments:
            return value.decode(to_unicode(self.request.arguments['encoding'][0]))
        else:
            return value

    def get(self, arg):
        def describe(s):
            if type(s) == bytes_type:
                return ["bytes", native_str(binascii.b2a_hex(s))]
            elif type(s) == unicode:
                return ["unicode", s]
            raise Exception("unknown type")
        self.write({'path': describe(arg),
                    'query': describe(self.get_argument("foo")),
                    })

class WebTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([
                url("/typecheck/(.*)", TypeCheckHandler, name='typecheck'),
                url("/decode_arg/(.*)", DecodeArgHandler),
                url("/decode_arg_kw/(?P<arg>.*)", DecodeArgHandler),
                ])

    def test_types(self):
        response = self.fetch("/typecheck/asdf?foo=bar",
                              headers={"Cookie": "cook=ie"})
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck/asdf?foo=bar", method="POST",
                              headers={"Cookie": "cook=ie"},
                              body="foo=bar")

    def test_decode_argument(self):
        # These urls all decode to the same thing
        urls = ["/decode_arg/%C3%A9?foo=%C3%A9&encoding=utf-8",
                "/decode_arg/%E9?foo=%E9&encoding=latin1",
                "/decode_arg_kw/%E9?foo=%E9&encoding=latin1",
                ]
        for url in urls:
            response = self.fetch(url)
            response.rethrow()
            data = json_decode(response.body)
            self.assertEqual(data, {u'path': [u'unicode', u'\u00e9'],
                                    u'query': [u'unicode', u'\u00e9'],
                                    })

        response = self.fetch("/decode_arg/%C3%A9?foo=%C3%A9")
        response.rethrow()
        data = json_decode(response.body)
        self.assertEqual(data, {u'path': [u'bytes', u'c3a9'],
                                u'query': [u'bytes', u'c3a9'],
                                })
