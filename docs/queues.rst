``tornado.queues`` -- Queues for coroutines
===========================================

.. versionadded:: 4.2

.. testsetup::

    from tornado import ioloop, gen, queues
    io_loop = ioloop.IOLoop.current()

.. automodule:: tornado.queues

   Classes
   -------

   Queue
   ^^^^^
   .. autoclass:: Queue
    :members:

   PriorityQueue
   ^^^^^^^^^^^^^
   .. autoclass:: PriorityQueue
    :members:

   LifoQueue
   ^^^^^^^^^
   .. autoclass:: LifoQueue
    :members:

   Exceptions
   ----------

   QueueEmpty
   ^^^^^^^^^^
   .. autoexception:: QueueEmpty

   QueueFull
   ^^^^^^^^^
   .. autoexception:: QueueFull
