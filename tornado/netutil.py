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

"""Miscellaneous network utility code."""

import errno
import os
import socket
import stat

from tornado.ioloop import IOLoop
from tornado.platform.auto import set_close_exec

def bind_sockets(port, address=None, family=socket.AF_UNSPEC, backlog=128):
    """Creates listening sockets bound to the given port and address.

    Returns a list of socket objects (multiple sockets are returned if
    the given address maps to multiple IP addresses, which is most common
    for mixed IPv4 and IPv6 use).

    Address may be either an IP address or hostname.  If it's a hostname,
    the server will listen on all IP addresses associated with the
    name.  Address may be an empty string or None to listen on all
    available interfaces.  Family may be set to either socket.AF_INET
    or socket.AF_INET6 to restrict to ipv4 or ipv6 addresses, otherwise
    both will be used if available.

    The ``backlog`` argument has the same meaning as for 
    ``socket.listen()``.
    """
    sockets = []
    if address == "":
        address = None
    flags = socket.AI_PASSIVE
    if hasattr(socket, "AI_ADDRCONFIG"):
        # AI_ADDRCONFIG ensures that we only try to bind on ipv6
        # if the system is configured for it, but the flag doesn't
        # exist on some platforms (specifically WinXP, although
        # newer versions of windows have it)
        flags |= socket.AI_ADDRCONFIG
    for res in socket.getaddrinfo(address, port, family, socket.SOCK_STREAM,
                                  0, flags):
        af, socktype, proto, canonname, sockaddr = res
        sock = socket.socket(af, socktype, proto)
        set_close_exec(sock.fileno())
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if af == socket.AF_INET6:
            # On linux, ipv6 sockets accept ipv4 too by default,
            # but this makes it impossible to bind to both
            # 0.0.0.0 in ipv4 and :: in ipv6.  On other systems,
            # separate sockets *must* be used to listen for both ipv4
            # and ipv6.  For consistency, always disable ipv4 on our
            # ipv6 sockets and use a separate ipv4 socket when needed.
            #
            # Python 2.x on windows doesn't have IPPROTO_IPV6.
            if hasattr(socket, "IPPROTO_IPV6"):
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.setblocking(0)
        sock.bind(sockaddr)
        sock.listen(backlog)
        sockets.append(sock)
    return sockets

if hasattr(socket, 'AF_UNIX'):
    def bind_unix_socket(file, mode=0600, backlog=128):
        """Creates a listening unix socket.

        If a socket with the given name already exists, it will be deleted.
        If any other file with that name exists, an exception will be
        raised.

        Returns a socket object (not a list of socket objects like 
        `bind_sockets`)
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        set_close_exec(sock.fileno())
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(0)
        try:
            st = os.stat(file)
        except OSError, err:
            if err.errno != errno.ENOENT:
                raise
        else:
            if stat.S_ISSOCK(st.st_mode):
                os.remove(file)
            else:
                raise ValueError("File %s exists and is not a socket", file)
        sock.bind(file)
        os.chmod(file, mode)
        sock.listen(backlog)
        return sock

def add_accept_handler(sock, callback, io_loop=None):
    """Adds an ``IOLoop`` event handler to accept new connections on ``sock``.

    When a connection is accepted, ``callback(connection, address)`` will
    be run (``connection`` is a socket object, and ``address`` is the
    address of the other end of the connection).  Note that this signature
    is different from the ``callback(fd, events)`` signature used for
    ``IOLoop`` handlers.
    """
    if io_loop is None:
        io_loop = IOLoop.instance()
    def accept_handler(fd, events):
        while True:
            try:
                connection, address = sock.accept()
            except socket.error, e:
                if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                    return
                raise
            callback(connection, address)
    io_loop.add_handler(sock.fileno(), accept_handler, IOLoop.READ)
