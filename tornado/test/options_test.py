from __future__ import absolute_import, division, print_function, with_statement

import os
import sys

from tornado.options import OptionParser, Error
from tornado.test.util import unittest

try:
    from cStringIO import StringIO  # python 2
except ImportError:
    from io import StringIO  # python 3

try:
    from unittest import mock  # python 3.3
except ImportError:
    try:
        import mock  # third-party mock package
    except ImportError:
        mock = None


class OptionsTest(unittest.TestCase):
    def test_parse_command_line(self):
        options = OptionParser()
        options.define("port", default=80)
        options.parse_command_line(["main.py", "--port=443"])
        self.assertEqual(options.port, 443)

    def test_parse_config_file(self):
        options = OptionParser()
        options.define("port", default=80)
        options.parse_config_file(os.path.join(os.path.dirname(__file__),
                                               "options_test.cfg"))
        self.assertEquals(options.port, 443)

    def test_parse_callbacks(self):
        options = OptionParser()
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
        options = OptionParser()
        try:
            orig_stderr = sys.stderr
            sys.stderr = StringIO()
            with self.assertRaises(SystemExit):
                options.parse_command_line(["main.py", "--help"])
            usage = sys.stderr.getvalue()
        finally:
            sys.stderr = orig_stderr
        self.assertIn("Usage:", usage)

    def test_subcommand(self):
        base_options = OptionParser()
        base_options.define("verbose", default=False)
        sub_options = OptionParser()
        sub_options.define("foo", type=str)
        rest = base_options.parse_command_line(
            ["main.py", "--verbose", "subcommand", "--foo=bar"])
        self.assertEqual(rest, ["subcommand", "--foo=bar"])
        self.assertTrue(base_options.verbose)
        rest2 = sub_options.parse_command_line(rest)
        self.assertEqual(rest2, [])
        self.assertEqual(sub_options.foo, "bar")

        # the two option sets are distinct
        try:
            orig_stderr = sys.stderr
            sys.stderr = StringIO()
            with self.assertRaises(Error):
                sub_options.parse_command_line(["subcommand", "--verbose"])
        finally:
            sys.stderr = orig_stderr

    def test_setattr(self):
        options = OptionParser()
        options.define('foo', default=1, type=int)
        options.foo = 2
        self.assertEqual(options.foo, 2)

    def test_setattr_type_check(self):
        # setattr requires that options be the right type and doesn't
        # parse from string formats.
        options = OptionParser()
        options.define('foo', default=1, type=int)
        with self.assertRaises(Error):
            options.foo = '2'

    def test_setattr_with_callback(self):
        values = []
        options = OptionParser()
        options.define('foo', default=1, type=int, callback=values.append)
        options.foo = 2
        self.assertEqual(values, [2])

    @unittest.skipIf(mock is None, 'mock package not present')
    def test_mock_patch(self):
        # ensure that our setattr hooks don't interfere with mock.patch
        options = OptionParser()
        options.define('foo', default=1)
        options.parse_command_line(['main.py', '--foo=2'])
        self.assertEqual(options.foo, 2)

        with mock.patch.object(options.mockable(), 'foo', 3):
            self.assertEqual(options.foo, 3)
        self.assertEqual(options.foo, 2)

        # Try nested patches mixed with explicit sets
        with mock.patch.object(options.mockable(), 'foo', 4):
            self.assertEqual(options.foo, 4)
            options.foo = 5
            self.assertEqual(options.foo, 5)
            with mock.patch.object(options.mockable(), 'foo', 6):
                self.assertEqual(options.foo, 6)
            self.assertEqual(options.foo, 5)
        self.assertEqual(options.foo, 2)
