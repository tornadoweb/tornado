``tornado.gen`` --- Simplify asynchronous code
==============================================

.. automodule:: tornado.gen

   Decorator
   ---------

   .. autofunction:: engine

   Yield points
   ------------

   Instances of the following classes may be used in yield expressions
   in the generator.

   .. autoclass:: Task

   .. autoclass:: Callback

   .. autoclass:: Wait

   .. autoclass:: WaitAll

   Other classes
   -------------

   .. class:: Arguments

      The result of a yield expression whose callback had more than one
      argument (or keyword arguments).

      The `Arguments` object can be used as a tuple ``(args, kwargs)``
      or an object with attributes ``args`` and ``kwargs``.
