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

from __future__ import absolute_import, division, print_function, with_statement

from contextlib import closing

from tornado.log import gen_log
from tornado.tcpclient import TCPClient
from tornado.tcpserver import TCPServer
from tornado.testing import AsyncTestCase, bind_unused_port, gen_test, ExpectLog

class TestTCPServer(TCPServer):
    def __init__(self):
        super(TestTCPServer, self).__init__()
        self.streams = []
        socket, self.port = bind_unused_port()
        self.add_socket(socket)

    def handle_stream(self, stream, address):
        self.streams.append(stream)

    def stop(self):
        super(TestTCPServer, self).stop()
        for stream in self.streams:
            stream.close()

class TCPClientTest(AsyncTestCase):
    def setUp(self):
        super(TCPClientTest, self).setUp()
        self.server = TestTCPServer()
        self.port = self.server.port
        self.client = TCPClient()

    def tearDown(self):
        self.client.close()
        self.server.stop()
        super(TCPClientTest, self).tearDown()

    @gen_test
    def test_connect_ipv4(self):
        stream = yield self.client.connect('127.0.0.1', self.port)
        with closing(stream):
            stream.write(b"hello")
            data = yield self.server.streams[0].read_bytes(5)
            self.assertEqual(data, b"hello")

    @gen_test
    def test_refused_ipv4(self):
        sock, port = bind_unused_port()
        sock.close()
        with ExpectLog(gen_log, 'Connect error'):
            with self.assertRaises(IOError):
                yield self.client.connect('127.0.0.1', port)
