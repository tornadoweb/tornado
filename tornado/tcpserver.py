#!/usr/bin/env python
#
# Copyright 2011 Facebook
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

from __future__ import absolute_import, division, with_statement

import errno
import logging
import socket

from tornado import process
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream, SSLIOStream
from tornado.netutil import add_accept_handler, bind_sockets, wrap_socket

try:
    import ssl  # Python 2.6+
except ImportError:
    ssl = None


class TCPServer(object):
    r"""A non-blocking, single-threaded TCP server.

    `TCPServer` takes a ``protocol`` argument that is called when an incoming
    connection is opened.

    `TCPServer` can serve SSL traffic with Python 2.6+ and OpenSSL.
    To make this server serve SSL traffic, send the ssl_options dictionary
    argument with the arguments required for the `ssl.wrap_socket` method,
    including "certfile" and "keyfile"::

       TCPServer(ssl_options={
           "certfile": os.path.join(data_dir, "mydomain.crt"),
           "keyfile": os.path.join(data_dir, "mydomain.key"),
       })

    `TCPServer` supports TLS NPN if Python 3.3+ and OpenSSL 1.0.1+ are
    installed. The ``npn_protocols`` argument specifies a list of ``(name,
    handler)`` tuples in order of preference; see `SPDYServer` for an example.
    Once NPN is completed, the handler for the selected name will be called.
    If the client does not support NPN, the handler passed in the ``protocol``
    argument will be used instead. This parameter requires ``ssl_options`` to
    be passed as well.

    `TCPServer` initialization follows one of three patterns:

    1. `listen`: simple single-process::

            server = TCPServer()
            server.listen(8888)
            IOLoop.instance().start()

    2. `bind`/`start`: simple multi-process::

            server = TCPServer()
            server.bind(8888)
            server.start(0)  # Forks multiple sub-processes
            IOLoop.instance().start()

       When using this interface, an `IOLoop` must *not* be passed
       to the `TCPServer` constructor.  `start` will always start
       the server on the default singleton `IOLoop`.

    3. `add_sockets`: advanced multi-process::

            sockets = bind_sockets(8888)
            tornado.process.fork_processes(0)
            server = TCPServer()
            server.add_sockets(sockets)
            IOLoop.instance().start()

       The `add_sockets` interface is more complicated, but it can be
       used with `tornado.process.fork_processes` to give you more
       flexibility in when the fork happens.  `add_sockets` can
       also be used in single-process servers if you want to create
       your listening sockets in some way other than
       `bind_sockets`.

    """
    def __init__(self, protocol, io_loop=None, npn_protocols=None,
                 ssl_options=None):
        self.protocol = protocol
        self.io_loop = io_loop
        assert not ssl_options or ssl, "Python 2.6+ and OpenSSL required for SSL"
        assert ssl_options or not npn_protocols, "npn_protocols requires ssl_options"
        self.npn_protocols = npn_protocols
        self.ssl_options = ssl_options
        if self.ssl_options:
            self.ssl_options.update({
                'server_side': True,
                'do_handshake_on_connect': False
            })
        self._sockets = {}  # fd -> socket object
        self._pending_sockets = []
        self._started = False

    def listen(self, port, address=""):
        """Starts accepting connections on the given port.

        This method may be called more than once to listen on multiple ports.
        `listen` takes effect immediately; it is not necessary to call
        `TCPServer.start` afterwards.  It is, however, necessary to start
        the `IOLoop`.
        """
        sockets = bind_sockets(port, address=address)
        self.add_sockets(sockets)

    def add_sockets(self, sockets):
        """Makes this server start accepting connections on the given sockets.

        The ``sockets`` parameter is a list of socket objects such as
        those returned by `bind_sockets`.
        `add_sockets` is typically used in combination with that
        method and `tornado.process.fork_processes` to provide greater
        control over the initialization of a multi-process server.
        """
        if self.io_loop is None:
            self.io_loop = IOLoop.instance()

        for sock in sockets:
            self._sockets[sock.fileno()] = sock
            add_accept_handler(sock, self._handle_connection,
                               io_loop=self.io_loop)

    def add_socket(self, socket):
        """Singular version of `add_sockets`.  Takes a single socket object."""
        self.add_sockets([socket])

    def bind(self, port, address=None, family=socket.AF_UNSPEC, backlog=128):
        """Binds this server to the given port on the given address.

        To start the server, call `start`. If you want to run this server
        in a single process, you can call `listen` as a shortcut to the
        sequence of `bind` and `start` calls.

        Address may be either an IP address or hostname.  If it's a hostname,
        the server will listen on all IP addresses associated with the
        name.  Address may be an empty string or None to listen on all
        available interfaces.  Family may be set to either ``socket.AF_INET``
        or ``socket.AF_INET6`` to restrict to ipv4 or ipv6 addresses, otherwise
        both will be used if available.

        The ``backlog`` argument has the same meaning as for
        `socket.listen`.

        This method may be called multiple times prior to `start` to listen
        on multiple ports or interfaces.
        """
        sockets = bind_sockets(port, address=address, family=family,
                               backlog=backlog)
        if self._started:
            self.add_sockets(sockets)
        else:
            self._pending_sockets.extend(sockets)

    def start(self, num_processes=1):
        """Starts this server in the IOLoop.

        By default, we run the server in this process and do not fork any
        additional child process.

        If num_processes is ``None`` or <= 0, we detect the number of cores
        available on this machine and fork that number of child
        processes. If num_processes is given and > 1, we fork that
        specific number of sub-processes.

        Since we use processes and not threads, there is no shared memory
        between any server code.

        Note that multiple processes are not compatible with the autoreload
        module (or the ``debug=True`` option to `tornado.web.Application`).
        When using multiple processes, no IOLoops can be created or
        referenced until after the call to ``TCPServer.start(n)``.
        """
        assert not self._started
        self._started = True
        if num_processes != 1:
            process.fork_processes(num_processes)
        sockets = self._pending_sockets
        self._pending_sockets = []
        self.add_sockets(sockets)

    def stop(self):
        """Stops listening for new connections.

        Requests currently in progress may still continue after the
        server is stopped.
        """
        for fd, sock in self._sockets.iteritems():
            self.io_loop.remove_handler(fd)
            sock.close()

    def _handle_connection(self, connection, address):
        if self.ssl_options is not None:
            try:
                npn_protocols = None
                if self.npn_protocols is not None:
                    npn_protocols = [name for name, _ in self.npn_protocols]
                connection = wrap_socket(connection, self.ssl_options,
                                         npn_protocols)
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

            stream = SSLIOStream(connection, io_loop=self.io_loop)
            if self.npn_protocols is not None:
                def on_connect():
                    handler = self.protocol
                    selected_name = connection.selected_npn_protocol()
                    if selected_name:
                        for name, protocol in self.npn_protocols:
                            if name == selected_name:
                                handler = protocol
                                break
                    self._run_protocol(handler, stream, address)
                stream.set_connect_callback(on_connect)
                return
        else:
            stream = IOStream(connection, io_loop=self.io_loop)
        self._run_protocol(self.protocol, stream, address)

    def _run_protocol(self, handler, stream, address):
        try:
            handler(stream, address, self)
        except Exception:
            logging.error("Error in connection callback", exc_info=True)
