from wsgiref.validate import validator

from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.util import b
from tornado.wsgi import WSGIApplication, WSGIContainer

class WSGIContainerTest(AsyncHTTPTestCase, LogTrapTestCase):
    def wsgi_app(self, environ, start_response):
        status = "200 OK"
        response_headers = [("Content-Type", "text/plain")]
        start_response(status, response_headers)
        return [b("Hello world!")]

    def get_app(self):
        return WSGIContainer(validator(self.wsgi_app))

    def test_simple(self):
        response = self.fetch("/")
        self.assertEqual(response.body, b("Hello world!"))
