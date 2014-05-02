``tornado.platform.asyncio`` --- Bridge between ``asyncio`` and Tornado
=======================================================================

.. versionadded:: 3.2

.. automodule:: tornado.platform.asyncio

IOLoops
-------

.. autoclass:: BaseAsyncIOLoop

.. automethod:: BaseAsyncIOLoop.get_asyncio_loop

.. autoclass:: AsyncIOMainLoop

.. autoclass:: AsyncIOLoop

Future-related convenience functions
------------------------------------

.. autofunction:: wrap_asyncio_future
.. autofunction:: wrap_tornado_future
.. autofunction:: task
