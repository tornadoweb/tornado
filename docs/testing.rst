``tornado.testing`` --- Unit testing support for asynchronous code
==================================================================

.. automodule:: tornado.testing

   Asynchronous test cases
   -----------------------

   .. autoclass:: AsyncTestCase
      :members:

   .. autoclass:: AsyncHTTPTestCase
      :members:

   .. autoclass:: AsyncHTTPSTestCase
      :members:

   .. autofunction:: gen_test

   Controlling log output
   ----------------------

   .. autoclass:: ExpectLog
      :members:

   .. autoclass:: LogTrapTestCase
      :members:

   Test runner
   -----------

   .. autofunction:: main

   Helper functions
   ----------------

   .. autofunction:: bind_unused_port

   .. autofunction:: get_unused_port

   .. autofunction:: get_async_test_timeout
