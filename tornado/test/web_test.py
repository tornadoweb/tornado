from tornado.testing import LogTrapTestCase
from tornado.web import RequestHandler, _O

import logging
import re

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
        handler.set_secure_cookie('foo', 'bar')
        self.assertEquals(handler.get_secure_cookie('foo'), 'bar')

    def test_cookie_tampering_future_timestamp(self):
        handler = CookieTestRequestHandler()
        # this string base64-encodes to '12345678'
        handler.set_secure_cookie('foo', '\xd7m\xf8\xe7\xae\xfc')
        cookie = handler._cookies['foo']
        match = re.match(r'12345678\|([0-9]+)\|([0-9a-f]+)', cookie)
        assert match
        timestamp = match.group(1)
        sig = match.group(2)
        self.assertEqual(handler._cookie_signature('foo', '12345678',
                                                   timestamp), sig)
        # shifting digits from payload to timestamp doesn't alter signature
        # (this is not desirable behavior, just confirming that that's how it
        # works)
        self.assertEqual(handler._cookie_signature('foo', '1234',
                                                   '5678' + timestamp), sig)
        # tamper with the cookie
        handler._cookies['foo'] = '1234|5678%s|%s' % (timestamp, sig)
        # it gets rejected
        assert handler.get_secure_cookie('foo') is None
