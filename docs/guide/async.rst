Asynchronous and non-Blocking I/O
---------------------------------

Real-time web features require a long-lived mostly-idle connection per
user.  In a traditional synchronous web server, this implies devoting
one thread to each user, which can be very expensive.

To minimize the cost of concurrent connections, Tornado uses a
single-threaded event loop.  This means that all application code
should aim to be asynchronous and non-blocking because only one
operation can be active at a time.

The terms asynchronous and non-blocking are closely related and are
often used interchangeably, but they are not quite the same thing.

Blocking
~~~~~~~~

A function **blocks** when it waits for something to happen before
returning.  A function may block for many reasons: network I/O, disk
I/O, mutexes, etc.  In fact, *every* function blocks, at least a
little bit, while it is running and using the CPU (for an extreme
example that demonstrates why CPU blocking must be taken as seriously
as other kinds of blocking, consider password hashing functions like
`bcrypt <http://bcrypt.sourceforge.net/>`_, which by design use
hundreds of milliseconds of CPU time, far more than a typical network
or disk access).

A function can be blocking in some respects and non-blocking in
others.  In the context of Tornado we generally talk about
blocking in the context of network I/O, although all kinds of blocking
are to be minimized.

Asynchronous
~~~~~~~~~~~~

An **asynchronous** function returns before it is finished, and
generally causes some work to happen in the background before
triggering some future action in the application (as opposed to normal
**synchronous** functions, which do everything they are going to do
before returning).  There are many styles of asynchronous interfaces:

* Callback argument
* Return a placeholder (`.Future`, ``Promise``, ``Deferred``)
* Deliver to a queue
* Callback registry (e.g. POSIX signals)

Regardless of which type of interface is used, asynchronous functions
*by definition* interact differently with their callers; there is no
free way to make a synchronous function asynchronous in a way that is
transparent to its callers (systems like `gevent
<http://www.gevent.org>`_ use lightweight threads to offer performance
comparable to asynchronous systems, but they do not actually make
things asynchronous).

Asynchronous operations in Tornado generally return placeholder
objects (``Futures``), with the exception of some low-level components
like the `.IOLoop` that use callbacks. ``Futures`` are usually
transformed into their result with the ``await`` or ``yield``
keywords.

Examples
~~~~~~~~

Here is a sample synchronous function:

.. testcode::

    from tornado.httpclient import HTTPClient

    def synchronous_fetch(url):
        http_client = HTTPClient()
        response = http_client.fetch(url)
        return response.body

.. testoutput::
   :hide:

And here is the same function rewritten asynchronously as a native coroutine:

.. testcode::

   from tornado.httpclient import AsyncHTTPClient

   async def asynchronous_fetch(url):
       http_client = AsyncHTTPClient()
       response = await http_client.fetch(url)
       return response.body

.. testoutput::
   :hide:

Or for compatibility with older versions of Python, using the `tornado.gen` module:

..  testcode::

    from tornado.httpclient import AsyncHTTPClient
    from tornado import gen

    @gen.coroutine
    def async_fetch_gen(url):
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch(url)
        raise gen.Return(response.body)

Coroutines are a little magical, but what they do internally is something like this:

.. testcode::

    from tornado.concurrent import Future

    def async_fetch_manual(url):
        http_client = AsyncHTTPClient()
        my_future = Future()
        fetch_future = http_client.fetch(url)
        def on_fetch(f):
            my_future.set_result(f.result().body)
        fetch_future.add_done_callback(on_fetch)
        return my_future

.. testoutput::
   :hide:

Notice that the coroutine returns its `.Future` before the fetch is
done. This is what makes coroutines *asynchronous*.

Anything you can do with coroutines you can also do by passing
callback objects around, but coroutines provide an important
simplification by letting you organize your code in the same way you
would if it were synchronous. This is especially important for error
handling, since ``try``/``except`` blocks work as you would expect in
coroutines while this is difficult to achieve with callbacks.
Coroutines will be discussed in depth in the next section of this
guide.
