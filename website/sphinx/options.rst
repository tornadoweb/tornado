``tornado.options`` --- Command-line parsing
============================================

.. automodule:: tornado.options



   Global functions
   ----------------
   
   .. autofunction:: define

   .. py:data:: options

       Global options object.  All defined options are available as attributes
       on this object.

   .. autofunction:: parse_command_line
   .. autofunction:: parse_config_file
   .. autofunction:: print_help(file=sys.stderr)
   .. autofunction:: add_parse_callback
   .. autoexception:: Error

   OptionParser class
   ------------------

   .. autoclass:: OptionParser
      :members:
