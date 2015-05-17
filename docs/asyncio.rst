``tornado.platform.asyncio`` --- Bridge between ``asyncio`` and Tornado
=======================================================================

.. module:: tornado.platform.asyncio

.. versionadded:: 3.2

This module integrates Tornado with the ``asyncio`` module introduced
in Python 3.4 (and available `as a separate download
<https://pypi.python.org/pypi/asyncio>`_ for Python 3.3).  This makes
it possible to combine the two libraries on the same event loop.

Most applications should use `AsyncIOMainLoop` to run Tornado on the
default ``asyncio`` event loop.  Applications that need to run event
loops on multiple threads may use `AsyncIOLoop` to create multiple
loops.

.. note::

   Tornado requires the `~asyncio.BaseEventLoop.add_reader` family of methods,
   so it is not compatible with the `~asyncio.ProactorEventLoop` on Windows.
   Use the `~asyncio.SelectorEventLoop` instead.

.. py:class:: AsyncIOMainLoop

    ``AsyncIOMainLoop`` creates an `.IOLoop` that corresponds to the
    current ``asyncio`` event loop (i.e. the one returned by
    ``asyncio.get_event_loop()``).  Recommended usage::

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
        IOLoop.current().start()

    Each ``AsyncIOLoop`` creates a new ``asyncio.EventLoop``; this object
    can be accessed with the ``asyncio_loop`` attribute.

.. py:function:: to_tornado_future

   Convert an ``asyncio.Future`` to a `tornado.concurrent.Future`.

   .. versionadded:: 4.1

.. py:function:: to_asyncio_future

   Convert a `tornado.concurrent.Future` to an ``asyncio.Future``.

   .. versionadded:: 4.1
