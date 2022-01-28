``tornado.util`` --- General-purpose utilities
==============================================

.. testsetup::

   from tornado.util import *

.. automodule:: tornado.util
    :members:

    .. class:: TimeoutError

        Exception raised by `.gen.with_timeout` and `.IOLoop.run_sync`.

        .. versionchanged:: 5.0
           Unified ``tornado.gen.TimeoutError`` and
           ``tornado.ioloop.TimeoutError`` as ``tornado.util.TimeoutError``.
           Both former names remain as aliases.

        .. versionchanged:: 6.2
           ``tornado.util.TimeoutError`` is an alias to :py:class:`asyncio.TimeoutError`
