#!/usr/bin/env python

from tornado.auth import OAuth2Mixin, FacebookGraphMixin

import unittest
import urlparse


class TestMixinQueryParts(unittest.TestCase):

    def _mock_redirect(self,url):
        self._redirected_to = url

    def test_oa2_q_oauth_request_token_url_no_trailing_amp(self):
        """
        test that OAuth2Mixin _OAUTH_ACCESS_TOKEN_URLs that have query
        parameters dont require a trailing ampersand
        """
        self.oa2_q = OAuth2Mixin()
        self.oa2_q._OAUTH_ACCESS_TOKEN_URL = "https://localhost/access_token?x"

        self.expected_tok_args = [
                'client_secret',
                'code',
                'client_id',
                'redirect_uri'
                ]

        url = self.oa2_q._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_oa2_q_authorize_redirect_no_trailing_amp(self):
        """
        test that OAuth2Mixin _OAUTH_AUTHORIZE_URLs that have query
        parameters dont require a trailing ampersand
        """
        self.oa2_q = OAuth2Mixin()
        self.oa2_q._OAUTH_AUTHORIZE_URL = "https://localhost/authorize?x"
        self.oa2_q.redirect = self._mock_redirect

        self.expected_auth_args = [
                'client_id',
                'redirect_uri'
                ]

        self.oa2_q.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def test_oa2_q_oauth_request_token_url_has_query_parts(self):
        """
        test that OAuth2Mixin _OAUTH_ACCESS_TOKEN_URLs that have query
        parameters can include a trailing ampersand
        """
        self.oa2_q = OAuth2Mixin()
        self.oa2_q._OAUTH_ACCESS_TOKEN_URL = "https://localhost/access_token?x&"

        self.expected_tok_args = [
                'client_secret',
                'code',
                'client_id',
                'redirect_uri'
                ]

        url = self.oa2_q._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_oa2_q_authorize_redirect_has_query_parts(self):
        """
        test that OAuth2Mixin _OAUTH_AUTHORIZE_URLs that have query
        parameters can include a trailing ampersand
        """
        self.oa2_q = OAuth2Mixin()
        self.oa2_q._OAUTH_AUTHORIZE_URL = "https://localhost/authorize?x&"
        self.oa2_q.redirect = self._mock_redirect

        self.expected_auth_args = [
                'client_id',
                'redirect_uri'
                ]

        self.oa2_q.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def test_oa2_oauth_request_token_url_has_query_parts(self):
        """
        test that OAuth2Mixin _OAUTH_ACCESS_TOKEN_URLs dont require a
        query parameters
        """
        self.oa2 = OAuth2Mixin()
        self.oa2._OAUTH_ACCESS_TOKEN_URL = "https://localhost/access_token"

        self.expected_tok_args = [
                'client_secret',
                'code',
                'client_id',
                'redirect_uri'
                ]

        url = self.oa2._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_oa2_authorize_redirect_has_query_parts(self):
        """
        test that OAuth2Mixin _OAUTH_AUTHORIZE_URLs dont require a
        query parameters
        """
        self.oa2 = OAuth2Mixin()
        self.oa2._OAUTH_AUTHORIZE_URL = "https://localhost/authorize"
        self.oa2.redirect = self._mock_redirect

        self.expected_auth_args = [
                'client_id',
                'redirect_uri'
                ]

        self.oa2.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def test_fb_oauth_request_token_url_has_query_parts(self):
        """
        test that FacebookGraphMixin _oauth_request_token_url contains
        the expected query parameters
        """
        self.fb = FacebookGraphMixin()

        self.expected_tok_args = [
                'client_secret',
                'code',
                'client_id',
                'redirect_uri'
                ]

        url = self.fb._oauth_request_token_url()
        self._test_query_parts(url, self.expected_tok_args)

    def test_fb_authorize_redirect_has_query_parts(self):
        """
        test that FacebookGraphMixin authorize_redirect contains
        the expected query parameters
        """
        self.fb = FacebookGraphMixin()
        self.fb.redirect = self._mock_redirect

        self.expected_auth_args = [
                'client_id',
                'redirect_uri'
                ]

        self.fb.authorize_redirect()
        self._test_query_parts(self._redirected_to, self.expected_auth_args)

    def _test_query_parts(self, url, expected):
        """
        test that the given url contains the expected query parameters
        """
        parts = urlparse.urlsplit(url)
        self.assertNotEqual(parts.query, "")

        query = urlparse.parse_qs(parts.query)
        self.assertEqual(set(query), set(expected))

        self.assertEqual(url.find('?&'), -1)
