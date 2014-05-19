``tornado.platform.asyncio`` --- Bridge between ``asyncio`` and Tornado
=======================================================================

.. versionadded:: 3.2

.. module:: tornado.platform.asyncio

This module integrates Tornado with the ``asyncio`` module introduced
in Python 3.4 (and available `as a separate download
<https://pypi.python.org/pypi/asyncio>`_ for Python 3.3).  This makes
it possible to combine the two libraries on the same event loop.

Most applications should use `AsyncIOMainLoop` to run Tornado on the
default ``asyncio`` event loop.  Applications that need to run event
loops on multiple threads may use `AsyncIOLoop` to create multiple
loops.

This is a work in progress and interfaces are subject to change.

IOLoops
-------

.. py:class:: BaseAsyncIOLoop

    Serves as a base for `.AsyncIOMainLoop` and `.AsyncIOLoop`.

.. py:method:: BaseAsyncIOLoop.get_asyncio_loop

    Returns the ``asyncio`` event loop used for this `.BaseAsyncIOLoop` object.

.. py:class:: AsyncIOMainLoop

    ``AsyncIOMainLoop`` creates an `.IOLoop` that corresponds to the
    current ``asyncio`` event loop (i.e. the one returned by
    ``asyncio.get_event_loop()``).

    Recommended usage::

        from tornado.platform.asyncio import AsyncIOMainLoop
        import asyncio
        AsyncIOMainLoop().install()
        asyncio.get_event_loop().run_forever()

.. py:class:: AsyncIOLoop

    ``AsyncIOLoop`` is an `.IOLoop` that runs on an ``asyncio`` event loop.

    This class follows the usual Tornado semantics for creating new
    ``IOLoops``; these loops are not necessarily related to the
    ``asyncio`` default event loop.  Recommended usage::

        from tornado.ioloop import IOLoop
        IOLoop.configure('tornado.platform.asyncio.AsyncIOLoop')
        IOLoop.instance().start()

Future-related convenience functions
------------------------------------

.. py:function:: wrap_tornado_future(future, *, loop=None)

    Wraps a `.tornado.concurrent.Future` in an ``asyncio.Future``.

    If ``loop`` is not supplied, an event loop will be retrieved
    using ``asyncio.get_event_loop()`` for use with the returned Future.
