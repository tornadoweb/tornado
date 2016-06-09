Coroutines
==========

.. testsetup::

   from tornado import gen

**Coroutines** are the recommended way to write asynchronous code in
Tornado.  Coroutines use the Python ``yield`` keyword to suspend and
resume execution instead of a chain of callbacks (cooperative
lightweight threads as seen in frameworks like `gevent
<http://www.gevent.org>`_ are sometimes called coroutines as well, but
in Tornado all coroutines use explicit context switches and are called
as asynchronous functions).

Coroutines are almost as simple as synchronous code, but without the
expense of a thread.  They also `make concurrency easier
<https://glyph.twistedmatrix.com/2014/02/unyielding.html>`_ to reason
about by reducing the number of places where a context switch can
happen.

Example::

    from tornado import gen

    @gen.coroutine
    def fetch_coroutine(url):
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch(url)
        # In Python versions prior to 3.3, returning a value from
        # a generator is not allowed and you must use
        #   raise gen.Return(response.body)
        # instead.
        return response.body

.. _native_coroutines:

Python 3.5: ``async`` and ``await``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python 3.5 introduces the ``async`` and ``await`` keywords (functions
using these keywords are also called "native coroutines"). Starting in
Tornado 4.3, you can use them in place of ``yield``-based coroutines.
Simply use ``async def foo()`` in place of a function definition with
the ``@gen.coroutine`` decorator, and ``await`` in place of yield. The
rest of this document still uses the ``yield`` style for compatibility
with older versions of Python, but ``async`` and ``await`` will run
faster when they are available::

    async def fetch_coroutine(url):
        http_client = AsyncHTTPClient()
        response = await http_client.fetch(url)
        return response.body

The ``await`` keyword is less versatile than the ``yield`` keyword.
For example, in a ``yield``-based coroutine you can yield a list of
``Futures``, while in a native coroutine you must wrap the list in
`tornado.gen.multi`. You can also use `tornado.gen.convert_yielded`
to convert anything that would work with ``yield`` into a form that
will work with ``await``.

While native coroutines are not visibly tied to a particular framework
(i.e. they do not use a decorator like `tornado.gen.coroutine` or
`asyncio.coroutine`), not all coroutines are compatible with each
other. There is a *coroutine runner* which is selected by the first
coroutine to be called, and then shared by all coroutines which are
called directly with ``await``. The Tornado coroutine runner is
designed to be versatile and accept awaitable objects from any
framework; other coroutine runners may be more limited (for example,
the ``asyncio`` coroutine runner does not accept coroutines from other
frameworks). For this reason, it is recommended to use the Tornado
coroutine runner for any application which combines multiple
frameworks. To call a coroutine using the Tornado runner from within a
coroutine that is already using the asyncio runner, use the
`tornado.platform.asyncio.to_asyncio_future` adapter.


How it works
~~~~~~~~~~~~

A function containing ``yield`` is a **generator**.  All generators
are asynchronous; when called they return a generator object instead
of running to completion.  The ``@gen.coroutine`` decorator
communicates with the generator via the ``yield`` expressions, and
with the coroutine's caller by returning a `.Future`.

Here is a simplified version of the coroutine decorator's inner loop::

    # Simplified inner loop of tornado.gen.Runner
    def run(self):
        # send(x) makes the current yield return x.
        # It returns when the next yield is reached
        future = self.gen.send(self.next)
        def callback(f):
            self.next = f.result()
            self.run()
        future.add_done_callback(callback)

The decorator receives a `.Future` from the generator, waits (without
blocking) for that `.Future` to complete, then "unwraps" the `.Future`
and sends the result back into the generator as the result of the
``yield`` expression.  Most asynchronous code never touches the `.Future`
class directly except to immediately pass the `.Future` returned by
an asynchronous function to a ``yield`` expression.

How to call a coroutine
~~~~~~~~~~~~~~~~~~~~~~~

Coroutines do not raise exceptions in the normal way: any exception
they raise will be trapped in the `.Future` until it is yielded. This
means it is important to call coroutines in the right way, or you may
have errors that go unnoticed::

    @gen.coroutine
    def divide(x, y):
        return x / y

    def bad_call():
        # This should raise a ZeroDivisionError, but it won't because
        # the coroutine is called incorrectly.
        divide(1, 0)

In nearly all cases, any function that calls a coroutine must be a
coroutine itself, and use the ``yield`` keyword in the call. When you
are overriding a method defined in a superclass, consult the
documentation to see if coroutines are allowed (the documentation
should say that the method "may be a coroutine" or "may return a
`.Future`")::

    @gen.coroutine
    def good_call():
        # yield will unwrap the Future returned by divide() and raise
        # the exception.
        yield divide(1, 0)

Sometimes you may want to "fire and forget" a coroutine without waiting
for its result. In this case it is recommended to use `.IOLoop.spawn_callback`,
which makes the `.IOLoop` responsible for the call. If it fails,
the `.IOLoop` will log a stack trace::

    # The IOLoop will catch the exception and print a stack trace in
    # the logs. Note that this doesn't look like a normal call, since
    # we pass the function object to be called by the IOLoop.
    IOLoop.current().spawn_callback(divide, 1, 0)

Finally, at the top level of a program, *if the `.IOLoop` is not yet
running,* you can start the `.IOLoop`, run the coroutine, and then
stop the `.IOLoop` with the `.IOLoop.run_sync` method. This is often
used to start the ``main`` function of a batch-oriented program::

    # run_sync() doesn't take arguments, so we must wrap the
    # call in a lambda.
    IOLoop.current().run_sync(lambda: divide(1, 0))

Coroutine patterns
~~~~~~~~~~~~~~~~~~

Interaction with callbacks
^^^^^^^^^^^^^^^^^^^^^^^^^^

To interact with asynchronous code that uses callbacks instead of
`.Future`, wrap the call in a `.Task`.  This will add the callback
argument for you and return a `.Future` which you can yield:

.. testcode::

    @gen.coroutine
    def call_task():
        # Note that there are no parens on some_function.
        # This will be translated by Task into
        #   some_function(other_args, callback=callback)
        yield gen.Task(some_function, other_args)

.. testoutput::
   :hide:

Calling blocking functions
^^^^^^^^^^^^^^^^^^^^^^^^^^

The simplest way to call a blocking function from a coroutine is to
use a `~concurrent.futures.ThreadPoolExecutor`, which returns
``Futures`` that are compatible with coroutines::

    thread_pool = ThreadPoolExecutor(4)

    @gen.coroutine
    def call_blocking():
        yield thread_pool.submit(blocking_func, args)

Parallelism
^^^^^^^^^^^

The coroutine decorator recognizes lists and dicts whose values are
``Futures``, and waits for all of those ``Futures`` in parallel:

.. testcode::

    @gen.coroutine
    def parallel_fetch(url1, url2):
        resp1, resp2 = yield [http_client.fetch(url1),
                              http_client.fetch(url2)]

    @gen.coroutine
    def parallel_fetch_many(urls):
        responses = yield [http_client.fetch(url) for url in urls]
        # responses is a list of HTTPResponses in the same order

    @gen.coroutine
    def parallel_fetch_dict(urls):
        responses = yield {url: http_client.fetch(url)
                            for url in urls}
        # responses is a dict {url: HTTPResponse}

.. testoutput::
   :hide:

Interleaving
^^^^^^^^^^^^

Sometimes it is useful to save a `.Future` instead of yielding it
immediately, so you can start another operation before waiting:

.. testcode::

    @gen.coroutine
    def get(self):
        fetch_future = self.fetch_next_chunk()
        while True:
            chunk = yield fetch_future
            if chunk is None: break
            self.write(chunk)
            fetch_future = self.fetch_next_chunk()
            yield self.flush()

.. testoutput::
   :hide:

Looping
^^^^^^^

Looping is tricky with coroutines since there is no way in Python
to ``yield`` on every iteration of a ``for`` or ``while`` loop and
capture the result of the yield.  Instead, you'll need to separate
the loop condition from accessing the results, as in this example
from `Motor <https://motor.readthedocs.io/en/stable/>`_::

    import motor
    db = motor.MotorClient().test

    @gen.coroutine
    def loop_example(collection):
        cursor = db.collection.find()
        while (yield cursor.fetch_next):
            doc = cursor.next_object()

Running in the background
^^^^^^^^^^^^^^^^^^^^^^^^^

`.PeriodicCallback` is not normally used with coroutines. Instead, a
coroutine can contain a ``while True:`` loop and use
`tornado.gen.sleep`::

    @gen.coroutine
    def minute_loop():
        while True:
            yield do_something()
            yield gen.sleep(60)

    # Coroutines that loop forever are generally started with
    # spawn_callback().
    IOLoop.current().spawn_callback(minute_loop)

Sometimes a more complicated loop may be desirable. For example, the
previous loop runs every ``60+N`` seconds, where ``N`` is the running
time of ``do_something()``. To run exactly every 60 seconds, use the
interleaving pattern from above::

    @gen.coroutine
    def minute_loop2():
        while True:
            nxt = gen.sleep(60)   # Start the clock.
            yield do_something()  # Run while the clock is ticking.
            yield nxt             # Wait for the timer to run out.
