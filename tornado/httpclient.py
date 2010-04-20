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

"""Blocking and non-blocking HTTP client implementations using pycurl."""

import calendar
import collections
import cStringIO
import email.utils
import errno
import functools
import httplib
import ioloop
import logging
import pycurl
import time
import weakref

_log = logging.getLogger('tornado.httpclient')

class HTTPClient(object):
    """A blocking HTTP client backed with pycurl.

    Typical usage looks like this:

        http_client = httpclient.HTTPClient()
        try:
            response = http_client.fetch("http://www.google.com/")
            print response.body
        except httpclient.HTTPError, e:
            print "Error:", e

    fetch() can take a string URL or an HTTPRequest instance, which offers
    more options, like executing POST/PUT/DELETE requests.
    """
    def __init__(self, max_simultaneous_connections=None):
        self._curl = _curl_create(max_simultaneous_connections)

    def __del__(self):
        self._curl.close()

    def fetch(self, request, **kwargs):
        """Executes an HTTPRequest, returning an HTTPResponse.

        If an error occurs during the fetch, we raise an HTTPError.
        """
        if not isinstance(request, HTTPRequest):
           request = HTTPRequest(url=request, **kwargs)
        buffer = cStringIO.StringIO()
        headers = {}
        try:
            _curl_setup_request(self._curl, request, buffer, headers)
            self._curl.perform()
            code = self._curl.getinfo(pycurl.HTTP_CODE)
            if code < 200 or code >= 300:
                raise HTTPError(code)
            effective_url = self._curl.getinfo(pycurl.EFFECTIVE_URL)
            return HTTPResponse(
                request=request, code=code, headers=headers,
                body=buffer.getvalue(), effective_url=effective_url)
        except pycurl.error, e:
            raise CurlError(*e)
        finally:
            buffer.close()


class AsyncHTTPClient(object):
    """An non-blocking HTTP client backed with pycurl.

    Example usage:

        import ioloop

        def handle_request(response):
            if response.error:
                print "Error:", response.error
            else:
                print response.body
            ioloop.IOLoop.instance().stop()

        http_client = httpclient.AsyncHTTPClient()
        http_client.fetch("http://www.google.com/", handle_request)
        ioloop.IOLoop.instance().start()

    fetch() can take a string URL or an HTTPRequest instance, which offers
    more options, like executing POST/PUT/DELETE requests.

    The keyword argument max_clients to the AsyncHTTPClient constructor
    determines the maximum number of simultaneous fetch() operations that
    can execute in parallel on each IOLoop.
    """
    _ASYNC_CLIENTS = weakref.WeakKeyDictionary()

    def __new__(cls, io_loop=None, max_clients=10,
                max_simultaneous_connections=None):
        # There is one client per IOLoop since they share curl instances
        io_loop = io_loop or ioloop.IOLoop.instance()
        if io_loop in cls._ASYNC_CLIENTS:
            return cls._ASYNC_CLIENTS[io_loop]
        else:
            instance = super(AsyncHTTPClient, cls).__new__(cls)
            instance.io_loop = io_loop
            instance._multi = pycurl.CurlMulti()
            instance._curls = [_curl_create(max_simultaneous_connections)
                               for i in xrange(max_clients)]
            instance._free_list = instance._curls[:]
            instance._requests = collections.deque()
            instance._fds = {}
            instance._events = {}
            instance._added_perform_callback = False
            instance._timeout = None
            instance._closed = False
            cls._ASYNC_CLIENTS[io_loop] = instance
            return instance

    def close(self):
        """Destroys this http client, freeing any file descriptors used.
        Not needed in normal use, but may be helpful in unittests that
        create and destroy http clients.  No other methods may be called
        on the AsyncHTTPClient after close().
        """
        del AsyncHTTPClient._ASYNC_CLIENTS[self.io_loop]
        for curl in self._curls:
            curl.close()
        self._multi.close()
        self._closed = True

    def fetch(self, request, callback, **kwargs):
        """Executes an HTTPRequest, calling callback with an HTTPResponse.

        If an error occurs during the fetch, the HTTPResponse given to the
        callback has a non-None error attribute that contains the exception
        encountered during the request. You can call response.reraise() to
        throw the exception (if any) in the callback.
        """
        if not isinstance(request, HTTPRequest):
           request = HTTPRequest(url=request, **kwargs)
        self._requests.append((request, callback))
        self._add_perform_callback()

    def _add_perform_callback(self):
        if not self._added_perform_callback:
            self.io_loop.add_callback(self._perform)
            self._added_perform_callback = True

    def _handle_events(self, fd, events):
        self._events[fd] = events
        self._add_perform_callback()

    def _handle_timeout(self):
        self._timeout = None
        self._perform()

    def _perform(self):
        self._added_perform_callback = False

        if self._closed:
            return

        while True:
            while True:
                ret, num_handles = self._multi.perform()
                if ret != pycurl.E_CALL_MULTI_PERFORM:
                    break

            # Handle completed fetches
            completed = 0
            while True:
                num_q, ok_list, err_list = self._multi.info_read()
                for curl in ok_list:
                    self._finish(curl)
                    completed += 1
                for curl, errnum, errmsg in err_list:
                    self._finish(curl, errnum, errmsg)
                    completed += 1
                if num_q == 0:
                    break

            # Start fetching new URLs
            started = 0
            while self._free_list and self._requests:
                started += 1
                curl = self._free_list.pop()
                (request, callback) = self._requests.popleft()
                curl.info = {
                    "headers": {},
                    "buffer": cStringIO.StringIO(),
                    "request": request,
                    "callback": callback,
                    "start_time": time.time(),
                }
                _curl_setup_request(curl, request, curl.info["buffer"],
                                    curl.info["headers"])
                self._multi.add_handle(curl)

            if not started and not completed:
                break

        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
            self._timeout = None

        if num_handles:
            self._timeout = self.io_loop.add_timeout(
                time.time() + 0.2, self._handle_timeout)

        # Wait for more I/O
        fds = {}
        (readable, writable, exceptable) = self._multi.fdset()
        for fd in readable:
            fds[fd] = fds.get(fd, 0) | 0x1 | 0x2
        for fd in writable:
            fds[fd] = fds.get(fd, 0) | 0x4
        for fd in exceptable:
            fds[fd] = fds.get(fd, 0) | 0x8 | 0x10

        for fd in self._fds:
            if fd not in fds:
                try:
                    self.io_loop.remove_handler(fd)
                except (OSError, IOError), e:
                    if e[0] != errno.ENOENT:
                        raise

        for fd, events in fds.iteritems():
            old_events = self._fds.get(fd, None)
            if old_events is None:
                self.io_loop.add_handler(fd, self._handle_events, events)
            elif old_events != events:
                try:
                    self.io_loop.update_handler(fd, events)
                except (OSError, IOError), e:
                    if e[0] == errno.ENOENT:
                        self.io_loop.add_handler(fd, self._handle_events,
                                                 events)
                    else:
                        raise
        self._fds = fds

    def _finish(self, curl, curl_error=None, curl_message=None):
        info = curl.info
        curl.info = None
        self._multi.remove_handle(curl)
        self._free_list.append(curl)
        if curl_error:
            error = CurlError(curl_error, curl_message)
            code = error.code
            body = None
            effective_url = None
        else:
            error = None
            code = curl.getinfo(pycurl.HTTP_CODE)
            body = info["buffer"].getvalue()
            effective_url = curl.getinfo(pycurl.EFFECTIVE_URL)
        info["buffer"].close()
        info["callback"](HTTPResponse(
            request=info["request"], code=code, headers=info["headers"],
            body=body, effective_url=effective_url, error=error,
            request_time=time.time() - info["start_time"]))


class HTTPRequest(object):
    def __init__(self, url, method="GET", headers={}, body=None,
                 auth_username=None, auth_password=None,
                 connect_timeout=20.0, request_timeout=20.0,
                 if_modified_since=None, follow_redirects=True,
                 max_redirects=5, user_agent=None, use_gzip=True,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None):
        if if_modified_since:
            timestamp = calendar.timegm(if_modified_since.utctimetuple())
            headers["If-Modified-Since"] = email.utils.formatdate(
                timestamp, localtime=False, usegmt=True)
        if "Pragma" not in headers:
            headers["Pragma"] = ""
        self.url = _utf8(url)
        self.method = method
        self.headers = headers
        self.body = body
        self.auth_username = _utf8(auth_username)
        self.auth_password = _utf8(auth_password)
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.use_gzip = use_gzip
        self.network_interface = network_interface
        self.streaming_callback = streaming_callback
        self.header_callback = header_callback
        self.prepare_curl_callback = prepare_curl_callback


class HTTPResponse(object):
    def __init__(self, request, code, headers={}, body="", effective_url=None,
                 error=None, request_time=None):
        self.request = request
        self.code = code
        self.headers = headers
        self.body = body
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        if error is None:
            if self.code < 200 or self.code >= 300:
                self.error = HTTPError(self.code)
            else:
                self.error = None
        else:
            self.error = error
        self.request_time = request_time

    def rethrow(self):
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in self.__dict__.iteritems())
        return "%s(%s)" % (self.__class__.__name__, args)


class HTTPError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        message = message or httplib.responses.get(code, "Unknown")
        Exception.__init__(self, "HTTP %d: %s" % (self.code, message))


class CurlError(HTTPError):
    def __init__(self, errno, message):
        HTTPError.__init__(self, 599, message)
        self.errno = errno


def _curl_create(max_simultaneous_connections=None):
    curl = pycurl.Curl()
    if _log.isEnabledFor(logging.DEBUG):
        curl.setopt(pycurl.VERBOSE, 1)
        curl.setopt(pycurl.DEBUGFUNCTION, _curl_debug)
    curl.setopt(pycurl.MAXCONNECTS, max_simultaneous_connections or 5)
    return curl


def _curl_setup_request(curl, request, buffer, headers):
    curl.setopt(pycurl.URL, request.url)
    curl.setopt(pycurl.HTTPHEADER,
                ["%s: %s" % i for i in request.headers.iteritems()])
    try:
        if request.header_callback:
            curl.setopt(pycurl.HEADERFUNCTION, request.header_callback)
        else:
            curl.setopt(pycurl.HEADERFUNCTION,
                        functools.partial(_curl_header_callback, headers))
    except:
        # Old version of curl; response will not include headers
        pass
    if request.streaming_callback:
        curl.setopt(pycurl.WRITEFUNCTION, request.streaming_callback)
    else:
        curl.setopt(pycurl.WRITEFUNCTION, buffer.write)
    curl.setopt(pycurl.FOLLOWLOCATION, request.follow_redirects)
    curl.setopt(pycurl.MAXREDIRS, request.max_redirects)
    curl.setopt(pycurl.CONNECTTIMEOUT, int(request.connect_timeout))
    curl.setopt(pycurl.TIMEOUT, int(request.request_timeout))
    if request.user_agent:
        curl.setopt(pycurl.USERAGENT, request.user_agent)
    else:
        curl.setopt(pycurl.USERAGENT, "Mozilla/5.0 (compatible; pycurl)")
    if request.network_interface:
        curl.setopt(pycurl.INTERFACE, request.network_interface)
    if request.use_gzip:
        curl.setopt(pycurl.ENCODING, "gzip,deflate")
    else:
        curl.setopt(pycurl.ENCODING, "none")

    # Set the request method through curl's retarded interface which makes
    # up names for almost every single method
    curl_options = {
        "GET": pycurl.HTTPGET,
        "POST": pycurl.POST,
        "PUT": pycurl.UPLOAD,
        "HEAD": pycurl.NOBODY,
    }
    custom_methods = set(["DELETE"])
    for o in curl_options.values():
        curl.setopt(o, False)
    if request.method in curl_options:
        curl.unsetopt(pycurl.CUSTOMREQUEST)
        curl.setopt(curl_options[request.method], True)
    elif request.method in custom_methods:
        curl.setopt(pycurl.CUSTOMREQUEST, request.method)
    else:
        raise KeyError('unknown method ' + request.method)

    # Handle curl's cryptic options for every individual HTTP method
    if request.method in ("POST", "PUT"):
        request_buffer =  cStringIO.StringIO(request.body)
        curl.setopt(pycurl.READFUNCTION, request_buffer.read)
        if request.method == "POST":
            def ioctl(cmd):
                if cmd == curl.IOCMD_RESTARTREAD:
                    request_buffer.seek(0)
            curl.setopt(pycurl.IOCTLFUNCTION, ioctl)
            curl.setopt(pycurl.POSTFIELDSIZE, len(request.body))
        else:
            curl.setopt(pycurl.INFILESIZE, len(request.body))

    if request.auth_username and request.auth_password:
        userpwd = "%s:%s" % (request.auth_username, request.auth_password)
        curl.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_BASIC)
        curl.setopt(pycurl.USERPWD, userpwd)
        _log.info("%s %s (username: %r)", request.method, request.url,
                     request.auth_username)
    else:
        curl.unsetopt(pycurl.USERPWD)
        _log.info("%s %s", request.method, request.url)
    if request.prepare_curl_callback is not None:
        request.prepare_curl_callback(curl)


def _curl_header_callback(headers, header_line):
    if header_line.startswith("HTTP/"):
        headers.clear()
        return
    if header_line == "\r\n":
        return
    parts = header_line.split(":", 1)
    if len(parts) != 2:
        _log.warning("Invalid HTTP response header line %r", header_line)
        return
    name = parts[0].strip()
    value = parts[1].strip()
    if name in headers:
        headers[name] = headers[name] + ',' + value
    else:
        headers[name] = value


def _curl_debug(debug_type, debug_msg):
    debug_types = ('I', '<', '>', '<', '>')
    if debug_type == 0:
        _log.debug('%s', debug_msg.strip())
    elif debug_type in (1, 2):
        for line in debug_msg.splitlines():
            _log.debug('%s %s', debug_types[debug_type], line)
    elif debug_type == 4:
        _log.debug('%s %r', debug_types[debug_type], debug_msg)


def _utf8(value):
    if value is None:
        return value
    if isinstance(value, unicode):
        return value.encode("utf-8")
    assert isinstance(value, str)
    return value
