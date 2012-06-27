from __future__ import absolute_import, division, with_statement
import logging
import os
import re
import tempfile
import unittest

from tornado.escape import utf8
from tornado.options import _Options, _LogFormatter
from tornado.util import b, bytes_type


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


class LogFormatterTest(unittest.TestCase):
    LINE_RE = re.compile(b("\x01\\[E [0-9]{6} [0-9]{2}:[0-9]{2}:[0-9]{2} options_test:[0-9]+\\]\x02 (.*)"))

    def setUp(self):
        self.formatter = _LogFormatter(color=False)
        # Fake color support.  We can't guarantee anything about the $TERM
        # variable when the tests are run, so just patch in some values
        # for testing.  (testing with color off fails to expose some potential
        # encoding issues from the control characters)
        self.formatter._colors = {
            logging.ERROR: u"\u0001",
            }
        self.formatter._normal = u"\u0002"
        self.formatter._color = True
        # construct a Logger directly to bypass getLogger's caching
        self.logger = logging.Logger('LogFormatterTest')
        self.logger.propagate = False
        self.tempdir = tempfile.mkdtemp()
        self.filename = os.path.join(self.tempdir, 'log.out')
        self.handler = self.make_handler(self.filename)
        self.handler.setFormatter(self.formatter)
        self.logger.addHandler(self.handler)

    def tearDown(self):
        os.unlink(self.filename)
        os.rmdir(self.tempdir)

    def make_handler(self, filename):
        # Base case: default setup without explicit encoding.
        # In python 2, supports arbitrary byte strings and unicode objects
        # that contain only ascii.  In python 3, supports ascii-only unicode
        # strings (but byte strings will be repr'd automatically.
        return logging.FileHandler(filename)

    def get_output(self):
        with open(self.filename, "rb") as f:
            line = f.read().strip()
            m = LogFormatterTest.LINE_RE.match(line)
            if m:
                return m.group(1)
            else:
                raise Exception("output didn't match regex: %r" % line)

    def test_basic_logging(self):
        self.logger.error("foo")
        self.assertEqual(self.get_output(), b("foo"))

    def test_bytes_logging(self):
        self.logger.error(b("\xe9"))
        # This will be "\xe9" on python 2 or "b'\xe9'" on python 3
        self.assertEqual(self.get_output(), utf8(repr(b("\xe9"))))

    def test_utf8_logging(self):
        self.logger.error(u"\u00e9".encode("utf8"))
        if issubclass(bytes_type, basestring):
            # on python 2, utf8 byte strings (and by extension ascii byte
            # strings) are passed through as-is.
            self.assertEqual(self.get_output(), utf8(u"\u00e9"))
        else:
            # on python 3, byte strings always get repr'd even if
            # they're ascii-only, so this degenerates into another
            # copy of test_bytes_logging.
            self.assertEqual(self.get_output(), utf8(repr(utf8(u"\u00e9"))))


class UnicodeLogFormatterTest(LogFormatterTest):
    def make_handler(self, filename):
        # Adding an explicit encoding configuration allows non-ascii unicode
        # strings in both python 2 and 3, without changing the behavior
        # for byte strings.
        return logging.FileHandler(filename, encoding="utf8")

    def test_unicode_logging(self):
        self.logger.error(u"\u00e9")
        self.assertEqual(self.get_output(), utf8(u"\u00e9"))
