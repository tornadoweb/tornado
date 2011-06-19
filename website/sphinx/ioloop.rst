``tornado.ioloop`` --- Main event loop
======================================

.. automodule:: tornado.ioloop

   IOLoop objects
   --------------

   .. autoclass:: IOLoop

   Running an IOLoop
   ^^^^^^^^^^^^^^^^^

   .. automethod:: IOLoop.instance
   .. automethod:: IOLoop.initialized
   .. automethod:: IOLoop.start
   .. automethod:: IOLoop.stop
   .. automethod:: IOLoop.running

   I/O events
   ^^^^^^^^^^

   .. automethod:: IOLoop.add_handler
   .. automethod:: IOLoop.update_handler
   .. automethod:: IOLoop.remove_handler

   Timeouts
   ^^^^^^^^

   .. automethod:: IOLoop.add_callback
   .. automethod:: IOLoop.add_timeout
   .. automethod:: IOLoop.remove_timeout
   .. autoclass:: PeriodicCallback
      :members:

   Debugging and error handling
   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

   .. automethod:: IOLoop.handle_callback_exception
   .. automethod:: IOLoop.set_blocking_signal_threshold
   .. automethod:: IOLoop.set_blocking_log_threshold
   .. automethod:: IOLoop.log_stack
