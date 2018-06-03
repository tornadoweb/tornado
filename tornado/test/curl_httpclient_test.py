# coding: utf-8
from __future__ import absolute_import, division, print_function

from hashlib import md5

from tornado.escape import utf8
from tornado.httpclient import HTTPRequest, HTTPClientError
from tornado.locks import Event
from tornado.stack_context import ExceptionStackContext
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.test import httpclient_test
from tornado.test.util import unittest, ignore_deprecation
from tornado.web import Application, RequestHandler


try:
    import pycurl  # type: ignore
except ImportError:
    pycurl = None

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        # make sure AsyncHTTPClient magic doesn't give us the wrong class
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client


class DigestAuthHandler(RequestHandler):
    def initialize(self, username, password):
        self.username = username
        self.password = password

    def get(self):
        realm = 'test'
        opaque = 'asdf'
        # Real implementations would use a random nonce.
        nonce = "1234"

        auth_header = self.request.headers.get('Authorization', None)
        if auth_header is not None:
            auth_mode, params = auth_header.split(' ', 1)
            assert auth_mode == 'Digest'
            param_dict = {}
            for pair in params.split(','):
                k, v = pair.strip().split('=', 1)
                if v[0] == '"' and v[-1] == '"':
                    v = v[1:-1]
                param_dict[k] = v
            assert param_dict['realm'] == realm
            assert param_dict['opaque'] == opaque
            assert param_dict['nonce'] == nonce
            assert param_dict['username'] == self.username
            assert param_dict['uri'] == self.request.path
            h1 = md5(utf8('%s:%s:%s' % (self.username, realm, self.password))).hexdigest()
            h2 = md5(utf8('%s:%s' % (self.request.method,
                                     self.request.path))).hexdigest()
            digest = md5(utf8('%s:%s:%s' % (h1, nonce, h2))).hexdigest()
            if digest == param_dict['response']:
                self.write('ok')
            else:
                self.write('fail')
        else:
            self.set_status(401)
            self.set_header('WWW-Authenticate',
                            'Digest realm="%s", nonce="%s", opaque="%s"' %
                            (realm, nonce, opaque))


class CustomReasonHandler(RequestHandler):
    def get(self):
        self.set_status(200, "Custom reason")


class CustomFailReasonHandler(RequestHandler):
    def get(self):
        self.set_status(400, "Custom reason")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientTestCase(AsyncHTTPTestCase):
    def setUp(self):
        super(CurlHTTPClientTestCase, self).setUp()
        self.http_client = self.create_client()

    def get_app(self):
        return Application([
            ('/digest', DigestAuthHandler, {'username': 'foo', 'password': 'bar'}),
            ('/digest_non_ascii', DigestAuthHandler, {'username': 'foo', 'password': 'barユ£'}),
            ('/custom_reason', CustomReasonHandler),
            ('/custom_fail_reason', CustomFailReasonHandler),
        ])

    def create_client(self, **kwargs):
        return CurlAsyncHTTPClient(force_instance=True,
                                   defaults=dict(allow_ipv6=False),
                                   **kwargs)

    @gen_test
    def test_prepare_curl_callback_stack_context(self):
        exc_info = []
        error_event = Event()

        def error_handler(typ, value, tb):
            exc_info.append((typ, value, tb))
            error_event.set()
            return True

        with ignore_deprecation():
            with ExceptionStackContext(error_handler):
                request = HTTPRequest(self.get_url('/custom_reason'),
                                      prepare_curl_callback=lambda curl: 1 / 0)
        yield [error_event.wait(), self.http_client.fetch(request)]
        self.assertEqual(1, len(exc_info))
        self.assertIs(exc_info[0][0], ZeroDivisionError)

    def test_digest_auth(self):
        response = self.fetch('/digest', auth_mode='digest',
                              auth_username='foo', auth_password='bar')
        self.assertEqual(response.body, b'ok')

    def test_custom_reason(self):
        response = self.fetch('/custom_reason')
        self.assertEqual(response.reason, "Custom reason")

    def test_fail_custom_reason(self):
        response = self.fetch('/custom_fail_reason')
        self.assertEqual(str(response.error), "HTTP 400: Custom reason")

    def test_failed_setup(self):
        self.http_client = self.create_client(max_clients=1)
        for i in range(5):
            with ignore_deprecation():
                response = self.fetch(u'/ユニコード')
            self.assertIsNot(response.error, None)

            with self.assertRaises((UnicodeEncodeError, HTTPClientError)):
                # This raises UnicodeDecodeError on py3 and
                # HTTPClientError(404) on py2. The main motivation of
                # this test is to ensure that the UnicodeEncodeError
                # during the setup phase doesn't lead the request to
                # be dropped on the floor.
                response = self.fetch(u'/ユニコード', raise_error=True)

    def test_digest_auth_non_ascii(self):
        response = self.fetch('/digest_non_ascii', auth_mode='digest',
                              auth_username='foo', auth_password='barユ£')
        self.assertEqual(response.body, b'ok')
