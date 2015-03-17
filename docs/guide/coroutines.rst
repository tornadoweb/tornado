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
from `Motor <http://motor.readthedocs.org/en/stable/>`_::

    import motor
    db = motor.MotorClient().test

    @gen.coroutine
    def loop_example(collection):
        cursor = db.collection.find()
        while (yield cursor.fetch_next):
            doc = cursor.next_object()
