import tornado.ioloop
import tornado.web
import tornado.testing
from menual import make_app

class TestUnicodeURL(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        return make_app()

    def test_unicode_url(self):
        response = self.fetch("/hello/%E4%BD%A0%E5%A5%BD")  # URL-encoded "你好" (Hello in Chinese)
        self.assertEqual(response.code, 200)
        self.assertIn("你好", response.body.decode())


raf = TestUnicodeURL()
raf.test_unicode_url()
