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
from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.ioloop import IOLoop
from tornado.iostream import IOStream, SSLIOStream
from tornado import gen
from tornado.netutil import Resolver

class TCPClient(object):
    """A non-blocking TCP connection factory.
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
                max_buffer_size=None):
        """Connect to the given host and port.

        Asynchronously returns an `.IOStream` (or `.SSLIOStream` if
        ``ssl_options`` is not None).
        """
        addrinfo = yield self.resolver.resolve(host, port, af)
        af, addr = addrinfo[0]
        stream = self._create_stream(af, ssl_options, max_buffer_size)
        yield stream.connect(addr, server_hostname=host)
        raise gen.Return(stream)

    def _create_stream(self, af, ssl_options, max_buffer_size):
        if ssl_options is None:
            return IOStream(socket.socket(af),
                            io_loop=self.io_loop,
                            max_buffer_size=max_buffer_size)
        else:
            return SSLIOStream(socket.socket(af),
                               io_loop=self.io_loop,
                               ssl_options=ssl_options,
                               max_buffer_size=max_buffer_size)
