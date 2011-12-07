"""Miscellaneous utility functions."""

from logging.handlers import MemoryHandler
import json
import logging

class ObjectDict(dict):
    """Makes a dictionary behave like an object."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


class LogCaptureHandler(MemoryHandler):
    def __init__(self):
        MemoryHandler.__init__(self, capacity=0, flushLevel=100)
        self.logger = logging.getLogger()

    def __enter__(self):
        self.logger.addHandler(self)
        return self

    def __exit__(self, type, value, traceback):
        self.logger.removeHandler(self)
        self.close()

    def prettyPrintBuffer(self):
        return json.dumps([record.__dict__ for record in self.buffer], sort_keys=True, indent=4)


def import_object(name):
    """Imports an object by name.

    import_object('x.y.z') is equivalent to 'from x.y import z'.

    >>> import tornado.escape
    >>> import_object('tornado.escape') is tornado.escape
    True
    >>> import_object('tornado.escape.utf8') is tornado.escape.utf8
    True
    """
    parts = name.split('.')
    obj = __import__('.'.join(parts[:-1]), None, None, [parts[-1]], 0)
    return getattr(obj, parts[-1])

# Fake byte literal support:  In python 2.6+, you can say b"foo" to get
# a byte literal (str in 2.x, bytes in 3.x).  There's no way to do this
# in a way that supports 2.5, though, so we need a function wrapper
# to convert our string literals.  b() should only be applied to literal
# latin1 strings.  Once we drop support for 2.5, we can remove this function
# and just use byte literals.
if str is unicode:
    def b(s):
        return s.encode('latin1')
    bytes_type = bytes
else:
    def b(s):
        return s
    bytes_type = str

def doctests():
    import doctest
    return doctest.DocTestSuite()
