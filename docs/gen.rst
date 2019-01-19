``tornado.gen`` --- Generator-based coroutines
==============================================

.. testsetup::

   from tornado.web import *
   from tornado import gen

.. automodule:: tornado.gen

   Decorators
   ----------

   .. autofunction:: coroutine

   .. autoexception:: Return

   Utility functions
   -----------------

   .. autofunction:: with_timeout(timeout: Union[float, datetime.timedelta], future: Yieldable, quiet_exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = ())

   .. autofunction:: sleep

   .. autoclass:: WaitIterator
      :members:

   .. autofunction:: multi(Union[List[Yieldable], Dict[Any, Yieldable]], quiet_exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = ())

   .. autofunction:: multi_future(Union[List[Yieldable], Dict[Any, Yieldable]], quiet_exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = ())

   .. autofunction:: convert_yielded

   .. autofunction:: maybe_future

   .. autofunction:: is_coroutine_function

   .. autodata:: moment
      :annotation:
