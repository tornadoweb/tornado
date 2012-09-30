from __future__ import absolute_import, division, with_statement

import sys

from tornado.options import _Options
from tornado.test.util import unittest

try:
    from cStringIO import StringIO  # python 2
except ImportError:
    from io import StringIO  # python 3

class OptionsTest(unittest.TestCase):
    def test_parse_command_line(self):
        options = _Options()
        options.define("port", default=80)
        options.parse_command_line(["main.py", "--port=443"])
        self.assertEqual(options.port, 443)

    def test_parse_callbacks(self):
        options = _Options()
        self.called = False
        def callback():
            self.called = True
        options.add_parse_callback(callback)

        # non-final parse doesn't run callbacks
        options.parse_command_line(["main.py"], final=False)
        self.assertFalse(self.called)

        # final parse does
        options.parse_command_line(["main.py"])
        self.assertTrue(self.called)

        # callbacks can be run more than once on the same options
        # object if there are multiple final parses
        self.called = False
        options.parse_command_line(["main.py"])
        self.assertTrue(self.called)

    def test_help(self):
        options = _Options()
        try:
            orig_stderr = sys.stderr
            sys.stderr = StringIO()
            with self.assertRaises(SystemExit):
                options.parse_command_line(["main.py", "--help"])
            usage = sys.stderr.getvalue()
        finally:
            sys.stderr = orig_stderr
        self.assertIn("Usage:", usage)
