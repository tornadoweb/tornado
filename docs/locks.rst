``tornado.locks`` -- Synchronization primitives
===============================================

.. versionadded:: 4.2

Coordinate coroutines with synchronization primitives analogous to those the
standard library provides to threads.

*(Note that these primitives are not actually thread-safe and cannot be used in
place of those from the standard library--they are meant to coordinate Tornado
coroutines in a single-threaded app, not to protect shared objects in a
multithreaded app.)*

.. automodule:: tornado.locks

   Condition
   ---------
   .. autoclass:: Condition
    :members:

   Event
   -----
   .. autoclass:: Event
    :members:

   Semaphore
   ---------
   .. autoclass:: Semaphore
    :members:

   BoundedSemaphore
   ----------------
   .. autoclass:: BoundedSemaphore
    :members:
    :inherited-members:

   Lock
   ----
   .. autoclass:: Lock
    :members:
    :inherited-members:
