#!/usr/bin/env python

from tornado.auth import OAuth2Mixin, FacebookGraphMixin

import unittest
import urlparse


class TestMixinQueryParts(unittest.TestCase):

    def setUp(self):
        self.fb = FacebookGraphMixin()
        self.oa2 = OAuth2Mixin()
        self.oa2._OAUTH_ACCESS_TOKEN_URL = "https://localhost/access_token"
        self.oa2._OAUTH_AUTHORIZE_URL = "https://localhost/authorize"
        self.expected_tok_args = [
                'client_secret',
                'code',
                'client_id',
                'redirect_uri'
                ]
        self.expected_auth_args = [
                'client_id',
                'redirect_uri'
                ]
        self.oa2.redirect = self._mock_redirect
        self.fb.redirect = self._mock_redirect

        self.oa2_q = OAuth2Mixin()
        self.oa2_q._OAUTH_ACCESS_TOKEN_URL = "https://localhost/access_token?x&"
        self.oa2_q._OAUTH_AUTHORIZE_URL = "https://localhost/authorize?x&"
        self.oa2_q.redirect = self._mock_redirect

    def _mock_redirect(self,url):
        self._redirected_to = url

    def test_oa2_q_oauth_request_token_url_has_query_parts(self):
        url = self.oa2_q._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_oa2_q_authorize_redirect_has_query_parts(self):
        self.oa2_q.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def test_oa2_oauth_request_token_url_has_query_parts(self):
        url = self.oa2._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_oa2_authorize_redirect_has_query_parts(self):
        self.oa2.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def test_fb_oauth_request_token_url_has_query_parts(self):
        url = self.fb._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_fb_authorize_redirect_has_query_parts(self):
        self.fb.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def _test_query_parts(self, url, expected):
        parts = urlparse.urlsplit(url)
        self.assertNotEqual(parts.query, "")

        query = urlparse.parse_qs(parts.query)
        self.assertEqual(set(query), set(expected))
