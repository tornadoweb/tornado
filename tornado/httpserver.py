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

"""A non-blocking, single-threaded HTTP server."""

import cgi
import errno
import logging
import os
import socket
import time
import urlparse

from tornado import httputil
from tornado import ioloop
from tornado import iostream

try:
    import fcntl
except ImportError:
    if os.name == 'nt':
        from tornado import win32_support as fcntl
    else:
        raise

try:
    import ssl # Python 2.6+
except ImportError:
    ssl = None

try:
    import multiprocessing # Python 2.6+
except ImportError:
    multiprocessing = None

def _cpu_count():
    if multiprocessing is not None:
        try:
            return multiprocessing.cpu_count()
        except NotImplementedError:
            pass
    try:
        return os.sysconf("SC_NPROCESSORS_CONF")
    except ValueError:
        pass
    logging.error("Could not detect number of processors; "
                  "running with one process")
    return 1


class HTTPServer(object):
    """A non-blocking, single-threaded HTTP server.

    A server is defined by a request callback that takes an HTTPRequest
    instance as an argument and writes a valid HTTP response with
    request.write(). request.finish() finishes the request (but does not
    necessarily close the connection in the case of HTTP/1.1 keep-alive
    requests). A simple example server that echoes back the URI you
    requested:

        import httpserver
        import ioloop

        def handle_request(request):
           message = "You requested %s\n" % request.uri
           request.write("HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (
                         len(message), message))
           request.finish()

        http_server = httpserver.HTTPServer(handle_request)
        http_server.listen(8888)
        ioloop.IOLoop.instance().start()

    HTTPServer is a very basic connection handler. Beyond parsing the
    HTTP request body and headers, the only HTTP semantics implemented
    in HTTPServer is HTTP/1.1 keep-alive connections. We do not, however,
    implement chunked encoding, so the request callback must provide a
    Content-Length header or implement chunked encoding for HTTP/1.1
    requests for the server to run correctly for HTTP/1.1 clients. If
    the request handler is unable to do this, you can provide the
    no_keep_alive argument to the HTTPServer constructor, which will
    ensure the connection is closed on every request no matter what HTTP
    version the client is using.

    If xheaders is True, we support the X-Real-Ip and X-Scheme headers,
    which override the remote IP and HTTP scheme for all requests. These
    headers are useful when running Tornado behind a reverse proxy or
    load balancer.

    HTTPServer can serve HTTPS (SSL) traffic with Python 2.6+ and OpenSSL.
    To make this server serve SSL traffic, send the ssl_options dictionary
    argument with the arguments required for the ssl.wrap_socket() method,
    including "certfile" and "keyfile":

       HTTPServer(applicaton, ssl_options={
           "certfile": os.path.join(data_dir, "mydomain.crt"),
           "keyfile": os.path.join(data_dir, "mydomain.key"),
       })

    By default, listen() runs in a single thread in a single process. You
    can utilize all available CPUs on this machine by calling bind() and
    start() instead of listen():

        http_server = httpserver.HTTPServer(handle_request)
        http_server.bind(8888)
        http_server.start(0) # Forks multiple sub-processes
        ioloop.IOLoop.instance().start()

    start(0) detects the number of CPUs on this machine and "pre-forks" that
    number of child processes so that we have one Tornado process per CPU,
    all with their own IOLoop. You can also pass in the specific number of
    child processes you want to run with if you want to override this
    auto-detection.
    """
    def __init__(self, request_callback, no_keep_alive=False, io_loop=None,
                 xheaders=False, ssl_options=None):
        """Initializes the server with the given request callback.

        If you use pre-forking/start() instead of the listen() method to
        start your server, you should not pass an IOLoop instance to this
        constructor. Each pre-forked child process will create its own
        IOLoop instance after the forking process.
        """
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.io_loop = io_loop
        self.xheaders = xheaders
        self.ssl_options = ssl_options
        self._socket = None
        self._started = False

    def listen(self, port, address=""):
        """Binds to the given port and starts the server in a single process.

        This method is a shortcut for:

            server.bind(port, address)
            server.start(1)

        """
        self.bind(port, address)
        self.start(1)

    def bind(self, port, address=""):
        """Binds this server to the given port on the given IP address.

        To start the server, call start(). If you want to run this server
        in a single process, you can call listen() as a shortcut to the
        sequence of bind() and start() calls.
        """
        assert not self._socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        flags = fcntl.fcntl(self._socket.fileno(), fcntl.F_GETFD)
        flags |= fcntl.FD_CLOEXEC
        fcntl.fcntl(self._socket.fileno(), fcntl.F_SETFD, flags)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setblocking(0)
        self._socket.bind((address, port))
        self._socket.listen(128)

    def start(self, num_processes=1):
        """Starts this server in the IOLoop.

        By default, we run the server in this process and do not fork any
        additional child process.

        If num_processes is None or <= 0, we detect the number of cores
        available on this machine and fork that number of child
        processes. If num_processes is given and > 1, we fork that
        specific number of sub-processes.

        Since we use processes and not threads, there is no shared memory
        between any server code.

        Note that multiple processes are not compatible with the autoreload
        module (or the debug=True option to tornado.web.Application).
        When using multiple processes, no IOLoops can be created or
        referenced until after the call to HTTPServer.start(n).
        """
        assert not self._started
        self._started = True
        if num_processes is None or num_processes <= 0:
            num_processes = _cpu_count()
        if num_processes > 1 and ioloop.IOLoop.initialized():
            logging.error("Cannot run in multiple processes: IOLoop instance "
                          "has already been initialized. You cannot call "
                          "IOLoop.instance() before calling start()")
            num_processes = 1
        if num_processes > 1:
            logging.info("Pre-forking %d server processes", num_processes)
            for i in range(num_processes):
                if os.fork() == 0:
                    import random
                    from binascii import hexlify
                    try:
                        # If available, use the same method as
                        # random.py
                        seed = long(hexlify(os.urandom(16)), 16)
                    except NotImplementedError:
                        # Include the pid to avoid initializing two
                        # processes to the same value
                        seed(int(time.time() * 1000) ^ os.getpid())
                    random.seed(seed)
                    self.io_loop = ioloop.IOLoop.instance()
                    self.io_loop.add_handler(
                        self._socket.fileno(), self._handle_events,
                        ioloop.IOLoop.READ)
                    return
            os.waitpid(-1, 0)
        else:
            if not self.io_loop:
                self.io_loop = ioloop.IOLoop.instance()
            self.io_loop.add_handler(self._socket.fileno(),
                                     self._handle_events,
                                     ioloop.IOLoop.READ)

    def stop(self):
        self.io_loop.remove_handler(self._socket.fileno())
        self._socket.close()

    def _handle_events(self, fd, events):
        while True:
            try:
                connection, address = self._socket.accept()
            except socket.error, e:
                if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                    return
                raise
            if self.ssl_options is not None:
                assert ssl, "Python 2.6+ and OpenSSL required for SSL"
                try:
                    connection = ssl.wrap_socket(connection,
                                                 server_side=True,
                                                 do_handshake_on_connect=False,
                                                 **self.ssl_options)
                except ssl.SSLError, err:
                    if err.args[0] == ssl.SSL_ERROR_EOF:
                        return connection.close()
                    else:
                        raise
                except socket.error, err:
                    if err.args[0] == errno.ECONNABORTED:
                        return connection.close()
                    else:
                        raise
            try:
                if self.ssl_options is not None:
                    stream = iostream.SSLIOStream(connection, io_loop=self.io_loop)
                else:
                    stream = iostream.IOStream(connection, io_loop=self.io_loop)
                HTTPConnection(stream, address, self.request_callback,
                               self.no_keep_alive, self.xheaders)
            except:
                logging.error("Error in connection callback", exc_info=True)


class HTTPConnection(object):
    """Handles a connection to an HTTP client, executing HTTP requests.

    We parse HTTP headers and bodies, and execute the request callback
    until the HTTP conection is closed.
    """
    def __init__(self, stream, address, request_callback, no_keep_alive=False,
                 xheaders=False):
        self.stream = stream
        self.address = address
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self._request = None
        self._request_finished = False
        self.stream.read_until("\r\n\r\n", self._on_headers)

    def write(self, chunk):
        assert self._request, "Request closed"
        if not self.stream.closed():
            self.stream.write(chunk, self._on_write_complete)

    def finish(self):
        assert self._request, "Request closed"
        self._request_finished = True
        if not self.stream.writing():
            self._finish_request()

    def _on_write_complete(self):
        if self._request_finished:
            self._finish_request()

    def _finish_request(self):
        if self.no_keep_alive:
            disconnect = True
        else:
            connection_header = self._request.headers.get("Connection")
            if self._request.supports_http_1_1():
                disconnect = connection_header == "close"
            elif ("Content-Length" in self._request.headers
                    or self._request.method in ("HEAD", "GET")):
                disconnect = connection_header != "Keep-Alive"
            else:
                disconnect = True
        self._request = None
        self._request_finished = False
        if disconnect:
            self.stream.close()
            return
        self.stream.read_until("\r\n\r\n", self._on_headers)

    def _on_headers(self, data):
        eol = data.find("\r\n")
        start_line = data[:eol]
        method, uri, version = start_line.split(" ")
        if not version.startswith("HTTP/"):
            raise Exception("Malformed HTTP version in HTTP Request-Line")
        headers = httputil.HTTPHeaders.parse(data[eol:])
        self._request = HTTPRequest(
            connection=self, method=method, uri=uri, version=version,
            headers=headers, remote_ip=self.address[0])

        content_length = headers.get("Content-Length")
        if content_length:
            content_length = int(content_length)
            if content_length > self.stream.max_buffer_size:
                raise Exception("Content-Length too long")
            if headers.get("Expect") == "100-continue":
                self.stream.write("HTTP/1.1 100 (Continue)\r\n\r\n")
            self.stream.read_bytes(content_length, self._on_request_body)
            return

        self.request_callback(self._request)

    def _on_request_body(self, data):
        self._request.body = data
        content_type = self._request.headers.get("Content-Type", "")
        if self._request.method in ("POST", "PUT"):
            if content_type.startswith("application/x-www-form-urlencoded"):
                arguments = cgi.parse_qs(self._request.body)
                for name, values in arguments.iteritems():
                    values = [v for v in values if v]
                    if values:
                        self._request.arguments.setdefault(name, []).extend(
                            values)
            elif content_type.startswith("multipart/form-data"):
                if 'boundary=' in content_type:
                    boundary = content_type.split('boundary=',1)[1]
                    if boundary: self._parse_mime_body(boundary, data)
                else:
                    logging.warning("Invalid multipart/form-data")
        self.request_callback(self._request)

    def _parse_mime_body(self, boundary, data):
        # The standard allows for the boundary to be quoted in the header,
        # although it's rare (it happens at least for google app engine
        # xmpp).  I think we're also supposed to handle backslash-escapes
        # here but I'll save that until we see a client that uses them
        # in the wild.
        if boundary.startswith('"') and boundary.endswith('"'):
            boundary = boundary[1:-1]
        if data.endswith("\r\n"):
            footer_length = len(boundary) + 6
        else:
            footer_length = len(boundary) + 4
        parts = data[:-footer_length].split("--" + boundary + "\r\n")
        for part in parts:
            if not part: continue
            eoh = part.find("\r\n\r\n")
            if eoh == -1:
                logging.warning("multipart/form-data missing headers")
                continue
            headers = httputil.HTTPHeaders.parse(part[:eoh])
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
                self._request.files.setdefault(name, []).append(dict(
                    filename=name_values["filename"], body=value,
                    content_type=ctype))
            else:
                self._request.arguments.setdefault(name, []).append(value)


class HTTPRequest(object):
    """A single HTTP request.

    GET/POST arguments are available in the arguments property, which
    maps arguments names to lists of values (to support multiple values
    for individual names). Names and values are both unicode always.

    File uploads are available in the files property, which maps file
    names to list of files. Each file is a dictionary of the form
    {"filename":..., "content_type":..., "body":...}. The content_type
    comes from the provided HTTP header and should not be trusted
    outright given that it can be easily forged.

    An HTTP request is attached to a single HTTP connection, which can
    be accessed through the "connection" attribute. Since connections
    are typically kept open in HTTP/1.1, multiple requests can be handled
    sequentially on a single connection.
    """
    def __init__(self, method, uri, version="HTTP/1.0", headers=None,
                 body=None, remote_ip=None, protocol=None, host=None,
                 files=None, connection=None):
        self.method = method
        self.uri = uri
        self.version = version
        self.headers = headers or httputil.HTTPHeaders()
        self.body = body or ""
        if connection and connection.xheaders:
            # Squid uses X-Forwarded-For, others use X-Real-Ip
            self.remote_ip = self.headers.get(
                "X-Real-Ip", self.headers.get("X-Forwarded-For", remote_ip))
            self.protocol = self.headers.get("X-Scheme", protocol) or "http"
        else:
            self.remote_ip = remote_ip
            self.protocol = protocol or "http"
        self.host = host or self.headers.get("Host") or "127.0.0.1"
        self.files = files or {}
        self.connection = connection
        self._start_time = time.time()
        self._finish_time = None

        scheme, netloc, path, query, fragment = urlparse.urlsplit(uri)
        self.path = path
        self.query = query
        arguments = cgi.parse_qs(query)
        self.arguments = {}
        for name, values in arguments.iteritems():
            values = [v for v in values if v]
            if values: self.arguments[name] = values

    def supports_http_1_1(self):
        """Returns True if this request supports HTTP/1.1 semantics"""
        return self.version == "HTTP/1.1"

    def write(self, chunk):
        """Writes the given chunk to the response stream."""
        assert isinstance(chunk, str)
        self.connection.write(chunk)

    def finish(self):
        """Finishes this HTTP request on the open connection."""
        self.connection.finish()
        self._finish_time = time.time()

    def full_url(self):
        """Reconstructs the full URL for this request."""
        return self.protocol + "://" + self.host + self.uri

    def request_time(self):
        """Returns the amount of time it took for this request to execute."""
        if self._finish_time is None:
            return time.time() - self._start_time
        else:
            return self._finish_time - self._start_time

    def __repr__(self):
        attrs = ("protocol", "host", "method", "uri", "version", "remote_ip",
                 "remote_ip", "body")
        args = ", ".join(["%s=%r" % (n, getattr(self, n)) for n in attrs])
        return "%s(%s, headers=%s)" % (
            self.__class__.__name__, args, dict(self.headers))
