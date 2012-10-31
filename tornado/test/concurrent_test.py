#!/usr/bin/env python
#
# Copyright 2012 Facebook
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

import logging
import re
import socket

from tornado.concurrent import Future, future_wrap
from tornado.escape import utf8, to_unicode
from tornado import gen
from tornado.iostream import IOStream
from tornado.netutil import TCPServer
from tornado.testing import AsyncTestCase, LogTrapTestCase, get_unused_port
from tornado.util import b

class CapServer(TCPServer):
    def handle_stream(self, stream, address):
        logging.info("handle_stream")
        self.stream = stream
        self.stream.read_until(b("\n"), self.handle_read)

    def handle_read(self, data):
        logging.info("handle_read")
        data = to_unicode(data)
        if data == data.upper():
            self.stream.write(b("error\talready capitalized\n"))
        else:
            # data already has \n
            self.stream.write(utf8("ok\t%s" % data.upper()))
        self.stream.close()


class CapError(Exception):
    pass


class BaseCapClient(object):
    def __init__(self, port, io_loop):
        self.port = port
        self.io_loop = io_loop

    def process_response(self, data):
        status, message = re.match('(.*)\t(.*)\n', to_unicode(data)).groups()
        if status == 'ok':
            return message
        else:
            raise CapError(message)


class ManualCapClient(BaseCapClient):
    def capitalize(self, request_data, callback=None):
        logging.info("capitalize")
        self.request_data = request_data
        self.stream = IOStream(socket.socket(), io_loop=self.io_loop)
        self.stream.connect(('127.0.0.1', self.port),
                            callback=self.handle_connect)
        self.future = Future()
        if callback is not None:
            self.future.add_done_callback(callback)
        return self.future

    def handle_connect(self):
        logging.info("handle_connect")
        self.stream.write(utf8(self.request_data + "\n"))
        self.stream.read_until(b('\n'), callback=self.handle_read)

    def handle_read(self, data):
        logging.info("handle_read")
        self.stream.close()
        try:
            self.future.set_result(self.process_response(data))
        except CapError, e:
            self.future.set_exception(e)


class DecoratorCapClient(BaseCapClient):
    @future_wrap
    def capitalize(self, request_data, callback):
        logging.info("capitalize")
        self.request_data = request_data
        self.stream = IOStream(socket.socket(), io_loop=self.io_loop)
        self.stream.connect(('127.0.0.1', self.port),
                            callback=self.handle_connect)
        self.callback = callback

    def handle_connect(self):
        logging.info("handle_connect")
        self.stream.write(utf8(self.request_data + "\n"))
        self.stream.read_until(b('\n'), callback=self.handle_read)

    def handle_read(self, data):
        logging.info("handle_read")
        self.stream.close()
        self.callback(self.process_response(data))


class GeneratorCapClient(BaseCapClient):
    @future_wrap
    @gen.engine
    def capitalize(self, request_data, callback):
        logging.info('capitalize')
        stream = IOStream(socket.socket(), io_loop=self.io_loop)
        logging.info('connecting')
        yield gen.Task(stream.connect, ('127.0.0.1', self.port))
        stream.write(utf8(request_data + '\n'))
        logging.info('reading')
        data = yield gen.Task(stream.read_until, b('\n'))
        logging.info('returning')
        stream.close()
        callback(self.process_response(data))


class ClientTestMixin(object):
    def setUp(self):
        super(ClientTestMixin, self).setUp()
        self.server = CapServer(io_loop=self.io_loop)
        port = get_unused_port()
        self.server.listen(port, address='127.0.0.1')
        self.client = self.client_class(io_loop=self.io_loop, port=port)

    def tearDown(self):
        self.server.stop()
        super(ClientTestMixin, self).tearDown()

    def test_callback(self):
        self.client.capitalize("hello", callback=self.stop)
        future = self.wait()
        self.assertEqual(future.result(), "HELLO")

    def test_callback_error(self):
        self.client.capitalize("HELLO", callback=self.stop)
        future = self.wait()
        self.assertRaisesRegexp(CapError, "already capitalized", future.result)

    def test_future(self):
        future = self.client.capitalize("hello")
        self.io_loop.add_future(future, self.stop)
        self.wait()
        self.assertEqual(future.result(), "HELLO")

    def test_future_error(self):
        future = self.client.capitalize("HELLO")
        self.io_loop.add_future(future, self.stop)
        self.wait()
        self.assertRaisesRegexp(CapError, "already capitalized", future.result)

    def test_generator(self):
        @gen.engine
        def f():
            result = yield self.client.capitalize("hello")
            self.assertEqual(result, "HELLO")
            self.stop()
        f()
        self.wait()

    def test_generator_error(self):
        @gen.engine
        def f():
            with self.assertRaisesRegexp(CapError, "already capitalized"):
                 yield self.client.capitalize("HELLO")
            self.stop()
        f()
        self.wait()


class ManualClientTest(ClientTestMixin, AsyncTestCase, LogTrapTestCase):
    client_class = ManualCapClient


class DecoratorClientTest(ClientTestMixin, AsyncTestCase, LogTrapTestCase):
    client_class = DecoratorCapClient


class GeneratorClientTest(ClientTestMixin, AsyncTestCase, LogTrapTestCase):
    client_class = GeneratorCapClient
