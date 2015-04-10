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

    .. testcode::

        q = queues.Queue(maxsize=2)

        @gen.coroutine
        def consumer():
            while True:
                item = yield q.get()
                try:
                    print('Doing work on %s' % item)
                    yield gen.sleep(0.01)
                finally:
                    q.task_done()

        @gen.coroutine
        def producer():
            for item in range(5):
                yield q.put(item)
                print('Put %s' % item)

        @gen.coroutine
        def main():
            consumer()           # Start consumer.
            yield producer()     # Wait for producer to put all tasks.
            yield q.join()       # Wait for consumer to finish all tasks.
            print('Done')

        io_loop.run_sync(main)

    .. testoutput::

        Put 0
        Put 1
        Put 2
        Doing work on 0
        Doing work on 1
        Put 3
        Doing work on 2
        Put 4
        Doing work on 3
        Doing work on 4
        Done


   PriorityQueue
   ^^^^^^^^^^^^^

    .. testcode::

        q = queues.PriorityQueue()
        q.put((1, 'medium-priority item'))
        q.put((0, 'high-priority item'))
        q.put((10, 'low-priority item'))

        print(q.get_nowait())
        print(q.get_nowait())
        print(q.get_nowait())

    .. testoutput::

        (0, 'high-priority item')
        (1, 'medium-priority item')
        (10, 'low-priority item')

   LifoQueue
   ^^^^^^^^^

    .. testcode::

        q = queues.LifoQueue()
        q.put(3)
        q.put(2)
        q.put(1)

        print(q.get_nowait())
        print(q.get_nowait())
        print(q.get_nowait())

    .. testoutput::

        1
        2
        3

   Exceptions
   ----------

   QueueEmpty
   ^^^^^^^^^^
   .. autoexception:: QueueEmpty

   QueueFull
   ^^^^^^^^^
   .. autoexception:: QueueFull
