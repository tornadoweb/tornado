# These tests do not currently do much to verify the correct implementation
# of the openid/oauth protocols, they just exercise the major code paths
# and ensure that it doesn't blow up (e.g. with unicode/bytes issues in
# python 3)


from __future__ import absolute_import, division, with_statement
from tornado.auth import OpenIdMixin, OAuthMixin, OAuth2Mixin
from tornado.escape import json_decode
from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.util import b
from tornado.web import RequestHandler, Application, asynchronous


class OpenIdClientLoginHandler(RequestHandler, OpenIdMixin):
    def initialize(self, test):
        self._OPENID_ENDPOINT = test.get_url('/openid/server/authenticate')

    @asynchronous
    def get(self):
        if self.get_argument('openid.mode', None):
            self.get_authenticated_user(
                self.on_user, http_client=self.settings['http_client'])
            return
        self.authenticate_redirect()

    def on_user(self, user):
        assert user is not None
        self.finish(user)


class OpenIdServerAuthenticateHandler(RequestHandler):
    def post(self):
        assert self.get_argument('openid.mode') == 'check_authentication'
        self.write('is_valid:true')


class OAuth1ClientLoginHandler(RequestHandler, OAuthMixin):
    def initialize(self, test, version):
        self._OAUTH_VERSION = version
        self._OAUTH_REQUEST_TOKEN_URL = test.get_url('/oauth1/server/request_token')
        self._OAUTH_AUTHORIZE_URL = test.get_url('/oauth1/server/authorize')
        self._OAUTH_ACCESS_TOKEN_URL = test.get_url('/oauth1/server/access_token')

    def _oauth_consumer_token(self):
        return dict(key='asdf', secret='qwer')

    @asynchronous
    def get(self):
        if self.get_argument('oauth_token', None):
            self.get_authenticated_user(
                self.on_user, http_client=self.settings['http_client'])
            return
        self.authorize_redirect(http_client=self.settings['http_client'])

    def on_user(self, user):
        assert user is not None
        self.finish(user)

    def _oauth_get_user(self, access_token, callback):
        assert access_token == dict(key=b('uiop'), secret=b('5678')), access_token
        callback(dict(email='foo@example.com'))


class OAuth1ClientRequestParametersHandler(RequestHandler, OAuthMixin):
    def initialize(self, version):
        self._OAUTH_VERSION = version

    def _oauth_consumer_token(self):
        return dict(key='asdf', secret='qwer')

    def get(self):
        params = self._oauth_request_parameters(
            'http://www.example.com/api/asdf',
            dict(key='uiop', secret='5678'),
            parameters=dict(foo='bar'))
        import urllib
        urllib.urlencode(params)
        self.write(params)


class OAuth1ServerRequestTokenHandler(RequestHandler):
    def get(self):
        self.write('oauth_token=zxcv&oauth_token_secret=1234')


class OAuth1ServerAccessTokenHandler(RequestHandler):
    def get(self):
        self.write('oauth_token=uiop&oauth_token_secret=5678')


class OAuth2ClientLoginHandler(RequestHandler, OAuth2Mixin):
    def initialize(self, test):
        self._OAUTH_AUTHORIZE_URL = test.get_url('/oauth2/server/authorize')

    def get(self):
        self.authorize_redirect()


class AuthTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application(
            [
                # test endpoints
                ('/openid/client/login', OpenIdClientLoginHandler, dict(test=self)),
                ('/oauth10/client/login', OAuth1ClientLoginHandler,
                 dict(test=self, version='1.0')),
                ('/oauth10/client/request_params',
                 OAuth1ClientRequestParametersHandler,
                 dict(version='1.0')),
                ('/oauth10a/client/login', OAuth1ClientLoginHandler,
                 dict(test=self, version='1.0a')),
                ('/oauth10a/client/request_params',
                 OAuth1ClientRequestParametersHandler,
                 dict(version='1.0a')),
                ('/oauth2/client/login', OAuth2ClientLoginHandler, dict(test=self)),

                # simulated servers
                ('/openid/server/authenticate', OpenIdServerAuthenticateHandler),
                ('/oauth1/server/request_token', OAuth1ServerRequestTokenHandler),
                ('/oauth1/server/access_token', OAuth1ServerAccessTokenHandler),
                ],
            http_client=self.http_client)

    def test_openid_redirect(self):
        response = self.fetch('/openid/client/login', follow_redirects=False)
        self.assertEqual(response.code, 302)
        self.assertTrue(
            '/openid/server/authenticate?' in response.headers['Location'])

    def test_openid_get_user(self):
        response = self.fetch('/openid/client/login?openid.mode=blah&openid.ns.ax=http://openid.net/srv/ax/1.0&openid.ax.type.email=http://axschema.org/contact/email&openid.ax.value.email=foo@example.com')
        response.rethrow()
        parsed = json_decode(response.body)
        self.assertEqual(parsed["email"], "foo@example.com")

    def test_oauth10_redirect(self):
        response = self.fetch('/oauth10/client/login', follow_redirects=False)
        self.assertEqual(response.code, 302)
        self.assertTrue(response.headers['Location'].endswith(
            '/oauth1/server/authorize?oauth_token=zxcv'))
        # the cookie is base64('zxcv')|base64('1234')
        self.assertTrue(
            '_oauth_request_token="enhjdg==|MTIzNA=="' in response.headers['Set-Cookie'],
            response.headers['Set-Cookie'])

    def test_oauth10_get_user(self):
        response = self.fetch(
            '/oauth10/client/login?oauth_token=zxcv',
            headers={'Cookie': '_oauth_request_token=enhjdg==|MTIzNA=='})
        response.rethrow()
        parsed = json_decode(response.body)
        self.assertEqual(parsed['email'], 'foo@example.com')
        self.assertEqual(parsed['access_token'], dict(key='uiop', secret='5678'))

    def test_oauth10_request_parameters(self):
        response = self.fetch('/oauth10/client/request_params')
        response.rethrow()
        parsed = json_decode(response.body)
        self.assertEqual(parsed['oauth_consumer_key'], 'asdf')
        self.assertEqual(parsed['oauth_token'], 'uiop')
        self.assertTrue('oauth_nonce' in parsed)
        self.assertTrue('oauth_signature' in parsed)

    def test_oauth10a_redirect(self):
        response = self.fetch('/oauth10a/client/login', follow_redirects=False)
        self.assertEqual(response.code, 302)
        self.assertTrue(response.headers['Location'].endswith(
            '/oauth1/server/authorize?oauth_token=zxcv'))
        # the cookie is base64('zxcv')|base64('1234')
        self.assertTrue(
            '_oauth_request_token="enhjdg==|MTIzNA=="' in response.headers['Set-Cookie'],
            response.headers['Set-Cookie'])

    def test_oauth10a_get_user(self):
        response = self.fetch(
            '/oauth10a/client/login?oauth_token=zxcv',
            headers={'Cookie': '_oauth_request_token=enhjdg==|MTIzNA=='})
        response.rethrow()
        parsed = json_decode(response.body)
        self.assertEqual(parsed['email'], 'foo@example.com')
        self.assertEqual(parsed['access_token'], dict(key='uiop', secret='5678'))

    def test_oauth10a_request_parameters(self):
        response = self.fetch('/oauth10a/client/request_params')
        response.rethrow()
        parsed = json_decode(response.body)
        self.assertEqual(parsed['oauth_consumer_key'], 'asdf')
        self.assertEqual(parsed['oauth_token'], 'uiop')
        self.assertTrue('oauth_nonce' in parsed)
        self.assertTrue('oauth_signature' in parsed)

    def test_oauth2_redirect(self):
        response = self.fetch('/oauth2/client/login', follow_redirects=False)
        self.assertEqual(response.code, 302)
        self.assertTrue('/oauth2/server/authorize?' in response.headers['Location'])
