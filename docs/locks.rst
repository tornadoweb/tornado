``tornado.locks`` -- Synchronization primitives
===============================================

.. versionadded:: 4.2

Coordinate coroutines with synchronization primitives analogous to those the
standard library provides to threads.

*(Note that these primitives are not actually thread-safe and cannot be used in
place of those from the standard library--they are meant to coordinate Tornado
coroutines in a single-threaded app, not to protect shared objects in a
multithreaded app.)*

.. testsetup:: *

    from tornado import ioloop, gen, locks
    io_loop = ioloop.IOLoop.current()

.. automodule:: tornado.locks

   Condition
   ---------
   .. autoclass:: Condition
    :members:

    With a `Condition`, coroutines can wait to be notified by other coroutines:

    .. testcode::

        condition = locks.Condition()

        @gen.coroutine
        def waiter():
            print("I'll wait right here")
            yield condition.wait()  # Yield a Future.
            print("I'm done waiting")

        @gen.coroutine
        def notifier():
            print("About to notify")
            condition.notify()
            print("Done notifying")

        @gen.coroutine
        def runner():
            # Yield two Futures; wait for waiter() and notifier() to finish.
            yield [waiter(), notifier()]

        io_loop.run_sync(runner)

    .. testoutput::

        I'll wait right here
        About to notify
        Done notifying
        I'm done waiting

    `wait` takes an optional ``timeout`` argument, which is either an absolute
    timestamp::

        io_loop = ioloop.IOLoop.current()

        # Wait up to 1 second for a notification.
        yield condition.wait(deadline=io_loop.time() + 1)

    ...or a `datetime.timedelta` for a deadline relative to the current time::

        # Wait up to 1 second.
        yield condition.wait(deadline=datetime.timedelta(seconds=1))

    The method raises `tornado.gen.TimeoutError` if there's no notification
    before the deadline.

   Event
   -----
   .. autoclass:: Event
    :members:

    A coroutine can wait for an event to be set. Once it is set, calls to
    ``yield event.wait()`` will not block unless the event has been cleared:

    .. testcode::

        event = locks.Event()

        @gen.coroutine
        def waiter():
            print("Waiting for event")
            yield event.wait()
            print("Not waiting this time")
            yield event.wait()
            print("Done")

        @gen.coroutine
        def setter():
            print("About to set the event")
            event.set()

        @gen.coroutine
        def runner():
            yield [waiter(), setter()]

        io_loop.run_sync(runner)

    .. testoutput::

        Waiting for event
        About to set the event
        Not waiting this time
        Done

   Semaphore
   ---------
   .. autoclass:: Semaphore
    :members:

    Semaphores limit access to a shared resource. To allow access for two
    workers at a time:

    .. testsetup:: semaphore

       from tornado import gen

       # Ensure reliable doctest output.
       waits = [0.1, 0.2, 0.1]

       @gen.coroutine
       def use_some_resource():
           yield gen.sleep(waits.pop())

    .. testcode:: semaphore

        sem = locks.Semaphore(2)

        @gen.coroutine
        def worker(worker_id):
            yield sem.acquire()
            try:
                print("Worker %d is working" % worker_id)
                yield use_some_resource()
            finally:
                print("Worker %d is done" % worker_id)
                sem.release()

        @gen.coroutine
        def runner():
            # Join all workers.
            yield [worker(i) for i in range(3)]

        io_loop.run_sync(runner)

    .. testoutput:: semaphore

        Worker 0 is working
        Worker 1 is working
        Worker 0 is done
        Worker 2 is working
        Worker 1 is done
        Worker 2 is done

    Workers 0 and 1 are allowed to run concurrently, but worker 2 waits until
    the semaphore has been released once, by worker 0.

    `.acquire` is a context manager, so ``worker`` could be written as::

        @gen.coroutine
        def worker(worker_id):
            with (yield sem.acquire()):
                print("Worker %d is working" % worker_id)
                yield use_some_resource()

            # Now the semaphore has been released.
            print("Worker %d is done" % worker_id)

   BoundedSemaphore
   ----------------
   .. autoclass:: BoundedSemaphore
    :members:
    :inherited-members:
