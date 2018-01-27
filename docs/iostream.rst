``tornado.iostream`` --- Convenient wrappers for non-blocking sockets
=====================================================================

.. automodule:: tornado.iostream

   Base class
   ----------

   .. autoclass:: BaseIOStream

   Main interface
   ^^^^^^^^^^^^^^

   .. automethod:: BaseIOStream.write
   .. automethod:: BaseIOStream.read_bytes
   .. automethod:: BaseIOStream.read_into
   .. automethod:: BaseIOStream.read_until
   .. automethod:: BaseIOStream.read_until_regex
   .. automethod:: BaseIOStream.read_until_close
   .. automethod:: BaseIOStream.close
   .. automethod:: BaseIOStream.set_close_callback
   .. automethod:: BaseIOStream.closed
   .. automethod:: BaseIOStream.reading
   .. automethod:: BaseIOStream.writing
   .. automethod:: BaseIOStream.set_nodelay

   Methods for subclasses
   ^^^^^^^^^^^^^^^^^^^^^^

   .. automethod:: BaseIOStream.fileno
   .. automethod:: BaseIOStream.close_fd
   .. automethod:: BaseIOStream.write_to_fd
   .. automethod:: BaseIOStream.read_from_fd
   .. automethod:: BaseIOStream.get_fd_error

   Implementations
   ---------------

   .. autoclass:: IOStream
      :members:

   .. autoclass:: SSLIOStream
      :members:

   .. autoclass:: PipeIOStream
      :members:

   Exceptions
   ----------

   .. autoexception:: StreamBufferFullError
   .. autoexception:: StreamClosedError
   .. autoexception:: UnsatisfiableReadError
