``tornado.concurrent`` --- Work with threads and futures
========================================================

.. testsetup::

   from tornado.concurrent import *
   from tornado import gen

.. automodule:: tornado.concurrent
    :members:
    :exclude-members: Future, TracebackFuture

    .. autoclass:: Future

    Consumer methods
    ^^^^^^^^^^^^^^^^

    .. automethod:: Future.result
    .. automethod:: Future.exception
    .. automethod:: Future.exc_info
    .. automethod:: Future.add_done_callback
    .. automethod:: Future.done
    .. automethod:: Future.running
    .. automethod:: Future.cancel
    .. automethod:: Future.cancelled

    Producer methods
    ^^^^^^^^^^^^^^^^

    .. automethod:: Future.set_result
    .. automethod:: Future.set_exception
    .. automethod:: Future.set_exc_info
