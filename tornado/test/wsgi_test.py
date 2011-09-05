from wsgiref.validate import validator

from tornado.testing import AsyncHTTPTestCase, LogTrapTestCase
from tornado.util import b
from tornado.web import RequestHandler
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

class WSGIApplicationTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class HelloHandler(RequestHandler):
            def get(self):
                self.write("Hello world!")

        class PathQuotingHandler(RequestHandler):
            def get(self, path):
                self.write(path)

        # It would be better to run the wsgiref server implementation in
        # another thread instead of using our own WSGIContainer, but this
        # fits better in our async testing framework and the wsgiref
        # validator should keep us honest
        return WSGIContainer(validator(WSGIApplication([
                        ("/", HelloHandler),
                        ("/path/(.*)", PathQuotingHandler),
                        ])))

    def test_simple(self):
        response = self.fetch("/")
        self.assertEqual(response.body, b("Hello world!"))

    def test_path_quoting(self):
        response = self.fetch("/path/foo%20bar%C3%A9")
        self.assertEqual(response.body, u"foo bar\u00e9".encode("utf-8"))

# This is kind of hacky, but run some of the HTTPServer tests through
# WSGIContainer and WSGIApplication to make sure everything survives
# repeated disassembly and reassembly.
from tornado.test.httpserver_test import HTTPConnectionTest

class WSGIConnectionTest(HTTPConnectionTest):
    def get_app(self):
        return WSGIContainer(validator(WSGIApplication(self.get_handlers())))

del HTTPConnectionTest
