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

.. py:function:: wrap_asyncio_future(future)

    Wraps an ``asyncio.Future`` in a `.tornado.concurrent.Future`.

.. py:function:: wrap_tornado_future(future, *, loop=None)

    Wraps a `.tornado.concurrent.Future` in an ``asyncio.Future``.

    If ``loop`` is not supplied, an event loop will be retrieved
    using ``asyncio.get_event_loop()`` for use with the returned Future.

.. py:function:: task(func)

    Decorator for wrapping an ``asyncio`` coroutine object in a `.tornado.concurrent.Future`.

    When a function decorated by ``@platform.asyncio.task`` is called, an ``asyncio.Task``
    object running on the event loop returned by ``asyncio.get_event_loop()`` will be
    constructed and subsequently wrapped in a `.tornado.concurrent.Future` and returned.

    A function decorated with ``@platform.asyncio.task`` does not need to be explicitly
    decorated with ``@asyncio.coroutine``.

    In ``asyncio`` coroutines, ``yield from`` can be used with Tornado's `.Future`, in which
    case the `.Future` will be automatically wrapped in an ``asyncio.Future``.

    Example usage::

        class AsyncIORequestHandler(RequestHandler):
            @platform.asyncio.task
            def get(self):
                response = yield from AsyncHTTPClient().fetch("http://google.com")
                print("Got response:", response)

                proc = yield from asyncio.create_subprocess_exec(
                    'ls', '-l', stdout=asyncio.subprocess.PIPE)
                stdout, _ = yield from proc.communicate()
                self.write(stdout.replace(b'\n', b'<br>'))
