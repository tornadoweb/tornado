from tornado.escape import json_decode, utf8, to_unicode, recursive_unicode, native_str
from tornado.iostream import IOStream
from tornado.template import DictLoader
from tornado.testing import LogTrapTestCase, AsyncHTTPTestCase
from tornado.util import b, bytes_type, ObjectDict
from tornado.web import RequestHandler, authenticated, Application, asynchronous, url, HTTPError, StaticFileHandler, _create_signature

import binascii
import logging
import os
import re
import socket
import sys

class CookieTestRequestHandler(RequestHandler):
    # stub out enough methods to make the secure_cookie functions work
    def __init__(self):
        # don't call super.__init__
        self._cookies = {}
        self.application = ObjectDict(settings=dict(cookie_secret='0123456789'))

    def get_cookie(self, name):
        return self._cookies.get(name)

    def set_cookie(self, name, value, expires_days=None):
        self._cookies[name] = value

class SecureCookieTest(LogTrapTestCase):
    def test_round_trip(self):
        handler = CookieTestRequestHandler()
        handler.set_secure_cookie('foo', b('bar'))
        self.assertEqual(handler.get_secure_cookie('foo'), b('bar'))

    def test_cookie_tampering_future_timestamp(self):
        handler = CookieTestRequestHandler()
        # this string base64-encodes to '12345678'
        handler.set_secure_cookie('foo', binascii.a2b_hex(b('d76df8e7aefc')))
        cookie = handler._cookies['foo']
        match = re.match(b(r'12345678\|([0-9]+)\|([0-9a-f]+)'), cookie)
        assert match
        timestamp = match.group(1)
        sig = match.group(2)
        self.assertEqual(
            _create_signature(handler.application.settings["cookie_secret"],
                              'foo', '12345678', timestamp),
            sig)
        # shifting digits from payload to timestamp doesn't alter signature
        # (this is not desirable behavior, just confirming that that's how it
        # works)
        self.assertEqual(
            _create_signature(handler.application.settings["cookie_secret"],
                              'foo', '1234', b('5678') + timestamp),
            sig)
        # tamper with the cookie
        handler._cookies['foo'] = utf8('1234|5678%s|%s' % (timestamp, sig))
        # it gets rejected
        assert handler.get_secure_cookie('foo') is None

class CookieTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class SetCookieHandler(RequestHandler):
            def get(self):
                # Try setting cookies with different argument types
                # to ensure that everything gets encoded correctly
                self.set_cookie("str", "asdf")
                self.set_cookie("unicode", u"qwer")
                self.set_cookie("bytes", b("zxcv"))

        class GetCookieHandler(RequestHandler):
            def get(self):
                self.write(self.get_cookie("foo"))

        class SetCookieDomainHandler(RequestHandler):
            def get(self):
                # unicode domain and path arguments shouldn't break things
                # either (see bug #285)
                self.set_cookie("unicode_args", "blah", domain=u"foo.com",
                                path=u"/foo")

        class SetCookieSpecialCharHandler(RequestHandler):
            def get(self):
                self.set_cookie("equals", "a=b")
                self.set_cookie("semicolon", "a;b")
                self.set_cookie("quote", 'a"b')


        return Application([
                ("/set", SetCookieHandler),
                ("/get", GetCookieHandler),
                ("/set_domain", SetCookieDomainHandler),
                ("/special_char", SetCookieSpecialCharHandler),
                ])

    def test_set_cookie(self):
        response = self.fetch("/set")
        self.assertEqual(response.headers.get_list("Set-Cookie"),
                         ["str=asdf; Path=/",
                          "unicode=qwer; Path=/",
                          "bytes=zxcv; Path=/"])

    def test_get_cookie(self):
        response = self.fetch("/get", headers={"Cookie": "foo=bar"})
        self.assertEqual(response.body, b("bar"))

        response = self.fetch("/get", headers={"Cookie": 'foo="bar"'})
        self.assertEqual(response.body, b("bar"))

    def test_set_cookie_domain(self):
        response = self.fetch("/set_domain")
        self.assertEqual(response.headers.get_list("Set-Cookie"),
                         ["unicode_args=blah; Domain=foo.com; Path=/foo"])

    def test_cookie_special_char(self):
        response = self.fetch("/special_char")
        headers = response.headers.get_list("Set-Cookie")
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0], 'equals="a=b"; Path=/')
        # python 2.7 octal-escapes the semicolon; older versions leave it alone
        self.assertTrue(headers[1] in ('semicolon="a;b"; Path=/',
                                       'semicolon="a\\073b"; Path=/'),
                        headers[1])
        self.assertEqual(headers[2], 'quote="a\\"b"; Path=/')

        data = [('foo=a=b', 'a=b'),
                ('foo="a=b"', 'a=b'),
                ('foo="a;b"', 'a;b'),
                #('foo=a\\073b', 'a;b'),  # even encoded, ";" is a delimiter
                ('foo="a\\073b"', 'a;b'),
                ('foo="a\\"b"', 'a"b'),
                ]
        for header, expected in data:
            logging.info("trying %r", header)
            response = self.fetch("/get", headers={"Cookie": header})
            self.assertEqual(response.body, utf8(expected))

class AuthRedirectRequestHandler(RequestHandler):
    def initialize(self, login_url):
        self.login_url = login_url

    def get_login_url(self):
        return self.login_url

    @authenticated
    def get(self):
        # we'll never actually get here because the test doesn't follow redirects
        self.send_error(500)

class AuthRedirectTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/relative', AuthRedirectRequestHandler,
                             dict(login_url='/login')),
                            ('/absolute', AuthRedirectRequestHandler,
                             dict(login_url='http://example.com/login'))])

    def test_relative_auth_redirect(self):
        self.http_client.fetch(self.get_url('/relative'), self.stop,
                               follow_redirects=False)
        response = self.wait()
        self.assertEqual(response.code, 302)
        self.assertEqual(response.headers['Location'], '/login?next=%2Frelative')

    def test_absolute_auth_redirect(self):
        self.http_client.fetch(self.get_url('/absolute'), self.stop,
                               follow_redirects=False)
        response = self.wait()
        self.assertEqual(response.code, 302)
        self.assertTrue(re.match(
            'http://example.com/login\?next=http%3A%2F%2Flocalhost%3A[0-9]+%2Fabsolute',
            response.headers['Location']), response.headers['Location'])


class ConnectionCloseHandler(RequestHandler):
    def initialize(self, test):
        self.test = test

    @asynchronous
    def get(self):
        self.test.on_handler_waiting()

    def on_connection_close(self):
        self.test.on_connection_close()

class ConnectionCloseTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([('/', ConnectionCloseHandler, dict(test=self))])

    def test_connection_close(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        s.connect(("localhost", self.get_http_port()))
        self.stream = IOStream(s, io_loop=self.io_loop)
        self.stream.write(b("GET / HTTP/1.0\r\n\r\n"))
        self.wait()

    def on_handler_waiting(self):
        logging.info('handler waiting')
        self.stream.close()

    def on_connection_close(self):
        logging.info('connection closed')
        self.stop()

class EchoHandler(RequestHandler):
    def get(self, path):
        # Type checks: web.py interfaces convert argument values to
        # unicode strings (by default, but see also decode_argument).
        # In httpserver.py (i.e. self.request.arguments), they're left
        # as bytes.  Keys are always native strings.
        for key in self.request.arguments:
            assert type(key) == str, repr(key)
            for value in self.request.arguments[key]:
                assert type(value) == bytes_type, repr(value)
            for value in self.get_arguments(key):
                assert type(value) == unicode, repr(value)
        assert type(path) == unicode, repr(path)
        self.write(dict(path=path,
                        args=recursive_unicode(self.request.arguments)))

class RequestEncodingTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([("/(.*)", EchoHandler)])

    def test_question_mark(self):
        # Ensure that url-encoded question marks are handled properly
        self.assertEqual(json_decode(self.fetch('/%3F').body),
                         dict(path='?', args={}))
        self.assertEqual(json_decode(self.fetch('/%3F?%3F=%3F').body),
                         dict(path='?', args={'?': ['?']}))

    def test_path_encoding(self):
        # Path components and query arguments should be decoded the same way
        self.assertEqual(json_decode(self.fetch('/%C3%A9?arg=%C3%A9').body),
                         {u"path":u"\u00e9",
                          u"args": {u"arg": [u"\u00e9"]}})

class TypeCheckHandler(RequestHandler):
    def prepare(self):
        self.errors = {}

        self.check_type('status', self.get_status(), int)

        # get_argument is an exception from the general rule of using
        # type str for non-body data mainly for historical reasons.
        self.check_type('argument', self.get_argument('foo'), unicode)
        self.check_type('cookie_key', self.cookies.keys()[0], str)
        self.check_type('cookie_value', self.cookies.values()[0].value, str)

        self.check_type('xsrf_token', self.xsrf_token, bytes_type)
        self.check_type('xsrf_form_html', self.xsrf_form_html(), str)

        self.check_type('reverse_url', self.reverse_url('typecheck', 'foo'), str)

        self.check_type('request_summary', self._request_summary(), str)

    def get(self, path_component):
        # path_component uses type unicode instead of str for consistency
        # with get_argument()
        self.check_type('path_component', path_component, unicode)
        self.write(self.errors)

    def post(self, path_component):
        self.check_type('path_component', path_component, unicode)
        self.write(self.errors)

    def check_type(self, name, obj, expected_type):
        actual_type = type(obj)
        if expected_type != actual_type:
            self.errors[name] = "expected %s, got %s" % (expected_type,
                                                         actual_type)

class DecodeArgHandler(RequestHandler):
    def decode_argument(self, value, name=None):
        assert type(value) == bytes_type, repr(value)
        # use self.request.arguments directly to avoid recursion
        if 'encoding' in self.request.arguments:
            return value.decode(to_unicode(self.request.arguments['encoding'][0]))
        else:
            return value

    def get(self, arg):
        def describe(s):
            if type(s) == bytes_type:
                return ["bytes", native_str(binascii.b2a_hex(s))]
            elif type(s) == unicode:
                return ["unicode", s]
            raise Exception("unknown type")
        self.write({'path': describe(arg),
                    'query': describe(self.get_argument("foo")),
                    })

class LinkifyHandler(RequestHandler):
    def get(self):
        self.render("linkify.html", message="http://example.com")

class UIModuleResourceHandler(RequestHandler):
    def get(self):
        self.render("page.html", entries=[1,2])

class OptionalPathHandler(RequestHandler):
    def get(self, path):
        self.write({"path": path})

class FlowControlHandler(RequestHandler):
    # These writes are too small to demonstrate real flow control,
    # but at least it shows that the callbacks get run.
    @asynchronous
    def get(self):
        self.write("1")
        self.flush(callback=self.step2)

    def step2(self):
        self.write("2")
        self.flush(callback=self.step3)

    def step3(self):
        self.write("3")
        self.finish()

class MultiHeaderHandler(RequestHandler):
    def get(self):
        self.set_header("x-overwrite", "1")
        self.set_header("x-overwrite", 2)
        self.add_header("x-multi", 3)
        self.add_header("x-multi", "4")

class WebTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        loader = DictLoader({
                "linkify.html": "{% module linkify(message) %}",
                "page.html": """\
<html><head></head><body>
{% for e in entries %}
{% module Template("entry.html", entry=e) %}
{% end %}
</body></html>""",
                "entry.html": """\
{{ set_resources(embedded_css=".entry { margin-bottom: 1em; }", embedded_javascript="js_embed()", css_files=["/base.css", "/foo.css"], javascript_files="/common.js", html_head="<meta>", html_body='<script src="/analytics.js"/>') }}
<div class="entry">...</div>""",
                })
        urls = [
            url("/typecheck/(.*)", TypeCheckHandler, name='typecheck'),
            url("/decode_arg/(.*)", DecodeArgHandler),
            url("/decode_arg_kw/(?P<arg>.*)", DecodeArgHandler),
            url("/linkify", LinkifyHandler),
            url("/uimodule_resources", UIModuleResourceHandler),
            url("/optional_path/(.+)?", OptionalPathHandler),
            url("/flow_control", FlowControlHandler),
            url("/multi_header", MultiHeaderHandler),
            ]
        return Application(urls,
                           template_loader=loader,
                           autoescape="xhtml_escape")

    def fetch_json(self, *args, **kwargs):
        response = self.fetch(*args, **kwargs)
        response.rethrow()
        return json_decode(response.body)

    def test_types(self):
        response = self.fetch("/typecheck/asdf?foo=bar",
                              headers={"Cookie": "cook=ie"})
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck/asdf?foo=bar", method="POST",
                              headers={"Cookie": "cook=ie"},
                              body="foo=bar")

    def test_decode_argument(self):
        # These urls all decode to the same thing
        urls = ["/decode_arg/%C3%A9?foo=%C3%A9&encoding=utf-8",
                "/decode_arg/%E9?foo=%E9&encoding=latin1",
                "/decode_arg_kw/%E9?foo=%E9&encoding=latin1",
                ]
        for url in urls:
            response = self.fetch(url)
            response.rethrow()
            data = json_decode(response.body)
            self.assertEqual(data, {u'path': [u'unicode', u'\u00e9'],
                                    u'query': [u'unicode', u'\u00e9'],
                                    })

        response = self.fetch("/decode_arg/%C3%A9?foo=%C3%A9")
        response.rethrow()
        data = json_decode(response.body)
        self.assertEqual(data, {u'path': [u'bytes', u'c3a9'],
                                u'query': [u'bytes', u'c3a9'],
                                })

    def test_uimodule_unescaped(self):
        response = self.fetch("/linkify")
        self.assertEqual(response.body,
                         b("<a href=\"http://example.com\">http://example.com</a>"))

    def test_uimodule_resources(self):
        response = self.fetch("/uimodule_resources")
        self.assertEqual(response.body, b("""\
<html><head><link href="/base.css" type="text/css" rel="stylesheet"/><link href="/foo.css" type="text/css" rel="stylesheet"/>
<style type="text/css">
.entry { margin-bottom: 1em; }
</style>
<meta>
</head><body>


<div class="entry">...</div>


<div class="entry">...</div>

<script src="/common.js" type="text/javascript"></script>
<script type="text/javascript">
//<![CDATA[
js_embed()
//]]>
</script>
<script src="/analytics.js"/>
</body></html>"""))

    def test_optional_path(self):
        self.assertEqual(self.fetch_json("/optional_path/foo"),
                         {u"path": u"foo"})
        self.assertEqual(self.fetch_json("/optional_path/"),
                         {u"path": None})

    def test_flow_control(self):
        self.assertEqual(self.fetch("/flow_control").body, b("123"))

    def test_multi_header(self):
        response = self.fetch("/multi_header")
        self.assertEqual(response.headers["x-overwrite"], "2")
        self.assertEqual(response.headers.get_list("x-multi"), ["3", "4"])


class ErrorResponseTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class DefaultHandler(RequestHandler):
            def get(self):
                if self.get_argument("status", None):
                    raise HTTPError(int(self.get_argument("status")))
                1/0

        class WriteErrorHandler(RequestHandler):
            def get(self):
                if self.get_argument("status", None):
                    self.send_error(int(self.get_argument("status")))
                else:
                    1/0

            def write_error(self, status_code, **kwargs):
                self.set_header("Content-Type", "text/plain")
                if "exc_info" in kwargs:
                    self.write("Exception: %s" % kwargs["exc_info"][0].__name__)
                else:
                    self.write("Status: %d" % status_code)

        class GetErrorHtmlHandler(RequestHandler):
            def get(self):
                if self.get_argument("status", None):
                    self.send_error(int(self.get_argument("status")))
                else:
                    1/0

            def get_error_html(self, status_code, **kwargs):
                self.set_header("Content-Type", "text/plain")
                if "exception" in kwargs:
                    self.write("Exception: %s" % sys.exc_info()[0].__name__)
                else:
                    self.write("Status: %d" % status_code)

        class FailedWriteErrorHandler(RequestHandler):
            def get(self):
                1/0

            def write_error(self, status_code, **kwargs):
                raise Exception("exception in write_error")


        return Application([
                url("/default", DefaultHandler),
                url("/write_error", WriteErrorHandler),
                url("/get_error_html", GetErrorHtmlHandler),
                url("/failed_write_error", FailedWriteErrorHandler),
                ])

    def test_default(self):
        response = self.fetch("/default")
        self.assertEqual(response.code, 500)
        self.assertTrue(b("500: Internal Server Error") in response.body)

        response = self.fetch("/default?status=503")
        self.assertEqual(response.code, 503)
        self.assertTrue(b("503: Service Unavailable") in response.body)

    def test_write_error(self):
        response = self.fetch("/write_error")
        self.assertEqual(response.code, 500)
        self.assertEqual(b("Exception: ZeroDivisionError"), response.body)

        response = self.fetch("/write_error?status=503")
        self.assertEqual(response.code, 503)
        self.assertEqual(b("Status: 503"), response.body)

    def test_get_error_html(self):
        response = self.fetch("/get_error_html")
        self.assertEqual(response.code, 500)
        self.assertEqual(b("Exception: ZeroDivisionError"), response.body)

        response = self.fetch("/get_error_html?status=503")
        self.assertEqual(response.code, 503)
        self.assertEqual(b("Status: 503"), response.body)

    def test_failed_write_error(self):
        response = self.fetch("/failed_write_error")
        self.assertEqual(response.code, 500)
        self.assertEqual(b(""), response.body)

class StaticFileTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class StaticUrlHandler(RequestHandler):
            def get(self, path):
                self.write(self.static_url(path))

        class AbsoluteStaticUrlHandler(RequestHandler):
            include_host = True
            def get(self, path):
                self.write(self.static_url(path))

        return Application([('/static_url/(.*)', StaticUrlHandler),
                            ('/abs_static_url/(.*)', AbsoluteStaticUrlHandler)],
                           static_path=os.path.join(os.path.dirname(__file__), 'static'))

    def test_static_files(self):
        response = self.fetch('/robots.txt')
        assert b("Disallow: /") in response.body

        response = self.fetch('/static/robots.txt')
        assert b("Disallow: /") in response.body

    def test_static_url(self):
        response = self.fetch("/static_url/robots.txt")
        self.assertEqual(response.body, b("/static/robots.txt?v=f71d2"))

    def test_absolute_static_url(self):
        response = self.fetch("/abs_static_url/robots.txt")
        self.assertEqual(response.body,
                         utf8(self.get_url("/") + "static/robots.txt?v=f71d2"))

class CustomStaticFileTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class MyStaticFileHandler(StaticFileHandler):
            def get(self, path):
                assert path == "foo.txt"
                self.write("bar")

            @classmethod
            def make_static_url(cls, settings, path):
                return "/static/%s?v=42" % path

        class StaticUrlHandler(RequestHandler):
            def get(self, path):
                self.write(self.static_url(path))

        return Application([("/static_url/(.*)", StaticUrlHandler)],
                           static_path="dummy",
                           static_handler_class=MyStaticFileHandler)

    def test_serve(self):
        response = self.fetch("/static/foo.txt")
        self.assertEqual(response.body, b("bar"))

    def test_static_url(self):
        response = self.fetch("/static_url/foo.txt")
        self.assertEqual(response.body, b("/static/foo.txt?v=42"))
