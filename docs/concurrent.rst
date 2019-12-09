``tornado.concurrent`` --- Work with ``Future`` objects
=======================================================

.. testsetup::

   from tornado.concurrent import *
   from tornado import gen

.. automodule:: tornado.concurrent
    :members:

     .. class:: Future

        ``tornado.concurrent.Future`` is an alias for `asyncio.Future`.

        In Tornado, the main way in which applications interact with
        ``Future`` objects is by ``awaiting`` or ``yielding`` them in
        coroutines, instead of calling methods on the ``Future`` objects
        themselves. For more information on the available methods, see
        the `asyncio.Future` docs.

        .. versionchanged:: 5.0

           Tornado's implementation of ``Future`` has been replaced by
           the version from `asyncio` when available.

           - ``Future`` objects can only be created while there is a
             current `.IOLoop`
           - The timing of callbacks scheduled with
             ``Future.add_done_callback`` has changed.
           - Cancellation is now partially supported (only on Python 3)
           - The ``exc_info`` and ``set_exc_info`` methods are no longer
             available on Python 3.
