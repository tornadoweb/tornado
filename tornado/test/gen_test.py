from __future__ import absolute_import, division, with_statement
import functools
from tornado.escape import url_escape
from tornado.httpclient import AsyncHTTPClient
from tornado.testing import AsyncHTTPTestCase, AsyncTestCase, LogTrapTestCase
from tornado.util import b
from tornado.web import Application, RequestHandler, asynchronous

from tornado import gen


class GenTest(AsyncTestCase):
    def run_gen(self, f):
        f()
        self.wait()

    def delay_callback(self, iterations, callback, arg):
        """Runs callback(arg) after a number of IOLoop iterations."""
        if iterations == 0:
            callback(arg)
        else:
            self.io_loop.add_callback(functools.partial(
                    self.delay_callback, iterations - 1, callback, arg))

    def test_no_yield(self):
        @gen.engine
        def f():
            self.stop()
        self.run_gen(f)

    def test_inline_cb(self):
        @gen.engine
        def f():
            (yield gen.Callback("k1"))()
            res = yield gen.Wait("k1")
            self.assertTrue(res is None)
            self.stop()
        self.run_gen(f)

    def test_ioloop_cb(self):
        @gen.engine
        def f():
            self.io_loop.add_callback((yield gen.Callback("k1")))
            yield gen.Wait("k1")
            self.stop()
        self.run_gen(f)

    def test_exception_phase1(self):
        @gen.engine
        def f():
            1 / 0
        self.assertRaises(ZeroDivisionError, self.run_gen, f)

    def test_exception_phase2(self):
        @gen.engine
        def f():
            self.io_loop.add_callback((yield gen.Callback("k1")))
            yield gen.Wait("k1")
            1 / 0
        self.assertRaises(ZeroDivisionError, self.run_gen, f)

    def test_exception_in_task_phase1(self):
        def fail_task(callback):
            1 / 0

        @gen.engine
        def f():
            try:
                yield gen.Task(fail_task)
                raise Exception("did not get expected exception")
            except ZeroDivisionError:
                self.stop()
        self.run_gen(f)

    def test_exception_in_task_phase2(self):
        # This is the case that requires the use of stack_context in gen.engine
        def fail_task(callback):
            self.io_loop.add_callback(lambda: 1 / 0)

        @gen.engine
        def f():
            try:
                yield gen.Task(fail_task)
                raise Exception("did not get expected exception")
            except ZeroDivisionError:
                self.stop()
        self.run_gen(f)

    def test_with_arg(self):
        @gen.engine
        def f():
            (yield gen.Callback("k1"))(42)
            res = yield gen.Wait("k1")
            self.assertEqual(42, res)
            self.stop()
        self.run_gen(f)

    def test_key_reuse(self):
        @gen.engine
        def f():
            yield gen.Callback("k1")
            yield gen.Callback("k1")
            self.stop()
        self.assertRaises(gen.KeyReuseError, self.run_gen, f)

    def test_key_mismatch(self):
        @gen.engine
        def f():
            yield gen.Callback("k1")
            yield gen.Wait("k2")
            self.stop()
        self.assertRaises(gen.UnknownKeyError, self.run_gen, f)

    def test_leaked_callback(self):
        @gen.engine
        def f():
            yield gen.Callback("k1")
            self.stop()
        self.assertRaises(gen.LeakedCallbackError, self.run_gen, f)

    def test_parallel_callback(self):
        @gen.engine
        def f():
            for k in range(3):
                self.io_loop.add_callback((yield gen.Callback(k)))
            yield gen.Wait(1)
            self.io_loop.add_callback((yield gen.Callback(3)))
            yield gen.Wait(0)
            yield gen.Wait(3)
            yield gen.Wait(2)
            self.stop()
        self.run_gen(f)

    def test_bogus_yield(self):
        @gen.engine
        def f():
            yield 42
        self.assertRaises(gen.BadYieldError, self.run_gen, f)

    def test_reuse(self):
        @gen.engine
        def f():
            self.io_loop.add_callback((yield gen.Callback(0)))
            yield gen.Wait(0)
            self.stop()
        self.run_gen(f)
        self.run_gen(f)

    def test_task(self):
        @gen.engine
        def f():
            yield gen.Task(self.io_loop.add_callback)
            self.stop()
        self.run_gen(f)

    def test_wait_all(self):
        @gen.engine
        def f():
            (yield gen.Callback("k1"))("v1")
            (yield gen.Callback("k2"))("v2")
            results = yield gen.WaitAll(["k1", "k2"])
            self.assertEqual(results, ["v1", "v2"])
            self.stop()
        self.run_gen(f)

    def test_exception_in_yield(self):
        @gen.engine
        def f():
            try:
                yield gen.Wait("k1")
                raise Exception("did not get expected exception")
            except gen.UnknownKeyError:
                pass
            self.stop()
        self.run_gen(f)

    def test_resume_after_exception_in_yield(self):
        @gen.engine
        def f():
            try:
                yield gen.Wait("k1")
                raise Exception("did not get expected exception")
            except gen.UnknownKeyError:
                pass
            (yield gen.Callback("k2"))("v2")
            self.assertEqual((yield gen.Wait("k2")), "v2")
            self.stop()
        self.run_gen(f)

    def test_orphaned_callback(self):
        @gen.engine
        def f():
            self.orphaned_callback = yield gen.Callback(1)
        try:
            self.run_gen(f)
            raise Exception("did not get expected exception")
        except gen.LeakedCallbackError:
            pass
        self.orphaned_callback()

    def test_multi(self):
        @gen.engine
        def f():
            (yield gen.Callback("k1"))("v1")
            (yield gen.Callback("k2"))("v2")
            results = yield [gen.Wait("k1"), gen.Wait("k2")]
            self.assertEqual(results, ["v1", "v2"])
            self.stop()
        self.run_gen(f)

    def test_multi_delayed(self):
        @gen.engine
        def f():
            # callbacks run at different times
            responses = yield [
                gen.Task(self.delay_callback, 3, arg="v1"),
                gen.Task(self.delay_callback, 1, arg="v2"),
                ]
            self.assertEqual(responses, ["v1", "v2"])
            self.stop()
        self.run_gen(f)

    def test_arguments(self):
        @gen.engine
        def f():
            (yield gen.Callback("noargs"))()
            self.assertEqual((yield gen.Wait("noargs")), None)
            (yield gen.Callback("1arg"))(42)
            self.assertEqual((yield gen.Wait("1arg")), 42)

            (yield gen.Callback("kwargs"))(value=42)
            result = yield gen.Wait("kwargs")
            self.assertTrue(isinstance(result, gen.Arguments))
            self.assertEqual(((), dict(value=42)), result)
            self.assertEqual(dict(value=42), result.kwargs)

            (yield gen.Callback("2args"))(42, 43)
            result = yield gen.Wait("2args")
            self.assertTrue(isinstance(result, gen.Arguments))
            self.assertEqual(((42, 43), {}), result)
            self.assertEqual((42, 43), result.args)

            def task_func(callback):
                callback(None, error="foo")
            result = yield gen.Task(task_func)
            self.assertTrue(isinstance(result, gen.Arguments))
            self.assertEqual(((None,), dict(error="foo")), result)

            self.stop()
        self.run_gen(f)

    def test_stack_context_leak(self):
        # regression test: repeated invocations of a gen-based
        # function should not result in accumulated stack_contexts
        from tornado import stack_context

        @gen.engine
        def inner(callback):
            yield gen.Task(self.io_loop.add_callback)
            callback()

        @gen.engine
        def outer():
            for i in xrange(10):
                yield gen.Task(inner)
            stack_increase = len(stack_context._state.contexts) - initial_stack_depth
            self.assertTrue(stack_increase <= 2)
            self.stop()
        initial_stack_depth = len(stack_context._state.contexts)
        self.run_gen(outer)


class GenSequenceHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        self.io_loop = self.request.connection.stream.io_loop
        self.io_loop.add_callback((yield gen.Callback("k1")))
        yield gen.Wait("k1")
        self.write("1")
        self.io_loop.add_callback((yield gen.Callback("k2")))
        yield gen.Wait("k2")
        self.write("2")
        # reuse an old key
        self.io_loop.add_callback((yield gen.Callback("k1")))
        yield gen.Wait("k1")
        self.finish("3")


class GenTaskHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        io_loop = self.request.connection.stream.io_loop
        client = AsyncHTTPClient(io_loop=io_loop)
        response = yield gen.Task(client.fetch, self.get_argument('url'))
        response.rethrow()
        self.finish(b("got response: ") + response.body)


class GenExceptionHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        # This test depends on the order of the two decorators.
        io_loop = self.request.connection.stream.io_loop
        yield gen.Task(io_loop.add_callback)
        raise Exception("oops")


class GenYieldExceptionHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        io_loop = self.request.connection.stream.io_loop
        # Test the interaction of the two stack_contexts.

        def fail_task(callback):
            io_loop.add_callback(lambda: 1 / 0)
        try:
            yield gen.Task(fail_task)
            raise Exception("did not get expected exception")
        except ZeroDivisionError:
            self.finish('ok')


class GenWebTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([
                ('/sequence', GenSequenceHandler),
                ('/task', GenTaskHandler),
                ('/exception', GenExceptionHandler),
                ('/yield_exception', GenYieldExceptionHandler),
                ])

    def test_sequence_handler(self):
        response = self.fetch('/sequence')
        self.assertEqual(response.body, b("123"))

    def test_task_handler(self):
        response = self.fetch('/task?url=%s' % url_escape(self.get_url('/sequence')))
        self.assertEqual(response.body, b("got response: 123"))

    def test_exception_handler(self):
        # Make sure we get an error and not a timeout
        response = self.fetch('/exception')
        self.assertEqual(500, response.code)

    def test_yield_exception_handler(self):
        response = self.fetch('/yield_exception')
        self.assertEqual(response.body, b('ok'))
