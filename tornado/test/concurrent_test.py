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
from __future__ import absolute_import, division, print_function

import logging
import re
import socket
import warnings

from tornado.concurrent import Future, run_on_executor, future_set_result_unless_cancelled
from tornado.escape import utf8, to_unicode
from tornado import gen
from tornado.iostream import IOStream
from tornado import stack_context
from tornado.tcpserver import TCPServer
from tornado.testing import AsyncTestCase, bind_unused_port, gen_test
from tornado.test.util import unittest, skipBefore35, exec_test


try:
    from concurrent import futures
except ImportError:
    futures = None


class MiscFutureTest(AsyncTestCase):

    def test_future_set_result_unless_cancelled(self):
        fut = Future()
        future_set_result_unless_cancelled(fut, 42)
        self.assertEqual(fut.result(), 42)
        self.assertFalse(fut.cancelled())

        fut = Future()
        fut.cancel()
        is_cancelled = fut.cancelled()
        future_set_result_unless_cancelled(fut, 42)
        self.assertEqual(fut.cancelled(), is_cancelled)
        if not is_cancelled:
            self.assertEqual(fut.result(), 42)


# The following series of classes demonstrate and test various styles
# of use, with and without generators and futures.


class CapServer(TCPServer):
    @gen.coroutine
    def handle_stream(self, stream, address):
        data = yield stream.read_until(b"\n")
        data = to_unicode(data)
        if data == data.upper():
            stream.write(b"error\talready capitalized\n")
        else:
            # data already has \n
            stream.write(utf8("ok\t%s" % data.upper()))
        stream.close()


class CapError(Exception):
    pass


class BaseCapClient(object):
    def __init__(self, port):
        self.port = port

    def process_response(self, data):
        status, message = re.match('(.*)\t(.*)\n', to_unicode(data)).groups()
        if status == 'ok':
            return message
        else:
            raise CapError(message)


class ManualCapClient(BaseCapClient):
    def capitalize(self, request_data, callback=None):
        logging.debug("capitalize")
        self.request_data = request_data
        self.stream = IOStream(socket.socket())
        self.stream.connect(('127.0.0.1', self.port),
                            callback=self.handle_connect)
        self.future = Future()
        if callback is not None:
            self.future.add_done_callback(
                stack_context.wrap(lambda future: callback(future.result())))
        return self.future

    def handle_connect(self):
        logging.debug("handle_connect")
        self.stream.write(utf8(self.request_data + "\n"))
        self.stream.read_until(b'\n', callback=self.handle_read)

    def handle_read(self, data):
        logging.debug("handle_read")
        self.stream.close()
        try:
            self.future.set_result(self.process_response(data))
        except CapError as e:
            self.future.set_exception(e)


class GeneratorCapClient(BaseCapClient):
    @gen.coroutine
    def capitalize(self, request_data):
        logging.debug('capitalize')
        stream = IOStream(socket.socket())
        logging.debug('connecting')
        yield stream.connect(('127.0.0.1', self.port))
        stream.write(utf8(request_data + '\n'))
        logging.debug('reading')
        data = yield stream.read_until(b'\n')
        logging.debug('returning')
        stream.close()
        raise gen.Return(self.process_response(data))


class ClientTestMixin(object):
    def setUp(self):
        super(ClientTestMixin, self).setUp()  # type: ignore
        self.server = CapServer()
        sock, port = bind_unused_port()
        self.server.add_sockets([sock])
        self.client = self.client_class(port=port)

    def tearDown(self):
        self.server.stop()
        super(ClientTestMixin, self).tearDown()  # type: ignore

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
        @gen.coroutine
        def f():
            result = yield self.client.capitalize("hello")
            self.assertEqual(result, "HELLO")
        self.io_loop.run_sync(f)

    def test_generator_error(self):
        @gen.coroutine
        def f():
            with self.assertRaisesRegexp(CapError, "already capitalized"):
                yield self.client.capitalize("HELLO")
        self.io_loop.run_sync(f)


class ManualClientTest(ClientTestMixin, AsyncTestCase):
    client_class = ManualCapClient

    def setUp(self):
        self.warning_catcher = warnings.catch_warnings()
        self.warning_catcher.__enter__()
        warnings.simplefilter('ignore', DeprecationWarning)
        super(ManualClientTest, self).setUp()

    def tearDown(self):
        super(ManualClientTest, self).tearDown()
        self.warning_catcher.__exit__(None, None, None)


class GeneratorClientTest(ClientTestMixin, AsyncTestCase):
    client_class = GeneratorCapClient


@unittest.skipIf(futures is None, "concurrent.futures module not present")
class RunOnExecutorTest(AsyncTestCase):
    @gen_test
    def test_no_calling(self):
        class Object(object):
            def __init__(self):
                self.executor = futures.thread.ThreadPoolExecutor(1)

            @run_on_executor
            def f(self):
                return 42

        o = Object()
        answer = yield o.f()
        self.assertEqual(answer, 42)

    @gen_test
    def test_call_with_no_args(self):
        class Object(object):
            def __init__(self):
                self.executor = futures.thread.ThreadPoolExecutor(1)

            @run_on_executor()
            def f(self):
                return 42

        o = Object()
        answer = yield o.f()
        self.assertEqual(answer, 42)

    @gen_test
    def test_call_with_executor(self):
        class Object(object):
            def __init__(self):
                self.__executor = futures.thread.ThreadPoolExecutor(1)

            @run_on_executor(executor='_Object__executor')
            def f(self):
                return 42

        o = Object()
        answer = yield o.f()
        self.assertEqual(answer, 42)

    @skipBefore35
    @gen_test
    def test_async_await(self):
        class Object(object):
            def __init__(self):
                self.executor = futures.thread.ThreadPoolExecutor(1)

            @run_on_executor()
            def f(self):
                return 42

        o = Object()
        namespace = exec_test(globals(), locals(), """
        async def f():
            answer = await o.f()
            return answer
        """)
        result = yield namespace['f']()
        self.assertEqual(result, 42)


if __name__ == '__main__':
    unittest.main()
