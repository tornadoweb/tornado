from __future__ import absolute_import, division, with_statement
import unittest

from tornado.options import _Options


class OptionsTest(unittest.TestCase):
    def setUp(self):
        self.options = _Options()
        define = self.options.define
        # these are currently required
        define("logging", default="none")
        define("help", default=False)

        define("port", default=80)

    def test_parse_command_line(self):
        self.options.parse_command_line(["main.py", "--port=443"])
        self.assertEqual(self.options.port, 443)
