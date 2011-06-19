#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""WSGI support for the Tornado web framework.

WSGI is the Python standard for web servers, and allows for interoperability
between Tornado and other Python web frameworks and servers.  This module
provides WSGI support in two ways:

* `WSGIApplication` is a version of `tornado.web.Application` that can run 
  inside a WSGI server.  This is useful for running a Tornado app on another
  HTTP server, such as Google App Engine.  See the `WSGIApplication` class
  documentation for limitations that apply.
* `WSGIContainer` lets you run other WSGI applications and frameworks on the
  Tornado HTTP server.  For example, with this class you can mix Django
  and Tornado handlers in a single server.
"""

import cgi
import httplib
import logging
import sys
import time
import tornado
import urllib

from tornado import escape
from tornado import httputil
from tornado import web
from tornado.escape import native_str, utf8
from tornado.util import b

try:
    from io import BytesIO  # python 3
except ImportError:
    from cStringIO import StringIO as BytesIO  # python 2

class WSGIApplication(web.Application):
    """A WSGI equivalent of `tornado.web.Application`.

    WSGIApplication is very similar to web.Application, except no
    asynchronous methods are supported (since WSGI does not support
    non-blocking requests properly). If you call self.flush() or other
    asynchronous methods in your request handlers running in a
    WSGIApplication, we throw an exception.

    Example usage::

        import tornado.web
        import tornado.wsgi
        import wsgiref.simple_server

        class MainHandler(tornado.web.RequestHandler):
            def get(self):
                self.write("Hello, world")

        if __name__ == "__main__":
            application = tornado.wsgi.WSGIApplication([
                (r"/", MainHandler),
            ])
            server = wsgiref.simple_server.make_server('', 8888, application)
            server.serve_forever()

    See the 'appengine' demo for an example of using this module to run
    a Tornado app on Google AppEngine.

    Since no asynchronous methods are available for WSGI applications, the
    httpclient and auth modules are both not available for WSGI applications.
    We support the same interface, but handlers running in a WSGIApplication
    do not support flush() or asynchronous methods. 
    """
    def __init__(self, handlers=None, default_host="", **settings):
        web.Application.__init__(self, handlers, default_host, transforms=[],
                                 wsgi=True, **settings)

    def __call__(self, environ, start_response):
        handler = web.Application.__call__(self, HTTPRequest(environ))
        assert handler._finished
        status = str(handler._status_code) + " " + \
            httplib.responses[handler._status_code]
        headers = handler._headers.items()
        for cookie_dict in getattr(handler, "_new_cookies", []):
            for cookie in cookie_dict.values():
                headers.append(("Set-Cookie", cookie.OutputString(None)))
        start_response(status,
                       [(native_str(k), native_str(v)) for (k,v) in headers])
        return handler._write_buffer


class HTTPRequest(object):
    """Mimics `tornado.httpserver.HTTPRequest` for WSGI applications."""
    def __init__(self, environ):
        """Parses the given WSGI environ to construct the request."""
        self.method = environ["REQUEST_METHOD"]
        self.path = urllib.quote(environ.get("SCRIPT_NAME", ""))
        self.path += urllib.quote(environ.get("PATH_INFO", ""))
        self.uri = self.path
        self.arguments = {}
        self.query = environ.get("QUERY_STRING", "")
        if self.query:
            self.uri += "?" + self.query
            arguments = cgi.parse_qs(self.query)
            for name, values in arguments.iteritems():
                values = [v for v in values if v]
                if values: self.arguments[name] = values
        self.version = "HTTP/1.1"
        self.headers = httputil.HTTPHeaders()
        if environ.get("CONTENT_TYPE"):
            self.headers["Content-Type"] = environ["CONTENT_TYPE"]
        if environ.get("CONTENT_LENGTH"):
            self.headers["Content-Length"] = environ["CONTENT_LENGTH"]
        for key in environ:
            if key.startswith("HTTP_"):
                self.headers[key[5:].replace("_", "-")] = environ[key]
        if self.headers.get("Content-Length"):
            self.body = environ["wsgi.input"].read(
                int(self.headers["Content-Length"]))
        else:
            self.body = ""
        self.protocol = environ["wsgi.url_scheme"]
        self.remote_ip = environ.get("REMOTE_ADDR", "")
        if environ.get("HTTP_HOST"):
            self.host = environ["HTTP_HOST"]
        else:
            self.host = environ["SERVER_NAME"]

        # Parse request body
        self.files = {}
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("application/x-www-form-urlencoded"):
            for name, values in cgi.parse_qs(self.body).iteritems():
                self.arguments.setdefault(name, []).extend(values)
        elif content_type.startswith("multipart/form-data"):
            if 'boundary=' in content_type:
                boundary = content_type.split('boundary=',1)[1]
                if boundary:
                    httputil.parse_multipart_form_data(
                        utf8(boundary), self.body, self.arguments, self.files)
            else:
                logging.warning("Invalid multipart/form-data")

        self._start_time = time.time()
        self._finish_time = None

    def supports_http_1_1(self):
        """Returns True if this request supports HTTP/1.1 semantics"""
        return self.version == "HTTP/1.1"

    def full_url(self):
        """Reconstructs the full URL for this request."""
        return self.protocol + "://" + self.host + self.uri

    def request_time(self):
        """Returns the amount of time it took for this request to execute."""
        if self._finish_time is None:
            return time.time() - self._start_time
        else:
            return self._finish_time - self._start_time


class WSGIContainer(object):
    r"""Makes a WSGI-compatible function runnable on Tornado's HTTP server.

    Wrap a WSGI function in a WSGIContainer and pass it to HTTPServer to
    run it. For example::

        def simple_app(environ, start_response):
            status = "200 OK"
            response_headers = [("Content-type", "text/plain")]
            start_response(status, response_headers)
            return ["Hello world!\n"]

        container = tornado.wsgi.WSGIContainer(simple_app)
        http_server = tornado.httpserver.HTTPServer(container)
        http_server.listen(8888)
        tornado.ioloop.IOLoop.instance().start()

    This class is intended to let other frameworks (Django, web.py, etc)
    run on the Tornado HTTP server and I/O loop.

    The `tornado.web.FallbackHandler` class is often useful for mixing
    Tornado and WSGI apps in the same server.  See
    https://github.com/bdarnell/django-tornado-demo for a complete example.
    """
    def __init__(self, wsgi_application):
        self.wsgi_application = wsgi_application

    def __call__(self, request):
        data = {}
        response = []
        def start_response(status, response_headers, exc_info=None):
            data["status"] = status
            data["headers"] = response_headers
            return response.append
        app_response = self.wsgi_application(
            WSGIContainer.environ(request), start_response)
        response.extend(app_response)
        body = b("").join(response)
        if hasattr(app_response, "close"):
            app_response.close()
        if not data: raise Exception("WSGI app did not call start_response")

        status_code = int(data["status"].split()[0])
        headers = data["headers"]
        header_set = set(k.lower() for (k,v) in headers)
        body = escape.utf8(body)
        if "content-length" not in header_set:
            headers.append(("Content-Length", str(len(body))))
        if "content-type" not in header_set:
            headers.append(("Content-Type", "text/html; charset=UTF-8"))
        if "server" not in header_set:
            headers.append(("Server", "TornadoServer/%s" % tornado.version))

        parts = [escape.utf8("HTTP/1.1 " + data["status"] + "\r\n")]
        for key, value in headers:
            parts.append(escape.utf8(key) + b(": ") + escape.utf8(value) + b("\r\n"))
        parts.append(b("\r\n"))
        parts.append(body)
        request.write(b("").join(parts))
        request.finish()
        self._log(status_code, request)

    @staticmethod
    def environ(request):
        """Converts a `tornado.httpserver.HTTPRequest` to a WSGI environment.
        """
        hostport = request.host.split(":")
        if len(hostport) == 2:
            host = hostport[0]
            port = int(hostport[1])
        else:
            host = request.host
            port = 443 if request.protocol == "https" else 80
        environ = {
            "REQUEST_METHOD": request.method,
            "SCRIPT_NAME": "",
            "PATH_INFO": urllib.unquote(request.path),
            "QUERY_STRING": request.query,
            "REMOTE_ADDR": request.remote_ip,
            "SERVER_NAME": host,
            "SERVER_PORT": str(port),
            "SERVER_PROTOCOL": request.version,
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": request.protocol,
            "wsgi.input": BytesIO(escape.utf8(request.body)),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": False,
            "wsgi.multiprocess": True,
            "wsgi.run_once": False,
        }
        if "Content-Type" in request.headers:
            environ["CONTENT_TYPE"] = request.headers.pop("Content-Type")
        if "Content-Length" in request.headers:
            environ["CONTENT_LENGTH"] = request.headers.pop("Content-Length")
        for key, value in request.headers.iteritems():
            environ["HTTP_" + key.replace("-", "_").upper()] = value
        return environ

    def _log(self, status_code, request):
        if status_code < 400:
            log_method = logging.info
        elif status_code < 500:
            log_method = logging.warning
        else:
            log_method = logging.error
        request_time = 1000.0 * request.request_time()
        summary = request.method + " " + request.uri + " (" + \
            request.remote_ip + ")"
        log_method("%d %s %.2fms", status_code, summary, request_time)
