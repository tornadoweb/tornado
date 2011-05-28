"""Miscellaneous utility functions."""

import urllib

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

def url_concat(url, args):
    """
    concatenate url and args regardless of whether url has existing
    query parameters
    """
    if url.find('?') == -1:
        url = url + '?'
    elif not url.endswith('?'):
        url = "%s%s" % (
                url,
                '' if url.endswith('&') else '&',
                )
    return url + urllib.urlencode(args)

# Fake byte literal support:  In python 2.6+, you can say b"foo" to get
# a byte literal (str in 2.x, bytes in 3.x).  There's no way to do this
# in a way that supports 2.5, though, so we need a function wrapper
# to convert our string literals.  b() should only be applied to literal
# ascii strings.  Once we drop support for 2.5, we can remove this function
# and just use byte literals.
if str is unicode:
    def b(s):
        return s.encode('ascii')
    bytes_type = bytes
else:
    def b(s):
        return s
    bytes_type = str

def doctests():
    import doctest
    return doctest.DocTestSuite()
