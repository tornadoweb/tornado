``tornado.options`` --- Command-line parsing
============================================

.. automodule:: tornado.options

   .. autofunction:: define

   .. py:data:: options

       Global options dictionary.  Supports both attribute-style and
       dict-style access.

   .. autofunction:: parse_command_line
   .. autofunction:: parse_config_file
   .. autofunction:: print_help(file=sys.stdout)
   .. autofunction:: enable_pretty_logging()
   .. autoexception:: Error
