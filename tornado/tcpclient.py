#!/usr/bin/env python
#
# Copyright 2014 Facebook
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

"""A non-blocking TCP connection factory.
"""
from __future__ import absolute_import, division, print_function

import functools
import socket

from tornado.concurrent import Future
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado import gen
from tornado.netutil import Resolver

_INITIAL_CONNECT_TIMEOUT = 0.3


class _Connector(object):
    """A stateless implementation of the "Happy Eyeballs" algorithm.

    "Happy Eyeballs" is documented in RFC6555 as the recommended practice
    for when both IPv4 and IPv6 addresses are available.

    In this implementation, we partition the addresses by family, and
    make the first connection attempt to whichever address was
    returned first by ``getaddrinfo``.  If that connection fails or
    times out, we begin a connection in parallel to the first address
    of the other family.  If there are additional failures we retry
    with other addresses, keeping one connection attempt per family
    in flight at a time.

    http://tools.ietf.org/html/rfc6555

    """
    def __init__(self, addrinfo, io_loop, connect):
        self.io_loop = io_loop
        self.connect = connect

        self.future = Future()
        self.timeout = None
        self.last_error = None
        self.remaining = len(addrinfo)
        self.primary_addrs, self.secondary_addrs = self.split(addrinfo)

    @staticmethod
    def split(addrinfo):
        """Partition the ``addrinfo`` list by address family.

        Returns two lists.  The first list contains the first entry from
        ``addrinfo`` and all others with the same family, and the
        second list contains all other addresses (normally one list will
        be AF_INET and the other AF_INET6, although non-standard resolvers
        may return additional families).
        """
        primary = []
        secondary = []
        primary_af = addrinfo[0][0]
        for af, addr in addrinfo:
            if af == primary_af:
                primary.append((af, addr))
            else:
                secondary.append((af, addr))
        return primary, secondary

    def start(self, timeout=_INITIAL_CONNECT_TIMEOUT):
        self.try_connect(iter(self.primary_addrs))
        self.set_timout(timeout)
        return self.future

    def try_connect(self, addrs):
        try:
            af, addr = next(addrs)
        except StopIteration:
            # We've reached the end of our queue, but the other queue
            # might still be working.  Send a final error on the future
            # only when both queues are finished.
            if self.remaining == 0 and not self.future.done():
                self.future.set_exception(self.last_error or
                                          IOError("connection failed"))
            return
        future = self.connect(af, addr)
        future.add_done_callback(functools.partial(self.on_connect_done,
                                                   addrs, af, addr))

    def on_connect_done(self, addrs, af, addr, future):
        self.remaining -= 1
        try:
            stream = future.result()
        except Exception as e:
            if self.future.done():
                return
            # Error: try again (but remember what happened so we have an
            # error to raise in the end)
            self.last_error = e
            self.try_connect(addrs)
            if self.timeout is not None:
                # If the first attempt failed, don't wait for the
                # timeout to try an address from the secondary queue.
                self.io_loop.remove_timeout(self.timeout)
                self.on_timeout()
            return
        self.clear_timeout()
        if self.future.done():
            # This is a late arrival; just drop it.
            stream.close()
        else:
            self.future.set_result((af, addr, stream))

    def set_timout(self, timeout):
        self.timeout = self.io_loop.add_timeout(self.io_loop.time() + timeout,
                                                self.on_timeout)

    def on_timeout(self):
        self.timeout = None
        self.try_connect(iter(self.secondary_addrs))

    def clear_timeout(self):
        if self.timeout is not None:
            self.io_loop.remove_timeout(self.timeout)


class TCPClient(object):
    """A non-blocking TCP connection factory.

    .. versionchanged:: 4.1
       The ``io_loop`` argument is deprecated.
    """
    def __init__(self, resolver=None, io_loop=None):
        self.io_loop = io_loop or IOLoop.current()
        if resolver is not None:
            self.resolver = resolver
            self._own_resolver = False
        else:
            self.resolver = Resolver(io_loop=io_loop)
            self._own_resolver = True

    def close(self):
        if self._own_resolver:
            self.resolver.close()

    @gen.coroutine
    def connect(self, host, port, af=socket.AF_UNSPEC, ssl_options=None,
                max_buffer_size=None, source_ip=None, source_port=None):
        """Connect to the given host and port.

        Asynchronously returns an `.IOStream` (or `.SSLIOStream` if
        ``ssl_options`` is not None).

        Using the ``source_ip`` kwarg, one can specify the source
        IP address to use when establishing the connection.
        In case the user needs to resolve and
        use a specific interface, it has to be handled outside
        of Tornado as this depends very much on the platform.

        Similarly, when the user requires a certain source port, it can
        be specified using the ``source_port`` arg.

        .. versionchanged:: 4.5
           Added the ``source_ip`` and ``source_port`` arguments.
        """
        addrinfo = yield self.resolver.resolve(host, port, af)
        connector = _Connector(
            addrinfo, self.io_loop,
            functools.partial(self._create_stream, max_buffer_size,
                              source_ip=source_ip, source_port=source_port)
        )
        af, addr, stream = yield connector.start()
        # TODO: For better performance we could cache the (af, addr)
        # information here and re-use it on subsequent connections to
        # the same host. (http://tools.ietf.org/html/rfc6555#section-4.2)
        if ssl_options is not None:
            stream = yield stream.start_tls(False, ssl_options=ssl_options,
                                            server_hostname=host)
        raise gen.Return(stream)

    def _create_stream(self, max_buffer_size, af, addr, source_ip=None,
                       source_port=None):
        # Always connect in plaintext; we'll convert to ssl if necessary
        # after one connection has completed.
        source_port_bind = source_port if isinstance(source_port, int) else 0
        source_ip_bind = source_ip
        if source_port_bind and not source_ip:
            # User required a specific port, but did not specify
            # a certain source IP, will bind to the default loopback.
            source_ip_bind = '::1' if af == socket.AF_INET6 else '127.0.0.1'
            # Trying to use the same address family as the requested af socket:
            # - 127.0.0.1 for IPv4
            # - ::1 for IPv6
        socket_obj = socket.socket(af)
        if source_port_bind or source_ip_bind:
            # If the user requires binding also to a specific IP/port.
            try:
                socket_obj.bind((source_ip_bind, source_port_bind))
            except socket.error:
                socket_obj.close()
                # Fail loudly if unable to use the IP/port.
                raise
        try:
            stream = IOStream(socket_obj,
                              io_loop=self.io_loop,
                              max_buffer_size=max_buffer_size)
        except socket.error as e:
            fu = Future()
            fu.set_exception(e)
            return fu
        else:
            return stream.connect(addr)
