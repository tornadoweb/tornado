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
import escape
import httplib
import httputil
import ioloop
import logging
import pycurl
import sys
import time
import weakref

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

            # Update the set of active file descriptors.  It is important
            # that this happen immediately after perform() because
            # fds that have been removed from fdset are free to be reused
            # in user callbacks.
            fds = {}
            (readable, writable, exceptable) = self._multi.fdset()
            for fd in readable:
                fds[fd] = fds.get(fd, 0) | 0x1 | 0x2
            for fd in writable:
                fds[fd] = fds.get(fd, 0) | 0x4
            for fd in exceptable:
                fds[fd] = fds.get(fd, 0) | 0x8 | 0x10

            if fds and max(fds.iterkeys()) > 900:
                # Libcurl has a bug in which it behaves unpredictably with
                # file descriptors greater than 1024.  (This is because
                # even though it uses poll() instead of select(), it still
                # uses FD_SET internally) Since curl opens its own file
                # descriptors we can't catch this problem when it happens,
                # and the best we can do is detect that it's about to
                # happen.  Exiting is a lousy way to handle this error,
                # but there's not much we can do at this point.  Exiting
                # (and getting restarted by whatever monitoring process
                # is handling crashed tornado processes) will at least
                # get things working again and hopefully bring the issue
                # to someone's attention.
                # If you run into this issue, you either have a file descriptor
                # leak or need to run more tornado processes (so that none
                # of them are handling more than 1000 simultaneous connections)
                print >> sys.stderr, "ERROR: File descriptor too high for libcurl. Exiting."
                logging.error("File descriptor too high for libcurl. Exiting.")
                sys.exit(1)

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
                    "headers": httputil.HTTPHeaders(),
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


    def _finish(self, curl, curl_error=None, curl_message=None):
        info = curl.info
        curl.info = None
        self._multi.remove_handle(curl)
        self._free_list.append(curl)
        buffer = info["buffer"]
        if curl_error:
            error = CurlError(curl_error, curl_message)
            code = error.code
            body = None
            effective_url = None
            buffer.close()
            buffer = None
        else:
            error = None
            code = curl.getinfo(pycurl.HTTP_CODE)
            effective_url = curl.getinfo(pycurl.EFFECTIVE_URL)
            buffer.seek(0)
        try:
            info["callback"](HTTPResponse(
                request=info["request"], code=code, headers=info["headers"],
                buffer=buffer, effective_url=effective_url, error=error,
                request_time=time.time() - info["start_time"]))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            logging.error("Exception in callback %r", info["callback"],
                          exc_info=True)


class AsyncHTTPClient2(object):
    """Alternate implementation of AsyncHTTPClient.

    This class has the same interface as AsyncHTTPClient (so see that class
    for usage documentation) but is implemented with a different set of
    libcurl APIs (curl_multi_socket_action instead of fdset/perform).
    This implementation will likely become the default in the future, but
    for now should be considered somewhat experimental.

    The main advantage of this class over the original implementation is
    that it is immune to the fd > 1024 bug, so applications with a large
    number of simultaneous requests (e.g. long-polling) may prefer this
    version.

    Known bugs:
    * Timeouts connecting to localhost
    In some situations, this implementation will return a connection
    timeout when the old implementation would be able to connect.  This
    has only been observed when connecting to localhost when using
    the kqueue-based IOLoop (mac/bsd), but it may also occur on epoll (linux)
    and, in principle, for non-localhost sites.
    While the bug is unrelated to IPv6, disabling IPv6 will avoid the
    most common manifestations of the bug, so this class disables IPv6 when
    it detects an affected version of libcurl.
    The underlying cause is a libcurl bug in versions up to and including
    7.21.0 (it will be fixed in the not-yet-released 7.21.1)
    http://sourceforge.net/tracker/?func=detail&aid=3017819&group_id=976&atid=100976
    """
    _ASYNC_CLIENTS = weakref.WeakKeyDictionary()

    def __new__(cls, io_loop=None, max_clients=10,
                max_simultaneous_connections=None):
        # There is one client per IOLoop since they share curl instances
        io_loop = io_loop or ioloop.IOLoop.instance()
        if io_loop in cls._ASYNC_CLIENTS:
            return cls._ASYNC_CLIENTS[io_loop]
        else:
            instance = super(AsyncHTTPClient2, cls).__new__(cls)
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
            return instance

    def close(self):
        """Destroys this http client, freeing any file descriptors used.
        Not needed in normal use, but may be helpful in unittests that
        create and destroy http clients.  No other methods may be called
        on the AsyncHTTPClient after close().
        """
        del AsyncHTTPClient2._ASYNC_CLIENTS[self.io_loop]
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
                ret, num_handles = self._multi.socket_action(fd, action)
            except Exception, e:
                ret = e[0]
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
        self._finish_pending_requests()

    def _handle_timeout(self):
        """Called by IOLoop when the requested timeout has passed."""
        self._timeout = None
        while True:
            try:
                ret, num_handles = self._multi.socket_action(
                                        pycurl.SOCKET_TIMEOUT, 0)
            except Exception, e:
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
                    "start_time": time.time(),
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
        try:
            info["callback"](HTTPResponse(
                request=info["request"], code=code, headers=info["headers"],
                buffer=buffer, effective_url=effective_url, error=error,
                request_time=time.time() - info["start_time"]))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            logging.error("Exception in callback %r", info["callback"],
                          exc_info=True)


class HTTPRequest(object):
    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None,
                 connect_timeout=20.0, request_timeout=20.0,
                 if_modified_since=None, follow_redirects=True,
                 max_redirects=5, user_agent=None, use_gzip=True,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 allow_nonstandard_methods=False):
        if headers is None:
            headers = httputil.HTTPHeaders()
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
        self.allow_nonstandard_methods = allow_nonstandard_methods


class HTTPResponse(object):
    def __init__(self, request, code, headers={}, buffer=None, effective_url=None,
                 error=None, request_time=None):
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
    if header_line.startswith("HTTP/"):
        headers.clear()
        return
    if header_line == "\r\n":
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
