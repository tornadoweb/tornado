from __future__ import absolute_import, division, with_statement

from tornado.options import _Options
from tornado.test.util import unittest


class OptionsTest(unittest.TestCase):
    def setUp(self):
        self.options = _Options()
        define = self.options.define
        # these are currently required
        define("help", default=False)

        define("port", default=80)

    def test_parse_command_line(self):
        self.options.parse_command_line(["main.py", "--port=443"])
        self.assertEqual(self.options.port, 443)

    def test_parse_callbacks(self):
        self.called = False
        def callback():
            self.called = True
        self.options.add_parse_callback(callback)

        # non-final parse doesn't run callbacks
        self.options.parse_command_line(["main.py"], final=False)
        self.assertFalse(self.called)

        # final parse does
        self.options.parse_command_line(["main.py"])
        self.assertTrue(self.called)

        # callbacks can be run more than once on the same options
        # object if there are multiple final parses
        self.called = False
        self.options.parse_command_line(["main.py"])
        self.assertTrue(self.called)
