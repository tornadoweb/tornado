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

We export WSGIApplication, which is very similar to web.Application, except
no asynchronous methods are supported (since WSGI does not support
non-blocking requests properly). If you call self.flush() or other
asynchronous methods in your request handlers running in a WSGIApplication,
we throw an exception.

Example usage:

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
"""

import cgi
import httplib
import logging
import time
import urllib
import web


class WSGIApplication(web.Application):
    """A WSGI-equivalent of web.Application.

    We support the same interface, but handlers running in a WSGIApplication
    do not support flush() or asynchronous methods.
    """
    def __init__(self, handlers=None, default_host="", **settings):
        web.Application.__init__(self, handlers, default_host, transforms=[],
                                 **settings)
        self._wsgi = True

    def __call__(self, environ, start_response):
        handler = web.Application.__call__(self, HTTPRequest(environ))
        assert handler._finished
        status = str(handler._status_code) + " " + \
            httplib.responses[handler._status_code]
        headers = handler._headers.items()
        for cookie_dict in getattr(handler, "_new_cookies", []):
            for cookie in cookie_dict.values():
                headers.append(("Set-Cookie", cookie.OutputString(None)))
        start_response(status, headers)
        return handler._write_buffer


class HTTPRequest(object):
    """Mimics httpserver.HTTPRequest for WSGI applications."""
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
        self.headers = HTTPHeaders()
        if environ.get("CONTENT_TYPE"):
            self.headers["Content-Type"] = environ["CONTENT_TYPE"]
        if environ.get("CONTENT_LENGTH"):
            self.headers["Content-Length"] = int(environ["CONTENT_LENGTH"])
        for key in environ:
            if key.startswith("HTTP_"):
                self.headers[key[5:].replace("_", "-")] = environ[key]
        if self.headers.get("Content-Length"):
            self.body = environ["wsgi.input"].read()
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
            boundary = content_type[30:]
            if boundary: self._parse_mime_body(boundary, data)

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

    def _parse_mime_body(self, boundary):
        if self.body.endswith("\r\n"):
            footer_length = len(boundary) + 6
        else:
            footer_length = len(boundary) + 4
        parts = self.body[:-footer_length].split("--" + boundary + "\r\n")
        for part in parts:
            if not part: continue
            eoh = part.find("\r\n\r\n")
            if eoh == -1:
                logging.warning("multipart/form-data missing headers")
                continue
            headers = HTTPHeaders.parse(part[:eoh])
            name_header = headers.get("Content-Disposition", "")
            if not name_header.startswith("form-data;") or \
               not part.endswith("\r\n"):
                logging.warning("Invalid multipart/form-data")
                continue
            value = part[eoh + 4:-2]
            name_values = {}
            for name_part in name_header[10:].split(";"):
                name, name_value = name_part.strip().split("=", 1)
                name_values[name] = name_value.strip('"').decode("utf-8")
            if not name_values.get("name"):
                logging.warning("multipart/form-data value missing name")
                continue
            name = name_values["name"]
            if name_values.get("filename"):
                ctype = headers.get("Content-Type", "application/unknown")
                self.files.setdefault(name, []).append(dict(
                    filename=name_values["filename"], body=value,
                    content_type=ctype))
            else:
                self.arguments.setdefault(name, []).append(value)


class HTTPHeaders(dict):
    """A dictionary that maintains Http-Header-Case for all keys."""
    def __setitem__(self, name, value):
        dict.__setitem__(self, self._normalize_name(name), value)

    def __getitem__(self, name):
        return dict.__getitem__(self, self._normalize_name(name))

    def _normalize_name(self, name):
        return intern("-".join([w.capitalize() for w in name.split("-")]))
