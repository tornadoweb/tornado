"""Miscellaneous utility functions and classes.

This module is used internally by Tornado.  It is not necessarily expected
that the functions and classes defined here will be useful to other
applications, but they are documented here in case they are.

The one public-facing part of this module is the `Configurable` class
and its `~Configurable.configure` method, which becomes a part of the
interface of its subclasses, including `.AsyncHTTPClient`, `.IOLoop`,
and `.Resolver`.
"""

from __future__ import absolute_import, division, print_function

import array
import atexit
import os
import re
import sys
import zlib

PY3 = sys.version_info >= (3,)

if PY3:
    xrange = range

# inspect.getargspec() raises DeprecationWarnings in Python 3.5.
# The two functions have compatible interfaces for the parts we need.
if PY3:
    from inspect import getfullargspec as getargspec
else:
    from inspect import getargspec

# Aliases for types that are spelled differently in different Python
# versions. bytes_type is deprecated and no longer used in Tornado
# itself but is left in case anyone outside Tornado is using it.
bytes_type = bytes
if PY3:
    unicode_type = str
    basestring_type = str
else:
    # The names unicode and basestring don't exist in py3 so silence flake8.
    unicode_type = unicode  # noqa
    basestring_type = basestring  # noqa


try:
    import typing  # noqa
    from typing import cast

    _ObjectDictBase = typing.Dict[str, typing.Any]
except ImportError:
    _ObjectDictBase = dict

    def cast(typ, x):
        return x
else:
    # More imports that are only needed in type comments.
    import datetime  # noqa
    import types  # noqa
    from typing import Any, AnyStr, Union, Optional, Dict, Mapping  # noqa
    from typing import Tuple, Match, Callable  # noqa

    if PY3:
        _BaseString = str
    else:
        _BaseString = Union[bytes, unicode_type]


try:
    from sys import is_finalizing
except ImportError:
    # Emulate it
    def _get_emulated_is_finalizing():
        L = []
        atexit.register(lambda: L.append(None))

        def is_finalizing():
            # Not referencing any globals here
            return L != []

        return is_finalizing

    is_finalizing = _get_emulated_is_finalizing()


class ObjectDict(_ObjectDictBase):
    """Makes a dictionary behave like an object, with attribute-style access.
    """
    def __getattr__(self, name):
        # type: (str) -> Any
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        # type: (str, Any) -> None
        self[name] = value


class GzipDecompressor(object):
    """Streaming gzip decompressor.

    The interface is like that of `zlib.decompressobj` (without some of the
    optional arguments, but it understands gzip headers and checksums.
    """
    def __init__(self):
        # Magic parameter makes zlib module understand gzip header
        # http://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib
        # This works on cpython and pypy, but not jython.
        self.decompressobj = zlib.decompressobj(16 + zlib.MAX_WBITS)

    def decompress(self, value, max_length=None):
        # type: (bytes, Optional[int]) -> bytes
        """Decompress a chunk, returning newly-available data.

        Some data may be buffered for later processing; `flush` must
        be called when there is no more input data to ensure that
        all data was processed.

        If ``max_length`` is given, some input data may be left over
        in ``unconsumed_tail``; you must retrieve this value and pass
        it back to a future call to `decompress` if it is not empty.
        """
        return self.decompressobj.decompress(value, max_length)

    @property
    def unconsumed_tail(self):
        # type: () -> bytes
        """Returns the unconsumed portion left over
        """
        return self.decompressobj.unconsumed_tail

    def flush(self):
        # type: () -> bytes
        """Return any remaining buffered data not yet returned by decompress.

        Also checks for errors such as truncated input.
        No other methods may be called on this object after `flush`.
        """
        return self.decompressobj.flush()


def import_object(name):
    # type: (_BaseString) -> Any
    """Imports an object by name.

    import_object('x') is equivalent to 'import x'.
    import_object('x.y.z') is equivalent to 'from x.y import z'.

    >>> import tornado.escape
    >>> import_object('tornado.escape') is tornado.escape
    True
    >>> import_object('tornado.escape.utf8') is tornado.escape.utf8
    True
    >>> import_object('tornado') is tornado
    True
    >>> import_object('tornado.missing_module')
    Traceback (most recent call last):
        ...
    ImportError: No module named missing_module
    """
    if not isinstance(name, str):
        # on python 2 a byte string is required.
        name = name.encode('utf-8')
    if name.count('.') == 0:
        return __import__(name, None, None)

    parts = name.split('.')
    obj = __import__('.'.join(parts[:-1]), None, None, [parts[-1]], 0)
    try:
        return getattr(obj, parts[-1])
    except AttributeError:
        raise ImportError("No module named %s" % parts[-1])


# Stubs to make mypy happy (and later for actual type-checking).
def raise_exc_info(exc_info):
    # type: (Tuple[type, BaseException, types.TracebackType]) -> None
    pass


def exec_in(code, glob, loc=None):
    # type: (Any, Dict[str, Any], Optional[Mapping[str, Any]]) -> Any
    if isinstance(code, basestring_type):
        # exec(string) inherits the caller's future imports; compile
        # the string first to prevent that.
        code = compile(code, '<string>', 'exec', dont_inherit=True)
    exec(code, glob, loc)


if PY3:
    exec("""
def raise_exc_info(exc_info):
    try:
        raise exc_info[1].with_traceback(exc_info[2])
    finally:
        exc_info = None

""")
else:
    exec("""
def raise_exc_info(exc_info):
    raise exc_info[0], exc_info[1], exc_info[2]
""")


def errno_from_exception(e):
    # type: (BaseException) -> Optional[int]
    """Provides the errno from an Exception object.

    There are cases that the errno attribute was not set so we pull
    the errno out of the args but if someone instantiates an Exception
    without any args you will get a tuple error. So this function
    abstracts all that behavior to give you a safe way to get the
    errno.
    """

    if hasattr(e, 'errno'):
        return e.errno  # type: ignore
    elif e.args:
        return e.args[0]
    else:
        return None


_alphanum = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _re_unescape_replacement(match):
    # type: (Match[str]) -> str
    group = match.group(1)
    if group[0] in _alphanum:
        raise ValueError("cannot unescape '\\\\%s'" % group[0])
    return group


_re_unescape_pattern = re.compile(r'\\(.)', re.DOTALL)


def re_unescape(s):
    # type: (str) -> str
    """Unescape a string escaped by `re.escape`.

    May raise ``ValueError`` for regular expressions which could not
    have been produced by `re.escape` (for example, strings containing
    ``\d`` cannot be unescaped).

    .. versionadded:: 4.4
    """
    return _re_unescape_pattern.sub(_re_unescape_replacement, s)


class Configurable(object):
    """Base class for configurable interfaces.

    A configurable interface is an (abstract) class whose constructor
    acts as a factory function for one of its implementation subclasses.
    The implementation subclass as well as optional keyword arguments to
    its initializer can be set globally at runtime with `configure`.

    By using the constructor as the factory method, the interface
    looks like a normal class, `isinstance` works as usual, etc.  This
    pattern is most useful when the choice of implementation is likely
    to be a global decision (e.g. when `~select.epoll` is available,
    always use it instead of `~select.select`), or when a
    previously-monolithic class has been split into specialized
    subclasses.

    Configurable subclasses must define the class methods
    `configurable_base` and `configurable_default`, and use the instance
    method `initialize` instead of ``__init__``.
    """
    __impl_class = None  # type: type
    __impl_kwargs = None  # type: Dict[str, Any]

    def __new__(cls, *args, **kwargs):
        base = cls.configurable_base()
        init_kwargs = {}
        if cls is base:
            impl = cls.configured_class()
            if base.__impl_kwargs:
                init_kwargs.update(base.__impl_kwargs)
        else:
            impl = cls
        init_kwargs.update(kwargs)
        instance = super(Configurable, cls).__new__(impl)
        # initialize vs __init__ chosen for compatibility with AsyncHTTPClient
        # singleton magic.  If we get rid of that we can switch to __init__
        # here too.
        instance.initialize(*args, **init_kwargs)
        return instance

    @classmethod
    def configurable_base(cls):
        # type: () -> Any
        # TODO: This class needs https://github.com/python/typing/issues/107
        # to be fully typeable.
        """Returns the base class of a configurable hierarchy.

        This will normally return the class in which it is defined.
        (which is *not* necessarily the same as the cls classmethod parameter).
        """
        raise NotImplementedError()

    @classmethod
    def configurable_default(cls):
        # type: () -> type
        """Returns the implementation class to be used if none is configured."""
        raise NotImplementedError()

    def initialize(self):
        # type: () -> None
        """Initialize a `Configurable` subclass instance.

        Configurable classes should use `initialize` instead of ``__init__``.

        .. versionchanged:: 4.2
           Now accepts positional arguments in addition to keyword arguments.
        """

    @classmethod
    def configure(cls, impl, **kwargs):
        # type: (Any, **Any) -> None
        """Sets the class to use when the base class is instantiated.

        Keyword arguments will be saved and added to the arguments passed
        to the constructor.  This can be used to set global defaults for
        some parameters.
        """
        base = cls.configurable_base()
        if isinstance(impl, (str, unicode_type)):
            impl = import_object(impl)
        if impl is not None and not issubclass(impl, cls):
            raise ValueError("Invalid subclass of %s" % cls)
        base.__impl_class = impl
        base.__impl_kwargs = kwargs

    @classmethod
    def configured_class(cls):
        # type: () -> type
        """Returns the currently configured class."""
        base = cls.configurable_base()
        if cls.__impl_class is None:
            base.__impl_class = cls.configurable_default()
        return base.__impl_class

    @classmethod
    def _save_configuration(cls):
        # type: () -> Tuple[type, Dict[str, Any]]
        base = cls.configurable_base()
        return (base.__impl_class, base.__impl_kwargs)

    @classmethod
    def _restore_configuration(cls, saved):
        # type: (Tuple[type, Dict[str, Any]]) -> None
        base = cls.configurable_base()
        base.__impl_class = saved[0]
        base.__impl_kwargs = saved[1]


class ArgReplacer(object):
    """Replaces one value in an ``args, kwargs`` pair.

    Inspects the function signature to find an argument by name
    whether it is passed by position or keyword.  For use in decorators
    and similar wrappers.
    """
    def __init__(self, func, name):
        # type: (Callable, str) -> None
        self.name = name
        try:
            self.arg_pos = self._getargnames(func).index(name)
        except ValueError:
            # Not a positional parameter
            self.arg_pos = None

    def _getargnames(self, func):
        # type: (Callable) -> List[str]
        try:
            return getargspec(func).args
        except TypeError:
            if hasattr(func, 'func_code'):
                # Cython-generated code has all the attributes needed
                # by inspect.getargspec, but the inspect module only
                # works with ordinary functions. Inline the portion of
                # getargspec that we need here. Note that for static
                # functions the @cython.binding(True) decorator must
                # be used (for methods it works out of the box).
                code = func.func_code  # type: ignore
                return code.co_varnames[:code.co_argcount]
            raise

    def get_old_value(self, args, kwargs, default=None):
        # type: (List[Any], Dict[str, Any], Any) -> Any
        """Returns the old value of the named argument without replacing it.

        Returns ``default`` if the argument is not present.
        """
        if self.arg_pos is not None and len(args) > self.arg_pos:
            return args[self.arg_pos]
        else:
            return kwargs.get(self.name, default)

    def replace(self, new_value, args, kwargs):
        # type: (Any, List[Any], Dict[str, Any]) -> Tuple[Any, List[Any], Dict[str, Any]]
        """Replace the named argument in ``args, kwargs`` with ``new_value``.

        Returns ``(old_value, args, kwargs)``.  The returned ``args`` and
        ``kwargs`` objects may not be the same as the input objects, or
        the input objects may be mutated.

        If the named argument was not found, ``new_value`` will be added
        to ``kwargs`` and None will be returned as ``old_value``.
        """
        if self.arg_pos is not None and len(args) > self.arg_pos:
            # The arg to replace is passed positionally
            old_value = args[self.arg_pos]
            args = list(args)  # *args is normally a tuple
            args[self.arg_pos] = new_value
        else:
            # The arg to replace is either omitted or passed by keyword.
            old_value = kwargs.get(self.name)
            kwargs[self.name] = new_value
        return old_value, args, kwargs


def timedelta_to_seconds(td):
    # type: (datetime.timedelta) -> float
    """Equivalent to td.total_seconds() (introduced in python 2.7)."""
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / float(10 ** 6)


def _websocket_mask_python(mask, data):
    # type: (bytes, bytes) -> bytes
    """Websocket masking function.

    `mask` is a `bytes` object of length 4; `data` is a `bytes` object of any length.
    Returns a `bytes` object of the same length as `data` with the mask applied
    as specified in section 5.3 of RFC 6455.

    This pure-python implementation may be replaced by an optimized version when available.
    """
    mask_arr = array.array("B", mask)
    unmasked_arr = array.array("B", data)
    for i in xrange(len(data)):
        unmasked_arr[i] = unmasked_arr[i] ^ mask_arr[i % 4]
    if PY3:
        # tostring was deprecated in py32.  It hasn't been removed,
        # but since we turn on deprecation warnings in our tests
        # we need to use the right one.
        return unmasked_arr.tobytes()
    else:
        return unmasked_arr.tostring()


if (os.environ.get('TORNADO_NO_EXTENSION') or
        os.environ.get('TORNADO_EXTENSION') == '0'):
    # These environment variables exist to make it easier to do performance
    # comparisons; they are not guaranteed to remain supported in the future.
    _websocket_mask = _websocket_mask_python
else:
    try:
        from tornado.speedups import websocket_mask as _websocket_mask
    except ImportError:
        if os.environ.get('TORNADO_EXTENSION') == '1':
            raise
        _websocket_mask = _websocket_mask_python


def doctests():
    import doctest
    return doctest.DocTestSuite()
