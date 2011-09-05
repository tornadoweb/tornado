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
            assert res is None
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
            1/0
        self.assertRaises(ZeroDivisionError, self.run_gen, f)

    def test_exception_phase2(self):
        @gen.engine
        def f():
            self.io_loop.add_callback((yield gen.Callback("k1")))
            yield gen.Wait("k1")
            1/0
        self.assertRaises(ZeroDivisionError, self.run_gen, f)

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

class GenWebTest(AsyncHTTPTestCase, LogTrapTestCase):
    def get_app(self):
        return Application([
                ('/sequence', GenSequenceHandler),
                ('/task', GenTaskHandler),
                ])

    def test_sequence_handler(self):
        response = self.fetch('/sequence')
        self.assertEqual(response.body, b("123"))

    def test_task_handler(self):
        response = self.fetch('/task?url=%s' % url_escape(self.get_url('/sequence')))
        self.assertEqual(response.body, b("got response: 123"))
