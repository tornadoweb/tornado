from __future__ import absolute_import, division, print_function
from wsgiref.validate import validator

from tornado.escape import json_decode
from tornado.test.httpserver_test import TypeCheckHandler
from tornado.test.util import ignore_deprecation
from tornado.testing import AsyncHTTPTestCase
from tornado.web import RequestHandler, Application
from tornado.wsgi import WSGIApplication, WSGIContainer, WSGIAdapter

from tornado.test import httpserver_test
from tornado.test import web_test


class WSGIContainerTest(AsyncHTTPTestCase):
    def wsgi_app(self, environ, start_response):
        status = "200 OK"
        response_headers = [("Content-Type", "text/plain")]
        start_response(status, response_headers)
        return [b"Hello world!"]

    def get_app(self):
        return WSGIContainer(validator(self.wsgi_app))

    def test_simple(self):
        response = self.fetch("/")
        self.assertEqual(response.body, b"Hello world!")


class WSGIAdapterTest(AsyncHTTPTestCase):
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
        with ignore_deprecation():
            return WSGIContainer(validator(WSGIAdapter(
                Application([
                    ("/", HelloHandler),
                    ("/path/(.*)", PathQuotingHandler),
                    ("/typecheck", TypeCheckHandler),
                ]))))

    def test_simple(self):
        response = self.fetch("/")
        self.assertEqual(response.body, b"Hello world!")

    def test_path_quoting(self):
        response = self.fetch("/path/foo%20bar%C3%A9")
        self.assertEqual(response.body, u"foo bar\u00e9".encode("utf-8"))

    def test_types(self):
        headers = {"Cookie": "foo=bar"}
        response = self.fetch("/typecheck?foo=bar", headers=headers)
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck", method="POST", body="foo=bar", headers=headers)
        data = json_decode(response.body)
        self.assertEqual(data, {})


# This is kind of hacky, but run some of the HTTPServer and web tests
# through WSGIContainer and WSGIApplication to make sure everything
# survives repeated disassembly and reassembly.
class WSGIConnectionTest(httpserver_test.HTTPConnectionTest):
    def get_app(self):
        with ignore_deprecation():
            return WSGIContainer(validator(WSGIAdapter(Application(self.get_handlers()))))


def wrap_web_tests_application():
    result = {}
    for cls in web_test.wsgi_safe_tests:
        def class_factory():
            class WSGIApplicationWrappedTest(cls):  # type: ignore
                def setUp(self):
                    self.warning_catcher = ignore_deprecation()
                    self.warning_catcher.__enter__()
                    super(WSGIApplicationWrappedTest, self).setUp()

                def tearDown(self):
                    super(WSGIApplicationWrappedTest, self).tearDown()
                    self.warning_catcher.__exit__(None, None, None)

                def get_app(self):
                    self.app = WSGIApplication(self.get_handlers(),
                                               **self.get_app_kwargs())
                    return WSGIContainer(validator(self.app))
        result["WSGIApplication_" + cls.__name__] = class_factory()
    return result


globals().update(wrap_web_tests_application())


def wrap_web_tests_adapter():
    result = {}
    for cls in web_test.wsgi_safe_tests:
        class WSGIAdapterWrappedTest(cls):  # type: ignore
            def get_app(self):
                self.app = Application(self.get_handlers(),
                                       **self.get_app_kwargs())
                with ignore_deprecation():
                    return WSGIContainer(validator(WSGIAdapter(self.app)))
        result["WSGIAdapter_" + cls.__name__] = WSGIAdapterWrappedTest
    return result


globals().update(wrap_web_tests_adapter())
