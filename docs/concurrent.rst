``tornado.concurrent`` --- Work with threads and futures
========================================================

.. automodule:: tornado.concurrent
    :members:

    .. py:class:: Future

        A ``Future`` encapsulates the result of an asynchronous
        operation.  In synchronous applications ``Futures`` are used
        to wait for the result from a thread or process pool; in
        Tornado they are normally used with `.IOLoop.add_future` or by
        yielding them in a `.gen.coroutine`.

        If the `concurrent.futures` package is available,
        `tornado.concurrent.Future` is simply an alias for
        `concurrent.futures.Future`.  Otherwise, we support the same
        interface with a few limitations:

        * It is an error to call `result` or `exception` before the
          ``Future`` has completed.
        * Cancellation is not supported.

        .. py:method:: result()

            If the operation succeeded, return its result.  If it failed,
            re-raise its exception.

        .. py:method:: exception()

            If the operation raised an exception, return the `Exception`
            object.  Otherwise returns None.

        .. py:method:: add_done_callback(fn)

            Attaches the given callback to the `Future`.  It will be invoked
            with the `Future` as its argument when it has finished running
            and its result is available.  In Tornado consider using
            `.IOLoop.add_future` instead of calling `add_done_callback`
            directly.

        .. py:method:: done()

            Returns True if the future has finished running and its
            `result` and `exception` methods are available.
