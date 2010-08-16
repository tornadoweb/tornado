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

from __future__ import with_statement

import cStringIO
import calendar
import collections
import email.utils
import errno
import httplib
import logging
import pycurl
import sys
import time
import weakref

from tornado import escape
from tornado import httputil
from tornado import ioloop
from tornado import stack_context

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
        headers = httputil.HTTPHeaders()
        try:
            _curl_setup_request(self._curl, request, buffer, headers)
            self._curl.perform()
            code = self._curl.getinfo(pycurl.HTTP_CODE)
            effective_url = self._curl.getinfo(pycurl.EFFECTIVE_URL)
            buffer.seek(0)
            response = HTTPResponse(
                request=request, code=code, headers=headers,
                buffer=buffer, effective_url=effective_url)
            if code < 200 or code >= 300:
                raise HTTPError(code, response=response)
            return response
        except pycurl.error, e:
            buffer.close()
            raise CurlError(*e)


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
            instance._multi.setopt(pycurl.M_TIMERFUNCTION,
                                   instance._set_timeout)
            instance._multi.setopt(pycurl.M_SOCKETFUNCTION,
                                   instance._handle_socket)
            instance._curls = [_curl_create(max_simultaneous_connections)
                               for i in xrange(max_clients)]
            instance._free_list = instance._curls[:]
            instance._requests = collections.deque()
            instance._fds = {}
            instance._timeout = None
            cls._ASYNC_CLIENTS[io_loop] = instance

            try:
                instance._socket_action = instance._multi.socket_action
            except AttributeError:
                # socket_action is found in pycurl since 7.18.2 (it's been
                # in libcurl longer than that but wasn't accessible to
                # python).
                logging.warning("socket_action method missing from pycurl; "
                                "falling back to socket_all. Upgrading "
                                "libcurl and pycurl will improve performance")
                instance._socket_action = \
                    lambda fd, action: instance._multi.socket_all()

            # libcurl has bugs that sometimes cause it to not report all
            # relevant file descriptors and timeouts to TIMERFUNCTION/
            # SOCKETFUNCTION.  Mitigate the effects of such bugs by
            # forcing a periodic scan of all active requests.
            instance._force_timeout_callback = ioloop.PeriodicCallback(
                instance._handle_force_timeout, 1000, io_loop=io_loop)
            instance._force_timeout_callback.start()

            return instance

    def close(self):
        """Destroys this http client, freeing any file descriptors used.
        Not needed in normal use, but may be helpful in unittests that
        create and destroy http clients.  No other methods may be called
        on the AsyncHTTPClient after close().
        """
        del AsyncHTTPClient._ASYNC_CLIENTS[self.io_loop]
        self._force_timeout_callback.stop()
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
        self._requests.append((request, stack_context.wrap(callback)))
        self._process_queue()
        self._set_timeout(0)

    def _handle_socket(self, event, fd, multi, data):
        """Called by libcurl when it wants to change the file descriptors
        it cares about.
        """
        event_map = {
            pycurl.POLL_NONE: ioloop.IOLoop.NONE,
            pycurl.POLL_IN: ioloop.IOLoop.READ,
            pycurl.POLL_OUT: ioloop.IOLoop.WRITE,
            pycurl.POLL_INOUT: ioloop.IOLoop.READ | ioloop.IOLoop.WRITE
        }
        if event == pycurl.POLL_REMOVE:
            self.io_loop.remove_handler(fd)
            del self._fds[fd]
        else:
            ioloop_event = event_map[event]
            if fd not in self._fds:
                self._fds[fd] = ioloop_event
                self.io_loop.add_handler(fd, self._handle_events,
                                         ioloop_event)
            else:
                self._fds[fd] = ioloop_event
                self.io_loop.update_handler(fd, ioloop_event)

    def _set_timeout(self, msecs):
        """Called by libcurl to schedule a timeout."""
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
        self._timeout = self.io_loop.add_timeout(
            time.time() + msecs/1000.0, self._handle_timeout)

    def _handle_events(self, fd, events):
        """Called by IOLoop when there is activity on one of our
        file descriptors.
        """
        action = 0
        if events & ioloop.IOLoop.READ: action |= pycurl.CSELECT_IN
        if events & ioloop.IOLoop.WRITE: action |= pycurl.CSELECT_OUT
        while True:
            try:
                ret, num_handles = self._socket_action(fd, action)
            except pycurl.error, e:
                ret = e[0]
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
        self._finish_pending_requests()

    def _handle_timeout(self):
        """Called by IOLoop when the requested timeout has passed."""
        with stack_context.NullContext():
            self._timeout = None
            while True:
                try:
                    ret, num_handles = self._socket_action(
                        pycurl.SOCKET_TIMEOUT, 0)
                except pycurl.error, e:
                    ret = e[0]
                if ret != pycurl.E_CALL_MULTI_PERFORM:
                    break
            self._finish_pending_requests()

        # In theory, we shouldn't have to do this because curl will
        # call _set_timeout whenever the timeout changes.  However,
        # sometimes after _handle_timeout we will need to reschedule
        # immediately even though nothing has changed from curl's
        # perspective.  This is because when socket_action is
        # called with SOCKET_TIMEOUT, libcurl decides internally which
        # timeouts need to be processed by using a monotonic clock
        # (where available) while tornado uses python's time.time()
        # to decide when timeouts have occurred.  When those clocks
        # disagree on elapsed time (as they will whenever there is an
        # NTP adjustment), tornado might call _handle_timeout before
        # libcurl is ready.  After each timeout, resync the scheduled
        # timeout with libcurl's current state.
        new_timeout = self._multi.timeout()
        if new_timeout != -1:
            self._set_timeout(new_timeout)

    def _handle_force_timeout(self):
        """Called by IOLoop periodically to ask libcurl to process any
        events it may have forgotten about.
        """
        with stack_context.NullContext():
            while True:
                try:
                    ret, num_handles = self._multi.socket_all()
                except pycurl.error, e:
                    ret = e[0]
                if ret != pycurl.E_CALL_MULTI_PERFORM:
                    break
            self._finish_pending_requests()

    def _finish_pending_requests(self):
        """Process any requests that were completed by the last
        call to multi.socket_action.
        """
        while True:
            num_q, ok_list, err_list = self._multi.info_read()
            for curl in ok_list:
                self._finish(curl)
            for curl, errnum, errmsg in err_list:
                self._finish(curl, errnum, errmsg)
            if num_q == 0:
                break
        self._process_queue()

    def _process_queue(self):
        with stack_context.NullContext():
            while True:
                started = 0
                while self._free_list and self._requests:
                    started += 1
                    curl = self._free_list.pop()
                    (request, callback) = self._requests.popleft()
                    curl.info = {
                        "headers": httputil.HTTPHeaders(),
                        "buffer": cStringIO.StringIO(),
                        "request": request,
                        "callback": callback,
                        "curl_start_time": time.time(),
                    }
                    # Disable IPv6 to mitigate the effects of this bug
                    # on curl versions <= 7.21.0
                    # http://sourceforge.net/tracker/?func=detail&aid=3017819&group_id=976&atid=100976
                    if pycurl.version_info()[2] <= 0x71500:  # 7.21.0
                        curl.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V4)
                    _curl_setup_request(curl, request, curl.info["buffer"],
                                        curl.info["headers"])
                    self._multi.add_handle(curl)

                if not started:
                    break

    def _finish(self, curl, curl_error=None, curl_message=None):
        info = curl.info
        curl.info = None
        self._multi.remove_handle(curl)
        self._free_list.append(curl)
        buffer = info["buffer"]
        if curl_error:
            error = CurlError(curl_error, curl_message)
            code = error.code
            effective_url = None
            buffer.close()
            buffer = None
        else:
            error = None
            code = curl.getinfo(pycurl.HTTP_CODE)
            effective_url = curl.getinfo(pycurl.EFFECTIVE_URL)
            buffer.seek(0)
        # the various curl timings are documented at
        # http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html
        time_info = dict(
            queue=info["curl_start_time"] - info["request"].start_time,
            namelookup=curl.getinfo(pycurl.NAMELOOKUP_TIME),
            connect=curl.getinfo(pycurl.CONNECT_TIME),
            pretransfer=curl.getinfo(pycurl.PRETRANSFER_TIME),
            starttransfer=curl.getinfo(pycurl.STARTTRANSFER_TIME),
            total=curl.getinfo(pycurl.TOTAL_TIME),
            redirect=curl.getinfo(pycurl.REDIRECT_TIME),
            )
        try:
            info["callback"](HTTPResponse(
                request=info["request"], code=code, headers=info["headers"],
                buffer=buffer, effective_url=effective_url, error=error,
                request_time=time.time() - info["curl_start_time"],
                time_info=time_info))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            logging.error("Exception in callback %r", info["callback"],
                          exc_info=True)

# For backwards compatibility: Tornado 1.0 included a new implementation of
# AsyncHTTPClient that has since replaced the original.  Define an alias
# so anything that used AsyncHTTPClient2 still works
AsyncHTTPClient2 = AsyncHTTPClient

class HTTPRequest(object):
    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None,
                 connect_timeout=20.0, request_timeout=20.0,
                 if_modified_since=None, follow_redirects=True,
                 max_redirects=5, user_agent=None, use_gzip=True,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 proxy_host=None, proxy_port=None, proxy_username=None,
                 proxy_password='', allow_nonstandard_methods=False):
        if headers is None:
            headers = httputil.HTTPHeaders()
        if if_modified_since:
            timestamp = calendar.timegm(if_modified_since.utctimetuple())
            headers["If-Modified-Since"] = email.utils.formatdate(
                timestamp, localtime=False, usegmt=True)
        if "Pragma" not in headers:
            headers["Pragma"] = ""
        # Proxy support: proxy_host and proxy_port must be set to connect via
        # proxy.  The username and password credentials are optional.
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        # libcurl's magic "Expect: 100-continue" behavior causes delays
        # with servers that don't support it (which include, among others,
        # Google's OpenID endpoint).  Additionally, this behavior has
        # a bug in conjunction with the curl_multi_socket_action API
        # (https://sourceforge.net/tracker/?func=detail&atid=100976&aid=3039744&group_id=976),
        # which increases the delays.  It's more trouble than it's worth,
        # so just turn off the feature (yes, setting Expect: to an empty
        # value is the official way to disable this)
        if "Expect" not in headers:
            headers["Expect"] = ""
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
        self.allow_nonstandard_methods = allow_nonstandard_methods
        self.start_time = time.time()


class HTTPResponse(object):
    """HTTP Response object.

    Attributes:
    * request: HTTPRequest object
    * code: numeric HTTP status code, e.g. 200 or 404
    * headers: httputil.HTTPHeaders object
    * buffer: cStringIO object for response body
    * body: respose body as string (created on demand from self.buffer)
    * error: Exception object, if any
    * request_time: seconds from request start to finish
    * time_info: dictionary of diagnostic timing information from the request.
        Available data are subject to change, but currently uses timings
        available from http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html,
        plus 'queue', which is the delay (if any) introduced by waiting for
        a slot under AsyncHTTPClient's max_clients setting.
    """
    def __init__(self, request, code, headers={}, buffer=None,
                 effective_url=None, error=None, request_time=None,
                 time_info={}):
        self.request = request
        self.code = code
        self.headers = headers
        self.buffer = buffer
        self._body = None
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        if error is None:
            if self.code < 200 or self.code >= 300:
                self.error = HTTPError(self.code, response=self)
            else:
                self.error = None
        else:
            self.error = error
        self.request_time = request_time
        self.time_info = time_info

    def _get_body(self):
        if self.buffer is None:
            return None
        elif self._body is None:
            self._body = self.buffer.getvalue()

        return self._body

    body = property(_get_body)

    def rethrow(self):
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in self.__dict__.iteritems())
        return "%s(%s)" % (self.__class__.__name__, args)

    def __del__(self):
        if self.buffer is not None:
            self.buffer.close()


class HTTPError(Exception):
    """Exception thrown for an unsuccessful HTTP request.

    Attributes:
    code - HTTP error integer error code, e.g. 404.  Error code 599 is
           used when no HTTP response was received, e.g. for a timeout.
    response - HTTPResponse object, if any.

    Note that if follow_redirects is False, redirects become HTTPErrors,
    and you can look at error.response.headers['Location'] to see the
    destination of the redirect.
    """
    def __init__(self, code, message=None, response=None):
        self.code = code
        message = message or httplib.responses.get(code, "Unknown")
        self.response = response
        Exception.__init__(self, "HTTP %d: %s" % (self.code, message))


class CurlError(HTTPError):
    def __init__(self, errno, message):
        HTTPError.__init__(self, 599, message)
        self.errno = errno


def _curl_create(max_simultaneous_connections=None):
    curl = pycurl.Curl()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        curl.setopt(pycurl.VERBOSE, 1)
        curl.setopt(pycurl.DEBUGFUNCTION, _curl_debug)
    curl.setopt(pycurl.MAXCONNECTS, max_simultaneous_connections or 5)
    return curl


def _curl_setup_request(curl, request, buffer, headers):
    curl.setopt(pycurl.URL, request.url)
    # Request headers may be either a regular dict or HTTPHeaders object
    if isinstance(request.headers, httputil.HTTPHeaders):
        curl.setopt(pycurl.HTTPHEADER,
                    [_utf8("%s: %s" % i) for i in request.headers.get_all()])
    else:
        curl.setopt(pycurl.HTTPHEADER,
                    [_utf8("%s: %s" % i) for i in request.headers.iteritems()])
    if request.header_callback:
        curl.setopt(pycurl.HEADERFUNCTION, request.header_callback)
    else:
        curl.setopt(pycurl.HEADERFUNCTION,
                    lambda line: _curl_header_callback(headers, line))
    if request.streaming_callback:
        curl.setopt(pycurl.WRITEFUNCTION, request.streaming_callback)
    else:
        curl.setopt(pycurl.WRITEFUNCTION, buffer.write)
    curl.setopt(pycurl.FOLLOWLOCATION, request.follow_redirects)
    curl.setopt(pycurl.MAXREDIRS, request.max_redirects)
    curl.setopt(pycurl.CONNECTTIMEOUT, int(request.connect_timeout))
    curl.setopt(pycurl.TIMEOUT, int(request.request_timeout))
    if request.user_agent:
        curl.setopt(pycurl.USERAGENT, _utf8(request.user_agent))
    else:
        curl.setopt(pycurl.USERAGENT, "Mozilla/5.0 (compatible; pycurl)")
    if request.network_interface:
        curl.setopt(pycurl.INTERFACE, request.network_interface)
    if request.use_gzip:
        curl.setopt(pycurl.ENCODING, "gzip,deflate")
    else:
        curl.setopt(pycurl.ENCODING, "none")
    if request.proxy_host and request.proxy_port:
        curl.setopt(pycurl.PROXY, request.proxy_host)
        curl.setopt(pycurl.PROXYPORT, request.proxy_port)
        if request.proxy_username:
            credentials = '%s:%s' % (request.proxy_username, 
                    request.proxy_password)
            curl.setopt(pycurl.PROXYUSERPWD, credentials)

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
    elif request.allow_nonstandard_methods or request.method in custom_methods:
        curl.setopt(pycurl.CUSTOMREQUEST, request.method)
    else:
        raise KeyError('unknown method ' + request.method)

    # Handle curl's cryptic options for every individual HTTP method
    if request.method in ("POST", "PUT"):
        request_buffer =  cStringIO.StringIO(escape.utf8(request.body))
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
        logging.info("%s %s (username: %r)", request.method, request.url,
                     request.auth_username)
    else:
        curl.unsetopt(pycurl.USERPWD)
        logging.info("%s %s", request.method, request.url)
    if request.prepare_curl_callback is not None:
        request.prepare_curl_callback(curl)


def _curl_header_callback(headers, header_line):
    # header_line as returned by curl includes the end-of-line characters.
    header_line = header_line.strip()
    if header_line.startswith("HTTP/"):
        headers.clear()
        return
    if not header_line:
        return
    headers.parse_line(header_line)

def _curl_debug(debug_type, debug_msg):
    debug_types = ('I', '<', '>', '<', '>')
    if debug_type == 0:
        logging.debug('%s', debug_msg.strip())
    elif debug_type in (1, 2):
        for line in debug_msg.splitlines():
            logging.debug('%s %s', debug_types[debug_type], line)
    elif debug_type == 4:
        logging.debug('%s %r', debug_types[debug_type], debug_msg)


def _utf8(value):
    if value is None:
        return value
    if isinstance(value, unicode):
        return value.encode("utf-8")
    assert isinstance(value, str)
    return value

def main():
    from tornado.options import define, options, parse_command_line
    define("print_headers", type=bool, default=False)
    define("print_body", type=bool, default=True)
    define("follow_redirects", type=bool, default=True)
    args = parse_command_line()
    client = HTTPClient()
    for arg in args:
        try:
            response = client.fetch(arg,
                                    follow_redirects=options.follow_redirects)
        except HTTPError, e:
            if e.response is not None:
                response = e.response
            else:
                raise
        if options.print_headers:
            print response.headers
        if options.print_body:
            print response.body

if __name__ == "__main__":
    main()
