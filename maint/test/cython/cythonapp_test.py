try:
    import backports_abc
except ImportError:
    raise
else:
    backports_abc.patch()

from tornado.testing import AsyncTestCase, gen_test

import cythonapp


class CythonCoroutineTest(AsyncTestCase):
    @gen_test
    def test_native_coroutine(self):
        x = yield cythonapp.native_coroutine()
        self.assertEqual(x, "goodbye")

    @gen_test
    def test_decorated_coroutine(self):
        x = yield cythonapp.decorated_coroutine()
        self.assertEqual(x, "goodbye")
