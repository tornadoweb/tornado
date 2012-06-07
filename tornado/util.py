"""Miscellaneous utility functions."""

from __future__ import absolute_import, division, with_statement

import zlib


class ObjectDict(dict):
    """Makes a dictionary behave like an object."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


class GzipDecompressor(object):
    def __init__(self):
        # Magic parameter makes zlib module understand gzip header
        # http://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib
        self.decompressobj = zlib.decompressobj(16 + zlib.MAX_WBITS)

    def __call__(self, value):
        return self.decompressobj.decompress(value)


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


def raise_exc_info(exc_info):
    """Re-raise an exception (with original traceback) from an exc_info tuple.

    The argument is a ``(type, value, traceback)`` tuple as returned by
    `sys.exc_info`.
    """
    # 2to3 isn't smart enough to convert three-argument raise
    # statements correctly in some cases.
    if isinstance(exc_info[1], exc_info[0]):
        raise exc_info[1], None, exc_info[2]
        # After 2to3: raise exc_info[1].with_traceback(exc_info[2])
    else:
        # I think this branch is only taken for string exceptions,
        # which were removed in Python 2.6.
        raise exc_info[0], exc_info[1], exc_info[2]
        # After 2to3: raise exc_info[0](exc_info[1]).with_traceback(exc_info[2])


def doctests():
    import doctest
    return doctest.DocTestSuite()
