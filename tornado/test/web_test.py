from __future__ import absolute_import, division, with_statement
from tornado import gen
from tornado.escape import json_decode, utf8, to_unicode, recursive_unicode, native_str
from tornado.iostream import IOStream
from tornado.template import DictLoader
from tornado.testing import LogTrapTestCase, AsyncHTTPTestCase
from tornado.util import b, bytes_type, ObjectDict
from tornado.web import RequestHandler, authenticated, Application, asynchronous, url, HTTPError, StaticFileHandler, _create_signature, create_signed_value

import binascii
import logging
import os
import re
import socket
import sys


class SimpleHandlerTestCase(AsyncHTTPTestCase):
    """Simplified base class for tests that work with a single handler class.

    To use, define a nested class named ``Handler``.
    """
    def get_app(self):
        return Application([('/', self.Handler)],
                           log_function=lambda x: None)


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
        self.assertTrue(match)
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
        self.assertTrue(handler.get_secure_cookie('foo') is None)

    def test_arbitrary_bytes(self):
        # Secure cookies accept arbitrary data (which is base64 encoded).
        # Note that normal cookies accept only a subset of ascii.
        handler = CookieTestRequestHandler()
        handler.set_secure_cookie('foo', b('\xe9'))
        self.assertEqual(handler.get_secure_cookie('foo'), b('\xe9'))


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
                self.write(self.get_cookie("foo", "default"))

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

        class SetCookieOverwriteHandler(RequestHandler):
            def get(self):
                self.set_cookie("a", "b", domain="example.com")
                self.set_cookie("c", "d", domain="example.com")
                # A second call with the same name clobbers the first.
                # Attributes from the first call are not carried over.
                self.set_cookie("a", "e")

        return Application([
                ("/set", SetCookieHandler),
                ("/get", GetCookieHandler),
                ("/set_domain", SetCookieDomainHandler),
                ("/special_char", SetCookieSpecialCharHandler),
                ("/set_overwrite", SetCookieOverwriteHandler),
                ])

    def test_set_cookie(self):
        response = self.fetch("/set")
        self.assertEqual(sorted(response.headers.get_list("Set-Cookie")),
                         ["bytes=zxcv; Path=/",
                          "str=asdf; Path=/",
                          "unicode=qwer; Path=/",
                          ])

    def test_get_cookie(self):
        response = self.fetch("/get", headers={"Cookie": "foo=bar"})
        self.assertEqual(response.body, b("bar"))

        response = self.fetch("/get", headers={"Cookie": 'foo="bar"'})
        self.assertEqual(response.body, b("bar"))

        response = self.fetch("/get", headers={"Cookie": "/=exception;"})
        self.assertEqual(response.body, b("default"))

    def test_set_cookie_domain(self):
        response = self.fetch("/set_domain")
        self.assertEqual(response.headers.get_list("Set-Cookie"),
                         ["unicode_args=blah; Domain=foo.com; Path=/foo"])

    def test_cookie_special_char(self):
        response = self.fetch("/special_char")
        headers = sorted(response.headers.get_list("Set-Cookie"))
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0], 'equals="a=b"; Path=/')
        self.assertEqual(headers[1], 'quote="a\\"b"; Path=/')
        # python 2.7 octal-escapes the semicolon; older versions leave it alone
        self.assertTrue(headers[2] in ('semicolon="a;b"; Path=/',
                                       'semicolon="a\\073b"; Path=/'),
                        headers[2])

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

    def test_set_cookie_overwrite(self):
        response = self.fetch("/set_overwrite")
        headers = response.headers.get_list("Set-Cookie")
        self.assertEqual(sorted(headers),
                         ["a=e; Path=/", "c=d; Domain=example.com; Path=/"])


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
    def get(self, *path_args):
        # Type checks: web.py interfaces convert argument values to
        # unicode strings (by default, but see also decode_argument).
        # In httpserver.py (i.e. self.request.arguments), they're left
        # as bytes.  Keys are always native strings.
        for key in self.request.arguments:
            if type(key) != str:
                raise Exception("incorrect type for key: %r" % type(key))
            for value in self.request.arguments[key]:
                if type(value) != bytes_type:
                    raise Exception("incorrect type for value: %r" %
                                    type(value))
            for value in self.get_arguments(key):
                if type(value) != unicode:
                    raise Exception("incorrect type for value: %r" %
                                    type(value))
        for arg in path_args:
            if type(arg) != unicode:
                raise Exception("incorrect type for path arg: %r" % type(arg))
        self.write(dict(path=self.request.path,
                        path_args=path_args,
                        args=recursive_unicode(self.request.arguments)))


class RequestEncodingTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([
                ("/group/(.*)", EchoHandler),
                ("/slashes/([^/]*)/([^/]*)", EchoHandler),
                ])

    def fetch_json(self, path):
        return json_decode(self.fetch(path).body)

    def test_group_question_mark(self):
        # Ensure that url-encoded question marks are handled properly
        self.assertEqual(self.fetch_json('/group/%3F'),
                         dict(path='/group/%3F', path_args=['?'], args={}))
        self.assertEqual(self.fetch_json('/group/%3F?%3F=%3F'),
                         dict(path='/group/%3F', path_args=['?'], args={'?': ['?']}))

    def test_group_encoding(self):
        # Path components and query arguments should be decoded the same way
        self.assertEqual(self.fetch_json('/group/%C3%A9?arg=%C3%A9'),
                         {u"path": u"/group/%C3%A9",
                          u"path_args": [u"\u00e9"],
                          u"args": {u"arg": [u"\u00e9"]}})

    def test_slashes(self):
        # Slashes may be escaped to appear as a single "directory" in the path,
        # but they are then unescaped when passed to the get() method.
        self.assertEqual(self.fetch_json('/slashes/foo/bar'),
                         dict(path="/slashes/foo/bar",
                              path_args=["foo", "bar"],
                              args={}))
        self.assertEqual(self.fetch_json('/slashes/a%2Fb/c%2Fd'),
                         dict(path="/slashes/a%2Fb/c%2Fd",
                              path_args=["a/b", "c/d"],
                              args={}))


class TypeCheckHandler(RequestHandler):
    def prepare(self):
        self.errors = {}

        self.check_type('status', self.get_status(), int)

        # get_argument is an exception from the general rule of using
        # type str for non-body data mainly for historical reasons.
        self.check_type('argument', self.get_argument('foo'), unicode)
        self.check_type('cookie_key', self.cookies.keys()[0], str)
        self.check_type('cookie_value', self.cookies.values()[0].value, str)

        # Secure cookies return bytes because they can contain arbitrary
        # data, but regular cookies are native strings.
        if self.cookies.keys() != ['asdf']:
            raise Exception("unexpected values for cookie keys: %r" %
                            self.cookies.keys())
        self.check_type('get_secure_cookie', self.get_secure_cookie('asdf'), bytes_type)
        self.check_type('get_cookie', self.get_cookie('asdf'), str)

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
        if type(value) != bytes_type:
            raise Exception("unexpected type for value: %r" % type(value))
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
        self.render("page.html", entries=[1, 2])


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


class RedirectHandler(RequestHandler):
    def get(self):
        if self.get_argument('permanent', None) is not None:
            self.redirect('/', permanent=int(self.get_argument('permanent')))
        elif self.get_argument('status', None) is not None:
            self.redirect('/', status=int(self.get_argument('status')))
        else:
            raise Exception("didn't get permanent or status arguments")


class EmptyFlushCallbackHandler(RequestHandler):
    @gen.engine
    @asynchronous
    def get(self):
        # Ensure that the flush callback is run whether or not there
        # was any output.
        yield gen.Task(self.flush)  # "empty" flush, but writes headers
        yield gen.Task(self.flush)  # empty flush
        self.write("o")
        yield gen.Task(self.flush)  # flushes the "o"
        yield gen.Task(self.flush)  # empty flush
        self.finish("k")


class HeaderInjectionHandler(RequestHandler):
    def get(self):
        try:
            self.set_header("X-Foo", "foo\r\nX-Bar: baz")
            raise Exception("Didn't get expected exception")
        except ValueError, e:
            if "Unsafe header value" in str(e):
                self.finish(b("ok"))
            else:
                raise


# This test is shared with wsgi_test.py
class WSGISafeWebTest(AsyncHTTPTestCase, LogTrapTestCase):
    COOKIE_SECRET = "WebTest.COOKIE_SECRET"

    def get_app(self):
        self.app = Application(self.get_handlers(), **self.get_app_kwargs())
        return self.app

    def get_app_kwargs(self):
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
        return dict(template_loader=loader,
                    autoescape="xhtml_escape",
                    cookie_secret=self.COOKIE_SECRET)

    def get_handlers(self):
        urls = [
            url("/typecheck/(.*)", TypeCheckHandler, name='typecheck'),
            url("/decode_arg/(.*)", DecodeArgHandler, name='decode_arg'),
            url("/decode_arg_kw/(?P<arg>.*)", DecodeArgHandler),
            url("/linkify", LinkifyHandler),
            url("/uimodule_resources", UIModuleResourceHandler),
            url("/optional_path/(.+)?", OptionalPathHandler),
            url("/multi_header", MultiHeaderHandler),
            url("/redirect", RedirectHandler),
            url("/header_injection", HeaderInjectionHandler),
            ]
        return urls

    def fetch_json(self, *args, **kwargs):
        response = self.fetch(*args, **kwargs)
        response.rethrow()
        return json_decode(response.body)

    def test_types(self):
        cookie_value = to_unicode(create_signed_value(self.COOKIE_SECRET,
                                                      "asdf", "qwer"))
        response = self.fetch("/typecheck/asdf?foo=bar",
                              headers={"Cookie": "asdf=" + cookie_value})
        data = json_decode(response.body)
        self.assertEqual(data, {})

        response = self.fetch("/typecheck/asdf?foo=bar", method="POST",
                              headers={"Cookie": "asdf=" + cookie_value},
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

    def test_reverse_url(self):
        self.assertEqual(self.app.reverse_url('decode_arg', 'foo'),
                         '/decode_arg/foo')
        self.assertEqual(self.app.reverse_url('decode_arg', 42),
                         '/decode_arg/42')
        self.assertEqual(self.app.reverse_url('decode_arg', b('\xe9')),
                         '/decode_arg/%E9')
        self.assertEqual(self.app.reverse_url('decode_arg', u'\u00e9'),
                         '/decode_arg/%C3%A9')

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

    def test_multi_header(self):
        response = self.fetch("/multi_header")
        self.assertEqual(response.headers["x-overwrite"], "2")
        self.assertEqual(response.headers.get_list("x-multi"), ["3", "4"])

    def test_redirect(self):
        response = self.fetch("/redirect?permanent=1", follow_redirects=False)
        self.assertEqual(response.code, 301)
        response = self.fetch("/redirect?permanent=0", follow_redirects=False)
        self.assertEqual(response.code, 302)
        response = self.fetch("/redirect?status=307", follow_redirects=False)
        self.assertEqual(response.code, 307)

    def test_header_injection(self):
        response = self.fetch("/header_injection")
        self.assertEqual(response.body, b("ok"))


class NonWSGIWebTests(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        urls = [
            ("/flow_control", FlowControlHandler),
            ("/empty_flush", EmptyFlushCallbackHandler),
            ]
        return Application(urls)

    def test_flow_control(self):
        self.assertEqual(self.fetch("/flow_control").body, b("123"))

    def test_empty_flush(self):
        response = self.fetch("/empty_flush")
        self.assertEqual(response.body, b("ok"))


class ErrorResponseTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class DefaultHandler(RequestHandler):
            def get(self):
                if self.get_argument("status", None):
                    raise HTTPError(int(self.get_argument("status")))
                1 / 0

        class WriteErrorHandler(RequestHandler):
            def get(self):
                if self.get_argument("status", None):
                    self.send_error(int(self.get_argument("status")))
                else:
                    1 / 0

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
                    1 / 0

            def get_error_html(self, status_code, **kwargs):
                self.set_header("Content-Type", "text/plain")
                if "exception" in kwargs:
                    self.write("Exception: %s" % sys.exc_info()[0].__name__)
                else:
                    self.write("Status: %d" % status_code)

        class FailedWriteErrorHandler(RequestHandler):
            def get(self):
                1 / 0

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

        class OverrideStaticUrlHandler(RequestHandler):
            def get(self, path):
                do_include = bool(self.get_argument("include_host"))
                self.include_host = not do_include

                regular_url = self.static_url(path)
                override_url = self.static_url(path, include_host=do_include)
                if override_url == regular_url:
                    return self.write(str(False))

                protocol = self.request.protocol + "://"
                protocol_length = len(protocol)
                check_regular = regular_url.find(protocol, 0, protocol_length)
                check_override = override_url.find(protocol, 0, protocol_length)

                if do_include:
                    result = (check_override == 0 and check_regular == -1)
                else:
                    result = (check_override == -1 and check_regular == 0)
                self.write(str(result))

        return Application([('/static_url/(.*)', StaticUrlHandler),
                            ('/abs_static_url/(.*)', AbsoluteStaticUrlHandler),
                            ('/override_static_url/(.*)', OverrideStaticUrlHandler)],
                           static_path=os.path.join(os.path.dirname(__file__), 'static'))

    def test_static_files(self):
        response = self.fetch('/robots.txt')
        self.assertTrue(b("Disallow: /") in response.body)

        response = self.fetch('/static/robots.txt')
        self.assertTrue(b("Disallow: /") in response.body)

    def test_static_url(self):
        response = self.fetch("/static_url/robots.txt")
        self.assertEqual(response.body, b("/static/robots.txt?v=f71d2"))

    def test_absolute_static_url(self):
        response = self.fetch("/abs_static_url/robots.txt")
        self.assertEqual(response.body,
                         utf8(self.get_url("/") + "static/robots.txt?v=f71d2"))

    def test_include_host_override(self):
        self._trigger_include_host_check(False)
        self._trigger_include_host_check(True)

    def _trigger_include_host_check(self, include_host):
        path = "/override_static_url/robots.txt?include_host=%s"
        response = self.fetch(path % int(include_host))
        self.assertEqual(response.body, utf8(str(True)))

    def test_static_304(self):
        response1 = self.fetch("/static/robots.txt")
        response2 = self.fetch("/static/robots.txt", headers={
                'If-Modified-Since': response1.headers['Last-Modified']})
        self.assertEqual(response2.code, 304)
        self.assertTrue('Content-Length' not in response2.headers)
        self.assertTrue('Last-Modified' not in response2.headers)


class CustomStaticFileTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class MyStaticFileHandler(StaticFileHandler):
            def get(self, path):
                path = self.parse_url_path(path)
                if path != "foo.txt":
                    raise Exception("unexpected path: %r" % path)
                self.write("bar")

            @classmethod
            def make_static_url(cls, settings, path):
                cls.get_version(settings, path)
                extension_index = path.rindex('.')
                before_version = path[:extension_index]
                after_version = path[(extension_index + 1):]
                return '/static/%s.%s.%s' % (before_version, 42, after_version)

            @classmethod
            def parse_url_path(cls, url_path):
                extension_index = url_path.rindex('.')
                version_index = url_path.rindex('.', 0, extension_index)
                return '%s%s' % (url_path[:version_index],
                                 url_path[extension_index:])

        class StaticUrlHandler(RequestHandler):
            def get(self, path):
                self.write(self.static_url(path))

        return Application([("/static_url/(.*)", StaticUrlHandler)],
                           static_path="dummy",
                           static_handler_class=MyStaticFileHandler)

    def test_serve(self):
        response = self.fetch("/static/foo.42.txt")
        self.assertEqual(response.body, b("bar"))

    def test_static_url(self):
        response = self.fetch("/static_url/foo.txt")
        self.assertEqual(response.body, b("/static/foo.42.txt"))


class NamedURLSpecGroupsTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        class EchoHandler(RequestHandler):
            def get(self, path):
                self.write(path)

        return Application([("/str/(?P<path>.*)", EchoHandler),
                            (u"/unicode/(?P<path>.*)", EchoHandler)])

    def test_named_urlspec_groups(self):
        response = self.fetch("/str/foo")
        self.assertEqual(response.body, b("foo"))

        response = self.fetch("/unicode/bar")
        self.assertEqual(response.body, b("bar"))


class ClearHeaderTest(SimpleHandlerTestCase):
    class Handler(RequestHandler):
        def get(self):
            self.set_header("h1", "foo")
            self.set_header("h2", "bar")
            self.clear_header("h1")
            self.clear_header("nonexistent")

    def test_clear_header(self):
        response = self.fetch("/")
        self.assertTrue("h1" not in response.headers)
        self.assertEqual(response.headers["h2"], "bar")


class Header304Test(SimpleHandlerTestCase):
    class Handler(RequestHandler):
        def get(self):
            self.set_header("Content-Language", "en_US")
            self.write("hello")

    def test_304_headers(self):
        response1 = self.fetch('/')
        self.assertEqual(response1.headers["Content-Length"], "5")
        self.assertEqual(response1.headers["Content-Language"], "en_US")

        response2 = self.fetch('/', headers={
                'If-None-Match': response1.headers["Etag"]})
        self.assertEqual(response2.code, 304)
        self.assertTrue("Content-Length" not in response2.headers)
        self.assertTrue("Content-Language" not in response2.headers)
        # Not an entity header, but should not be added to 304s by chunking
        self.assertTrue("Transfer-Encoding" not in response2.headers)
