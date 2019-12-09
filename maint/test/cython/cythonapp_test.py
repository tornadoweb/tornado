from tornado.testing import AsyncTestCase, gen_test
from tornado.util import ArgReplacer
import unittest

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


class CythonArgReplacerTest(unittest.TestCase):
    def test_arg_replacer_function(self):
        replacer = ArgReplacer(cythonapp.function_with_args, 'two')
        args = (1, 'old', 3)
        kwargs = {}
        self.assertEqual(replacer.get_old_value(args, kwargs), 'old')
        self.assertEqual(replacer.replace('new', args, kwargs),
                         ('old', [1, 'new', 3], {}))

    def test_arg_replacer_method(self):
        replacer = ArgReplacer(cythonapp.AClass().method_with_args, 'two')
        args = (1, 'old', 3)
        kwargs = {}
        self.assertEqual(replacer.get_old_value(args, kwargs), 'old')
        self.assertEqual(replacer.replace('new', args, kwargs),
                         ('old', [1, 'new', 3], {}))
