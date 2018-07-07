``tornado.gen`` --- Generator-based coroutines
==============================================

.. testsetup::

   from tornado.web import *
   from tornado import gen

.. automodule:: tornado.gen

   Decorators
   ----------

   .. autofunction:: coroutine

   Utility functions
   -----------------

   .. autoexception:: Return

   .. autofunction:: with_timeout

   .. autofunction:: sleep

   .. autodata:: moment
      :annotation:

   .. autoclass:: WaitIterator
      :members:

   .. autofunction:: multi

   .. autofunction:: multi_future

   .. autofunction:: convert_yielded

   .. autofunction:: maybe_future

   .. autofunction:: is_coroutine_function
