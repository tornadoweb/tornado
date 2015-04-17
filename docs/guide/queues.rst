:class:`~tornado.queues.Queue` example - a concurrent web spider
================================================================

.. currentmodule:: tornado.queues

Tornado's `tornado.queues` module implements an asynchronous producer /
consumer pattern for coroutines, analogous to the pattern implemented for
threads by the Python standard library's `queue` module.

A coroutine that yields `Queue.get` pauses until there is an item in the queue.
If the queue has a maximum size set, a coroutine that yields `Queue.put` pauses
until there is room for another item.

A `~Queue` maintains a count of unfinished tasks, which begins at zero.
`~Queue.put` increments the count; `~Queue.task_done` decrements it.

In the web-spider example here, the queue begins containing only base_url. When
a worker fetches a page it parses the links and puts new ones in the queue,
then calls `~Queue.task_done` to decrement the counter once. Eventually, a
worker fetches a page whose URLs have all been seen before, and there is also
no work left in the queue. Thus that worker's call to `~Queue.task_done`
decrements the counter to zero. The main coroutine, which is waiting for
`~Queue.join`, is unpaused and finishes.

.. literalinclude:: ../../demos/webspider/webspider.py
