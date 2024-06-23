from hashlib import md5
import unittest
import logging
from logging import getLogger

from tornado.escape import utf8
from tornado.testing import AsyncHTTPTestCase
from tornado.test import httpclient_test
from tornado.web import Application, RequestHandler
from tornado.escape import native_str

import pycurl
from tornado.httpclient import HTTPResponse
from tornado import ioloop
from io import BytesIO
from tornado.curl_httpclient import CurlAsyncHTTPClient

try:
    import pycurl
except ImportError:
    pycurl = None  # type: ignore

if pycurl is not None:
    from tornado.curl_httpclient import CurlAsyncHTTPClient


@unittest.skipIf(pycurl is None, "pycurl module not present")

class CurlHTTPClientCommonTestCase(httpclient_test.HTTPClientCommonTestCase):
    def get_http_client(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        self.assertTrue(isinstance(client, CurlAsyncHTTPClient))
        return client

    def test_curl_create(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        curl = client._curl_create()

        curl_log = logging.getLogger("tornado.curl_httpclient")
        curl_log.setLevel(logging.DEBUG)

        if hasattr(pycurl, "PROTOCOLS"):
            delattr(pycurl, "PROTOCOLS")
        try:
            curl = client._curl_create()
            self.assertIsInstance(curl, pycurl.Curl)
            self.assertTrue(callable(client._curl_debug))
            if hasattr(pycurl, "PROTOCOLS"):
                self.assertTrue(True)
        finally:
            curl_log.setLevel(logging.WARNING)

    def test_curl_debug_logging(self):
        client = CurlAsyncHTTPClient(defaults=dict(allow_ipv6=False))
        curl_log = logging.getLogger("tornado.curl_httpclient")
        curl_log.setLevel(logging.DEBUG)
    

        with self.assertLogs('tornado.curl_httpclient', level='DEBUG') as log:
            client._curl_debug(0, "   This is a debug message   \n")
            self.assertIn("This is a debug message", log.output[0])
        
class DigestAuthHandler(RequestHandler):
    def initialize(self, username, password):
        self.username = username
        self.password = password

    def get(self):
        realm = "test"
        opaque = "asdf"
        # Real implementations would use a random nonce.
        nonce = "1234"

        auth_header = self.request.headers.get("Authorization", None)
        if auth_header is not None:
            auth_mode, params = auth_header.split(" ", 1)
            assert auth_mode == "Digest"
            param_dict = {}
            for pair in params.split(","):
                k, v = pair.strip().split("=", 1)
                if v[0] == '"' and v[-1] == '"':
                    v = v[1:-1]
                param_dict[k] = v
            assert param_dict["realm"] == realm
            assert param_dict["opaque"] == opaque
            assert param_dict["nonce"] == nonce
            assert param_dict["username"] == self.username
            assert param_dict["uri"] == self.request.path
            h1 = md5(
                utf8("%s:%s:%s" % (self.username, realm, self.password))
            ).hexdigest()
            h2 = md5(
                utf8("%s:%s" % (self.request.method, self.request.path))
            ).hexdigest()
            digest = md5(utf8("%s:%s:%s" % (h1, nonce, h2))).hexdigest()
            if digest == param_dict["response"]:
                self.write("ok")
            else:
                self.write("fail")
        else:
            self.set_status(401)
            self.set_header(
                "WWW-Authenticate",
                'Digest realm="%s", nonce="%s", opaque="%s"' % (realm, nonce, opaque),
            )


class CustomReasonHandler(RequestHandler):
    def get(self):
        self.set_status(200, "Custom reason")


class CustomFailReasonHandler(RequestHandler):
    def get(self):
        self.set_status(400, "Custom reason")


@unittest.skipIf(pycurl is None, "pycurl module not present")
class CurlHTTPClientTestCase(AsyncHTTPTestCase):
    def setUp(self):
        super().setUp()
        self.http_client = self.create_client()

    def get_app(self):
        return Application(
            [
                ("/digest", DigestAuthHandler, {"username": "foo", "password": "bar"}),
                (
                    "/digest_non_ascii",
                    DigestAuthHandler,
                    {"username": "foo", "password": "barユ£"},
                ),
                ("/custom_reason", CustomReasonHandler),
                ("/custom_fail_reason", CustomFailReasonHandler),
            ]
        )

    def create_client(self, **kwargs):
        return CurlAsyncHTTPClient(
            force_instance=True, defaults=dict(allow_ipv6=False), **kwargs
        )

    def test_digest_auth(self):
        response = self.fetch(
            "/digest", auth_mode="digest", auth_username="foo", auth_password="bar"
        )
        self.assertEqual(response.body, b"ok")

    def test_custom_reason(self):
        response = self.fetch("/custom_reason")
        self.assertEqual(response.reason, "Custom reason")

    def test_fail_custom_reason(self):
        response = self.fetch("/custom_fail_reason")
        self.assertEqual(str(response.error), "HTTP 400: Custom reason")

    def test_digest_auth_non_ascii(self):
        response = self.fetch(
            "/digest_non_ascii",
            auth_mode="digest",
            auth_username="foo",
            auth_password="barユ£",
        )
        self.assertEqual(response.body, b"ok")
