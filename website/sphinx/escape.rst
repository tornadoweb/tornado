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
   These functions are used extensively within Tornado itself,
   but should not be directly needed by most applications.  Note that 
   much of the complexity of these functions comes from the fact that
   Tornado supports both Python 2 and Python 3.

   .. autofunction:: utf8
   .. autofunction:: to_unicode
   .. function:: native_str

      Converts a byte or unicode string into type `str`.  Equivalent to
      `utf8` on Python 2 and `to_unicode` on Python 3.

   .. autofunction:: to_basestring

   .. autofunction:: recursive_unicode

   Miscellaneous functions
   -----------------------
   .. autofunction:: linkify
   .. autofunction:: squeeze
