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

import gc
import logging
import re
import socket
import sys
import traceback
import warnings

from tornado.concurrent import (Future, return_future, ReturnValueIgnoredError,
                                run_on_executor, future_set_result_unless_cancelled)
from tornado.escape import utf8, to_unicode
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream
from tornado.log import app_log
from tornado import stack_context
from tornado.tcpserver import TCPServer
from tornado.testing import AsyncTestCase, ExpectLog, bind_unused_port, gen_test
from tornado.test.util import unittest, skipBefore35, exec_test, ignore_deprecation


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


class ReturnFutureTest(AsyncTestCase):
    with ignore_deprecation():
        @return_future
        def sync_future(self, callback):
            callback(42)

        @return_future
        def async_future(self, callback):
            self.io_loop.add_callback(callback, 42)

        @return_future
        def immediate_failure(self, callback):
            1 / 0

        @return_future
        def delayed_failure(self, callback):
            self.io_loop.add_callback(lambda: 1 / 0)

        @return_future
        def return_value(self, callback):
            # Note that the result of both running the callback and returning
            # a value (or raising an exception) is unspecified; with current
            # implementations the last event prior to callback resolution wins.
            return 42

        @return_future
        def no_result_future(self, callback):
            callback()

    def test_immediate_failure(self):
        with self.assertRaises(ZeroDivisionError):
            # The caller sees the error just like a normal function.
            self.immediate_failure(callback=self.stop)
        # The callback is not run because the function failed synchronously.
        self.io_loop.add_timeout(self.io_loop.time() + 0.05, self.stop)
        result = self.wait()
        self.assertIs(result, None)

    def test_return_value(self):
        with self.assertRaises(ReturnValueIgnoredError):
            self.return_value(callback=self.stop)

    def test_callback_kw(self):
        with ignore_deprecation():
            future = self.sync_future(callback=self.stop)
        result = self.wait()
        self.assertEqual(result, 42)
        self.assertEqual(future.result(), 42)

    def test_callback_positional(self):
        # When the callback is passed in positionally, future_wrap shouldn't
        # add another callback in the kwargs.
        with ignore_deprecation():
            future = self.sync_future(self.stop)
        result = self.wait()
        self.assertEqual(result, 42)
        self.assertEqual(future.result(), 42)

    def test_no_callback(self):
        future = self.sync_future()
        self.assertEqual(future.result(), 42)

    def test_none_callback_kw(self):
        # explicitly pass None as callback
        future = self.sync_future(callback=None)
        self.assertEqual(future.result(), 42)

    def test_none_callback_pos(self):
        future = self.sync_future(None)
        self.assertEqual(future.result(), 42)

    def test_async_future(self):
        future = self.async_future()
        self.assertFalse(future.done())
        self.io_loop.add_future(future, self.stop)
        future2 = self.wait()
        self.assertIs(future, future2)
        self.assertEqual(future.result(), 42)

    @gen_test
    def test_async_future_gen(self):
        result = yield self.async_future()
        self.assertEqual(result, 42)

    def test_delayed_failure(self):
        future = self.delayed_failure()
        with ignore_deprecation():
            self.io_loop.add_future(future, self.stop)
            future2 = self.wait()
        self.assertIs(future, future2)
        with self.assertRaises(ZeroDivisionError):
            future.result()

    def test_kw_only_callback(self):
        with ignore_deprecation():
            @return_future
            def f(**kwargs):
                kwargs['callback'](42)
        future = f()
        self.assertEqual(future.result(), 42)

    def test_error_in_callback(self):
        with ignore_deprecation():
            self.sync_future(callback=lambda future: 1 / 0)
        # The exception gets caught by our StackContext and will be re-raised
        # when we wait.
        self.assertRaises(ZeroDivisionError, self.wait)

    def test_no_result_future(self):
        with ignore_deprecation():
            future = self.no_result_future(self.stop)
        result = self.wait()
        self.assertIs(result, None)
        # result of this future is undefined, but not an error
        future.result()

    def test_no_result_future_callback(self):
        with ignore_deprecation():
            future = self.no_result_future(callback=lambda: self.stop())
        result = self.wait()
        self.assertIs(result, None)
        future.result()

    @gen_test
    def test_future_traceback_legacy(self):
        with ignore_deprecation():
            @return_future
            @gen.engine
            def f(callback):
                yield gen.Task(self.io_loop.add_callback)
                try:
                    1 / 0
                except ZeroDivisionError:
                    self.expected_frame = traceback.extract_tb(
                        sys.exc_info()[2], limit=1)[0]
                    raise
            try:
                yield f()
                self.fail("didn't get expected exception")
            except ZeroDivisionError:
                tb = traceback.extract_tb(sys.exc_info()[2])
                self.assertIn(self.expected_frame, tb)

    @gen_test
    def test_future_traceback(self):
        @gen.coroutine
        def f():
            yield gen.moment
            try:
                1 / 0
            except ZeroDivisionError:
                self.expected_frame = traceback.extract_tb(
                    sys.exc_info()[2], limit=1)[0]
                raise
        try:
            yield f()
            self.fail("didn't get expected exception")
        except ZeroDivisionError:
            tb = traceback.extract_tb(sys.exc_info()[2])
            self.assertIn(self.expected_frame, tb)

    @gen_test
    def test_uncaught_exception_log(self):
        if IOLoop.configured_class().__name__.endswith('AsyncIOLoop'):
            # Install an exception handler that mirrors our
            # non-asyncio logging behavior.
            def exc_handler(loop, context):
                app_log.error('%s: %s', context['message'],
                              type(context.get('exception')))
            self.io_loop.asyncio_loop.set_exception_handler(exc_handler)

        @gen.coroutine
        def f():
            yield gen.moment
            1 / 0

        g = f()

        with ExpectLog(app_log,
                       "(?s)Future.* exception was never retrieved:"
                       ".*ZeroDivisionError"):
            yield gen.moment
            yield gen.moment
            # For some reason, TwistedIOLoop and pypy3 need a third iteration
            # in order to drain references to the future
            yield gen.moment
            del g
            gc.collect()  # for PyPy


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


class DecoratorCapClient(BaseCapClient):
    with ignore_deprecation():
        @return_future
        def capitalize(self, request_data, callback):
            logging.debug("capitalize")
            self.request_data = request_data
            self.stream = IOStream(socket.socket())
            self.stream.connect(('127.0.0.1', self.port),
                                callback=self.handle_connect)
            self.callback = callback

    def handle_connect(self):
        logging.debug("handle_connect")
        self.stream.write(utf8(self.request_data + "\n"))
        self.stream.read_until(b'\n', callback=self.handle_read)

    def handle_read(self, data):
        logging.debug("handle_read")
        self.stream.close()
        self.callback(self.process_response(data))


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

    def test_callback(self):
        with ignore_deprecation():
            self.client.capitalize("hello", callback=self.stop)
        result = self.wait()
        self.assertEqual(result, "HELLO")

    def test_callback_error(self):
        with ignore_deprecation():
            self.client.capitalize("HELLO", callback=self.stop)
            self.assertRaisesRegexp(CapError, "already capitalized", self.wait)

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


class DecoratorClientTest(ClientTestMixin, AsyncTestCase):
    client_class = DecoratorCapClient

    def setUp(self):
        self.warning_catcher = warnings.catch_warnings()
        self.warning_catcher.__enter__()
        warnings.simplefilter('ignore', DeprecationWarning)
        super(DecoratorClientTest, self).setUp()

    def tearDown(self):
        super(DecoratorClientTest, self).tearDown()
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
