Frequently Asked Questions
==========================

.. contents::
   :local:

Why isn't this example with ``time.sleep()`` running in parallel?
-----------------------------------------------------------------

Many people's first foray into Tornado's concurrency looks something like
this::

   class BadExampleHandler(RequestHandler):
       def get(self):
           for i in range(5):
               print(i)
               time.sleep(1)

Fetch this handler twice at the same time and you'll see that the second
five-second countdown doesn't start until the first one has completely
finished. The reason for this is that `time.sleep` is a **blocking**
function: it doesn't allow control to return to the `.IOLoop` so that other
handlers can be run.

Of course, `time.sleep` is really just a placeholder in these examples,
the point is to show what happens when something in a handler gets slow.
No matter what the real code is doing, to achieve concurrency blocking
code must be replaced with non-blocking equivalents. This means one of three things:

1. *Find a coroutine-friendly equivalent.* For `time.sleep`, use
   `tornado.gen.sleep` (or `asyncio.sleep`) instead::

    class CoroutineSleepHandler(RequestHandler):
        async def get(self):
            for i in range(5):
                print(i)
                await gen.sleep(1)

   When this option is available, it is usually the best approach.
   See the `Tornado wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_
   for links to asynchronous libraries that may be useful.

2. *Find a callback-based equivalent.* Similar to the first option,
   callback-based libraries are available for many tasks, although they
   are slightly more complicated to use than a library designed for
   coroutines. Adapt the callback-based function into a future::

    class CoroutineTimeoutHandler(RequestHandler):
        async def get(self):
            io_loop = IOLoop.current()
            for i in range(5):
                print(i)
                f = tornado.concurrent.Future()
                do_something_with_callback(f.set_result)
                result = await f

   Again, the
   `Tornado wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_
   can be useful to find suitable libraries.

3. *Run the blocking code on another thread.* When asynchronous libraries
   are not available, `concurrent.futures.ThreadPoolExecutor` can be used
   to run any blocking code on another thread. This is a universal solution
   that can be used for any blocking function whether an asynchronous
   counterpart exists or not::

    class ThreadPoolHandler(RequestHandler):
        async def get(self):
            for i in range(5):
                print(i)
                await IOLoop.current().run_in_executor(None, time.sleep, 1)

See the :doc:`Asynchronous I/O <guide/async>` chapter of the Tornado
user's guide for more on blocking and asynchronous functions.


My code is asynchronous. Why is it not running in parallel in two browser tabs?
-------------------------------------------------------------------------------

Even when a handler is asynchronous and non-blocking, it can be surprisingly
tricky to verify this. Browsers will recognize that you are trying to
load the same page in two different tabs and delay the second request
until the first has finished. To work around this and see that the server
is in fact working in parallel, do one of two things:

* Add something to your urls to make them unique. Instead of
  ``http://localhost:8888`` in both tabs, load
  ``http://localhost:8888/?x=1`` in one and
  ``http://localhost:8888/?x=2`` in the other.

* Use two different browsers. For example, Firefox will be able to load
  a url even while that same url is being loaded in a Chrome tab.
