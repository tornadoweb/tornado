``tornado.escape`` --- Escaping and string manipulation
=======================================================

.. automodule:: tornado.escape

   Escaping functions
   ------------------

   .. autofunction:: xhtml_escape
   .. autofunction:: xhtml_unescape

   .. autofunction:: url_escape
   .. autofunction:: url_unescape

   .. autofunction:: json_encode
   .. autofunction:: json_decode

   Byte/unicode conversions
   ------------------------

   .. autofunction:: utf8
   .. autofunction:: to_unicode
   .. function:: native_str
   .. function:: to_basestring

      Converts a byte or unicode string into type `str`. These functions
      were used to help transition from Python 2 to Python 3 but are now
      deprecated aliases for `to_unicode`.

   .. autofunction:: recursive_unicode

   Miscellaneous functions
   -----------------------
   .. autofunction:: linkify
   .. autofunction:: squeeze
