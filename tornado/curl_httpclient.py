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

"""Non-blocking HTTP client implementation using pycurl."""

import collections
import functools
import inspect
import logging
import re
import threading
import time
from collections.abc import Callable
from io import BytesIO
from typing import Any

import pycurl

from tornado import gen, httputil, ioloop
from tornado.escape import native_str, utf8
from tornado.httpclient import (
    AsyncHTTPClient,
    HTTPError,
    HTTPRequest,
    HTTPResponse,
    main,
)
from tornado.log import app_log

curl_log = logging.getLogger("tornado.curl_httpclient")

CR_OR_LF_RE = re.compile(b"\r|\n")


class CurlAsyncHTTPClient(AsyncHTTPClient):
    def initialize(  # type: ignore
        self, max_clients: int = 10, defaults: dict[str, Any] | None = None
    ) -> None:
        super().initialize(defaults=defaults)
        # Typeshed is incomplete for CurlMulti, so just use Any for now.
        self._multi: Any = pycurl.CurlMulti()
        self._multi.setopt(pycurl.M_TIMERFUNCTION, self._set_timeout)
        self._multi.setopt(pycurl.M_SOCKETFUNCTION, self._handle_socket)
        self._curls = [self._curl_create() for i in range(max_clients)]
        self._free_list = self._curls[:]
        self._requests: collections.deque[
            tuple[HTTPRequest, Callable[[HTTPResponse], None], float]
        ] = collections.deque()
        self._fds: dict[int, int] = {}
        self._timeout: object | None = None

        # Work around a bug in libcurl 7.29.0: Some fields in the curl
        # multi object are initialized lazily, and its destructor will
        # segfault if it is destroyed without having been used.  Add
        # and remove a dummy handle to make sure everything is
        # initialized.
        dummy_curl_handle = pycurl.Curl()
        self._multi.add_handle(dummy_curl_handle)
        self._multi.remove_handle(dummy_curl_handle)

    def close(self) -> None:
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
        for curl in self._curls:
            curl.close()
        self._multi.close()
        super().close()

        # Set below properties to None to reduce the reference count of current
        # instance, because those properties hold some methods of current
        # instance that will case circular reference.
        self._multi = None

    def fetch_impl(
        self, request: HTTPRequest, callback: Callable[[HTTPResponse], None]
    ) -> None:
        self._requests.append((request, callback, self.io_loop.time()))
        self._process_queue()
        self._set_timeout(0)

    def _handle_socket(self, event: int, fd: int, multi: Any, data: bytes) -> None:
        """Called by libcurl when it wants to change the file descriptors
        it cares about.
        """
        event_map = {
            pycurl.POLL_NONE: ioloop.IOLoop.NONE,
            pycurl.POLL_IN: ioloop.IOLoop.READ,
            pycurl.POLL_OUT: ioloop.IOLoop.WRITE,
            pycurl.POLL_INOUT: ioloop.IOLoop.READ | ioloop.IOLoop.WRITE,
        }
        if event == pycurl.POLL_REMOVE:
            if fd in self._fds:
                self.io_loop.remove_handler(fd)
                del self._fds[fd]
        else:
            ioloop_event = event_map[event]
            # libcurl sometimes closes a socket and then opens a new
            # one using the same FD without giving us a POLL_NONE in
            # between.  This is a problem with the epoll IOLoop,
            # because the kernel can tell when a socket is closed and
            # removes it from the epoll automatically, causing future
            # update_handler calls to fail.  Since we can't tell when
            # this has happened, always use remove and re-add
            # instead of update.
            if fd in self._fds:
                self.io_loop.remove_handler(fd)
            self.io_loop.add_handler(fd, self._handle_events, ioloop_event)
            self._fds[fd] = ioloop_event

    def _set_timeout(self, msecs: int) -> None:
        """Called by libcurl to schedule a timeout."""
        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
        self._timeout = self.io_loop.add_timeout(
            self.io_loop.time() + msecs / 1000.0, self._handle_timeout
        )

    def _handle_events(self, fd: int, events: int) -> None:
        """Called by IOLoop when there is activity on one of our
        file descriptors.
        """
        action = 0
        if events & ioloop.IOLoop.READ:
            action |= pycurl.CSELECT_IN
        if events & ioloop.IOLoop.WRITE:
            action |= pycurl.CSELECT_OUT
        while True:
            try:
                ret, num_handles = self._multi.socket_action(fd, action)
            except pycurl.error as e:
                ret = e.args[0]
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
        self._finish_pending_requests()

    def _handle_timeout(self) -> None:
        """Called by IOLoop when the requested timeout has passed."""
        self._timeout = None
        while True:
            try:
                ret, num_handles = self._multi.socket_action(pycurl.SOCKET_TIMEOUT, 0)
            except pycurl.error as e:
                ret = e.args[0]
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
        if new_timeout >= 0:
            self._set_timeout(new_timeout)

    def _finish_pending_requests(self) -> None:
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

    def _process_queue(self) -> None:
        while True:
            started = 0
            while self._free_list and self._requests:
                started += 1
                curl = self._free_list.pop()
                request, callback, queue_start_time = self._requests.popleft()
                # TODO: Don't smuggle extra data on an attribute of the Curl object.
                curl.info = {  # type: ignore
                    "headers": httputil.HTTPHeaders(),
                    "buffer": BytesIO(),
                    "request": request,
                    "callback": callback,
                    "queue_start_time": queue_start_time,
                    "curl_start_time": time.time(),
                    "curl_start_ioloop_time": self.io_loop.current().time(),  # type: ignore
                }
                try:
                    self._curl_setup_request(
                        curl,
                        request,
                        curl.info["buffer"],  # type: ignore
                        curl.info["headers"],  # type: ignore
                    )
                except Exception as e:
                    # If there was an error in setup, pass it on
                    # to the callback. Note that allowing the
                    # error to escape here will appear to work
                    # most of the time since we are still in the
                    # caller's original stack frame, but when
                    # _process_queue() is called from
                    # _finish_pending_requests the exceptions have
                    # nowhere to go.
                    curl.reset()
                    self._free_list.append(curl)
                    callback(HTTPResponse(request=request, code=599, error=e))
                else:
                    self._multi.add_handle(curl)

            if not started:
                break

    def _finish(
        self,
        curl: pycurl.Curl,
        curl_error: int | None = None,
        curl_message: str | None = None,
    ) -> None:
        info = curl.info  # type: ignore
        curl.info = None  # type: ignore
        self._multi.remove_handle(curl)
        buffer = info["buffer"]
        if curl_error:
            assert curl_message is not None
            error: CurlError | None = CurlError(curl_error, curl_message)
            assert error is not None
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
            queue=info["curl_start_ioloop_time"] - info["queue_start_time"],
            namelookup=curl.getinfo(pycurl.NAMELOOKUP_TIME),
            connect=curl.getinfo(pycurl.CONNECT_TIME),
            appconnect=curl.getinfo(pycurl.APPCONNECT_TIME),
            pretransfer=curl.getinfo(pycurl.PRETRANSFER_TIME),
            starttransfer=curl.getinfo(pycurl.STARTTRANSFER_TIME),
            total=curl.getinfo(pycurl.TOTAL_TIME),
            redirect=curl.getinfo(pycurl.REDIRECT_TIME),
        )
        try:
            info["callback"](
                HTTPResponse(
                    request=info["request"],
                    code=code,
                    headers=info["headers"],
                    buffer=buffer,
                    effective_url=effective_url,
                    error=error,
                    reason=info["headers"].get("X-Http-Reason", None),
                    request_time=self.io_loop.time() - info["curl_start_ioloop_time"],
                    start_time=info["curl_start_time"],
                    time_info=time_info,
                )
            )
        except Exception:
            self.handle_callback_exception(info["callback"])
        curl.reset()
        self._free_list.append(curl)

    def handle_callback_exception(self, callback: Any) -> None:
        app_log.error("Exception in callback %r", callback, exc_info=True)

    def _curl_create(self) -> pycurl.Curl:
        return pycurl.Curl()

    def _setup_curl_logging(self, curl: pycurl.Curl) -> None:
        """Configure curl logging and debug options."""
        if curl_log.isEnabledFor(logging.DEBUG):
            curl.setopt(pycurl.VERBOSE, 1)
            curl.setopt(pycurl.DEBUGFUNCTION, self._curl_debug)
        if hasattr(
            pycurl, "PROTOCOLS"
        ):  # PROTOCOLS first appeared in pycurl 7.19.5 (2014-07-12)
            curl.setopt(pycurl.PROTOCOLS, pycurl.PROTO_HTTP | pycurl.PROTO_HTTPS)
            curl.setopt(pycurl.REDIR_PROTOCOLS, pycurl.PROTO_HTTP | pycurl.PROTO_HTTPS)

    def _setup_curl_url_and_headers(
        self,
        curl: pycurl.Curl,
        request: HTTPRequest,
        headers: httputil.HTTPHeaders,
    ) -> None:
        """Configure curl URL and HTTP headers."""
        curl.setopt(pycurl.URL, native_str(request.url))

        # libcurl's magic "Expect: 100-continue" behavior causes delays
        # with servers that don't support it (which include, among others,
        # Google's OpenID endpoint).  Additionally, this behavior has
        # a bug in conjunction with the curl_multi_socket_action API
        # (https://sourceforge.net/tracker/?func=detail&atid=100976&aid=3039744&group_id=976),
        # which increases the delays.  It's more trouble than it's worth,
        # so just turn off the feature (yes, setting Expect: to an empty
        # value is the official way to disable this)
        if "Expect" not in request.headers:
            request.headers["Expect"] = ""

        # libcurl adds Pragma: no-cache by default; disable that too
        if "Pragma" not in request.headers:
            request.headers["Pragma"] = ""

        encoded_headers = [
            b"%s: %s"
            % (native_str(k).encode("ASCII"), native_str(v).encode("ISO8859-1"))
            for k, v in request.headers.get_all()
        ]
        for line in encoded_headers:
            if CR_OR_LF_RE.search(line):
                raise ValueError("Illegal characters in header (CR or LF): %r" % line)
        curl.setopt(pycurl.HTTPHEADER, encoded_headers)

        curl.setopt(
            pycurl.HEADERFUNCTION,
            functools.partial(
                self._curl_header_callback, headers, request.header_callback
            ),
        )

    def _setup_curl_write_function(
        self,
        curl: pycurl.Curl,
        request: HTTPRequest,
        buffer: BytesIO,
    ) -> None:
        """Configure curl write callback function."""
        if request.streaming_callback:
            if gen.is_coroutine_function(
                request.streaming_callback
            ) or inspect.iscoroutinefunction(request.streaming_callback):
                raise TypeError(
                    "'CurlAsyncHTTPClient' does not support async streaming_callbacks."
                )

            def write_function(b: bytes | bytearray) -> int:
                assert request.streaming_callback is not None
                self.io_loop.add_callback(request.streaming_callback, b)
                return len(b)

        else:
            write_function = buffer.write  # type: ignore
        curl.setopt(pycurl.WRITEFUNCTION, write_function)

    def _setup_curl_redirect_and_timeout(
        self, curl: pycurl.Curl, request: HTTPRequest
    ) -> None:
        """Configure curl redirection and timeout settings."""
        curl.setopt(pycurl.FOLLOWLOCATION, request.follow_redirects)
        curl.setopt(pycurl.MAXREDIRS, request.max_redirects)
        assert request.connect_timeout is not None
        curl.setopt(pycurl.CONNECTTIMEOUT_MS, int(1000 * request.connect_timeout))
        assert request.request_timeout is not None
        curl.setopt(pycurl.TIMEOUT_MS, int(1000 * request.request_timeout))

    def _setup_curl_user_agent_and_interface(
        self, curl: pycurl.Curl, request: HTTPRequest
    ) -> None:
        """Configure curl user agent and network interface."""
        if request.user_agent:
            curl.setopt(pycurl.USERAGENT, native_str(request.user_agent))
        else:
            curl.setopt(pycurl.USERAGENT, "Mozilla/5.0 (compatible; pycurl)")
        if request.network_interface:
            curl.setopt(pycurl.INTERFACE, request.network_interface)

    def _setup_curl_encoding(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl response compression encoding."""
        if request.decompress_response:
            curl.setopt(pycurl.ENCODING, "gzip,deflate")
        else:
            curl.setopt(pycurl.ENCODING, None)

    def _setup_curl_proxy(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl proxy settings."""
        if request.proxy_host and request.proxy_port:
            curl.setopt(pycurl.PROXY, request.proxy_host)
            curl.setopt(pycurl.PROXYPORT, request.proxy_port)
            if request.proxy_username:
                assert request.proxy_password is not None
                credentials = httputil.encode_username_password(
                    request.proxy_username, request.proxy_password
                )
                curl.setopt(pycurl.PROXYUSERPWD, credentials)

            if request.proxy_auth_mode is None or request.proxy_auth_mode == "basic":
                curl.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_BASIC)
            elif request.proxy_auth_mode == "digest":
                curl.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_DIGEST)
            else:
                raise ValueError(
                    "Unsupported proxy_auth_mode %s" % request.proxy_auth_mode
                )
        else:
            try:
                curl.unsetopt(pycurl.PROXY)
            except TypeError:  # not supported, disable proxy
                curl.setopt(pycurl.PROXY, "")
            curl.unsetopt(pycurl.PROXYUSERPWD)

    def _setup_curl_ssl_verification(
        self, curl: pycurl.Curl, request: HTTPRequest
    ) -> None:
        """Configure curl SSL/TLS certificate verification."""
        if request.validate_cert:
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
        else:
            curl.setopt(pycurl.SSL_VERIFYPEER, 0)
            curl.setopt(pycurl.SSL_VERIFYHOST, 0)
        if request.ca_certs is not None:
            curl.setopt(pycurl.CAINFO, request.ca_certs)

    def _setup_curl_ipv6(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl IPv6 resolution settings."""
        if request.allow_ipv6 is False:
            # Curl behaves reasonably when DNS resolution gives an ipv6 address
            # that we can't reach, so allow ipv6 unless the user asks to disable.
            curl.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V4)
        else:
            curl.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_WHATEVER)

    def _setup_curl_http_method(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl HTTP request method."""
        # Set the request method through curl's irritating interface which makes
        # up names for almost every single method
        curl_options = {
            "GET": pycurl.HTTPGET,
            "POST": pycurl.POST,
            "PUT": pycurl.UPLOAD,
            "HEAD": pycurl.NOBODY,
        }
        custom_methods = {"DELETE", "OPTIONS", "PATCH"}
        for o in curl_options.values():
            curl.setopt(o, False)
        if request.method in curl_options:
            curl.unsetopt(pycurl.CUSTOMREQUEST)
            curl.setopt(curl_options[request.method], True)
        elif request.allow_nonstandard_methods or request.method in custom_methods:
            curl.setopt(pycurl.CUSTOMREQUEST, request.method)
        else:
            raise KeyError("unknown method " + request.method)

    def _validate_request_body(self, request: HTTPRequest) -> None:
        """Validate request body for the HTTP method."""
        body_expected = request.method in ("POST", "PATCH", "PUT")
        body_present = request.body is not None
        if not request.allow_nonstandard_methods:
            # Some HTTP methods nearly always have bodies while others
            # almost never do. Fail in this case unless the user has
            # opted out of sanity checks with allow_nonstandard_methods.
            if (body_expected and not body_present) or (
                body_present and not body_expected
            ):
                raise ValueError(
                    "Body must %sbe None for method %s (unless "
                    "allow_nonstandard_methods is true)"
                    % ("not " if body_expected else "", request.method)
                )

    def _setup_curl_request_body(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl request body and related settings."""
        body_expected = request.method in ("POST", "PATCH", "PUT")
        body_present = request.body is not None

        if body_expected or body_present:
            if request.method == "GET":
                # Even with `allow_nonstandard_methods` we disallow
                # GET with a body (because libcurl doesn't allow it
                # unless we use CUSTOMREQUEST). While the spec doesn't
                # forbid clients from sending a body, it arguably
                # disallows the server from doing anything with them.
                raise ValueError("Body must be None for GET request")
            request_buffer = BytesIO(utf8(request.body or ""))

            def seek(offset: int, origin: int) -> int:
                request_buffer.seek(offset, origin)
                return pycurl.SEEKFUNC_OK

            curl.setopt(pycurl.READFUNCTION, request_buffer.read)
            curl.setopt(pycurl.SEEKFUNCTION, seek)
            if request.method == "POST":
                curl.setopt(pycurl.POSTFIELDSIZE, len(request.body or ""))
            else:
                curl.setopt(pycurl.UPLOAD, True)
                curl.setopt(pycurl.INFILESIZE, len(request.body or ""))

    def _setup_curl_auth(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl HTTP basic/digest authentication."""
        if request.auth_username is not None:
            assert request.auth_password is not None
            if request.auth_mode is None or request.auth_mode == "basic":
                curl.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_BASIC)
            elif request.auth_mode == "digest":
                curl.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
            else:
                raise ValueError("Unsupported auth_mode %s" % request.auth_mode)

            userpwd = httputil.encode_username_password(
                request.auth_username, request.auth_password
            )
            curl.setopt(pycurl.USERPWD, userpwd)
            curl_log.debug(
                "%s %s (username: %r)",
                request.method,
                request.url,
                request.auth_username,
            )
        else:
            curl.unsetopt(pycurl.USERPWD)
            curl_log.debug("%s %s", request.method, request.url)

    def _setup_curl_client_cert(self, curl: pycurl.Curl, request: HTTPRequest) -> None:
        """Configure curl client certificate settings."""
        if request.client_cert is not None:
            curl.setopt(pycurl.SSLCERT, request.client_cert)

        if request.client_key is not None:
            curl.setopt(pycurl.SSLKEY, request.client_key)

        if request.ssl_options is not None:
            raise ValueError("ssl_options not supported in curl_httpclient")

    def _setup_curl_threading_and_callback(
        self, curl: pycurl.Curl, request: HTTPRequest
    ) -> None:
        """Configure curl threading safety and prepare callback."""
        if threading.active_count() > 1:
            # libcurl/pycurl is not thread-safe by default.  When multiple threads
            # are used, signals should be disabled.  This has the side effect
            # of disabling DNS timeouts in some environments (when libcurl is
            # not linked against ares), so we don't do it when there is only one
            # thread.  Applications that use many short-lived threads may need
            # to set NOSIGNAL manually in a prepare_curl_callback since
            # there may not be any other threads running at the time we call
            # threading.activeCount.
            curl.setopt(pycurl.NOSIGNAL, 1)
        if request.prepare_curl_callback is not None:
            request.prepare_curl_callback(curl)

    def _curl_setup_request(
        self,
        curl: pycurl.Curl,
        request: HTTPRequest,
        buffer: BytesIO,
        headers: httputil.HTTPHeaders,
    ) -> None:
        """Setup a curl handle for the given request.
        
        This method orchestrates the configuration of all curl settings
        by delegating to specialized setup methods.
        """
        self._setup_curl_logging(curl)
        self._setup_curl_url_and_headers(curl, request, headers)
        self._setup_curl_write_function(curl, request, buffer)
        self._setup_curl_redirect_and_timeout(curl, request)
        self._setup_curl_user_agent_and_interface(curl, request)
        self._setup_curl_encoding(curl, request)
        self._setup_curl_proxy(curl, request)
        self._setup_curl_ssl_verification(curl, request)
        self._setup_curl_ipv6(curl, request)
        self._setup_curl_http_method(curl, request)
        self._validate_request_body(request)
        self._setup_curl_request_body(curl, request)
        self._setup_curl_auth(curl, request)
        self._setup_curl_client_cert(curl, request)
        self._setup_curl_threading_and_callback(curl, request)

    def _curl_header_callback(
        self,
        headers: httputil.HTTPHeaders,
        header_callback: Callable[[str], None] | None,
        header_line_bytes: bytes,
    ) -> None:
        header_line = native_str(header_line_bytes.decode("latin1"))
        if header_callback is not None:
            self.io_loop.add_callback(header_callback, header_line)
        # header_line as returned by curl includes the end-of-line characters.
        # whitespace at the start should be preserved to allow multi-line headers
        header_line = header_line.rstrip()
        if header_line.startswith("HTTP/"):
            headers.clear()
            try:
                _version, _code, reason = httputil.parse_response_start_line(
                    header_line
                )
                header_line = "X-Http-Reason: %s" % reason
            except httputil.HTTPInputError:
                return
        if not header_line:
            return
        headers.parse_line(header_line)

    def _curl_debug(self, debug_type: int, debug_msg: str) -> None:
        debug_types = ("I", "<", ">", "<", ">")
        if debug_type == 0:
            debug_msg = native_str(debug_msg)
            curl_log.debug("%s", debug_msg.strip())
        elif debug_type in (1, 2):
            debug_msg = native_str(debug_msg)
            for line in debug_msg.splitlines():
                curl_log.debug("%s %s", debug_types[debug_type], line)
        elif debug_type == 4:
            curl_log.debug("%s %r", debug_types[debug_type], debug_msg)


class CurlError(HTTPError):
    def __init__(self, errno: int, message: str) -> None:
        HTTPError.__init__(self, 599, message)
        self.errno = errno


if __name__ == "__main__":
    AsyncHTTPClient.configure(CurlAsyncHTTPClient)
    main()
