``tornado.web``
===============

.. automodule:: tornado.web
   :exclude-members: RequestHandler, Application, asynchronous, addslash, removeslash, URLSpec, url

   Request handlers
   ----------------
   .. autoclass:: RequestHandler
      :exclude-members: initialize, prepare, get, post, put, delete, head, options, get_argument, get_arguments, decode_argument, set_status, set_header, write, flush, finish, render, render_string, send_error, get_error_html, cookies, get_cookie, set_cookie, clear_cookie, clear_all_cookies, get_secure_cookie, set_secure_cookie, create_signed_value

      **Entry points**
      
      .. automethod:: initialize
      .. automethod:: prepare

      Implement any of the following methods to handle the corresponding
      HTTP method.

      .. automethod:: get
      .. automethod:: post
      .. automethod:: put
      .. automethod:: delete
      .. automethod:: head
      .. automethod:: options

      **Input**

      .. automethod:: get_argument
      .. automethod:: get_arguments
      .. automethod:: decode_argument

      **Output**

      .. automethod:: set_status
      .. automethod:: set_header
      .. automethod:: write
      .. automethod:: flush
      .. automethod:: finish
      .. automethod:: render
      .. automethod:: render_string
      .. automethod:: send_error
      .. automethod:: get_error_html

      **Cookies**

      .. autoattribute:: cookies
      .. automethod:: get_cookie
      .. automethod:: set_cookie
      .. automethod:: clear_cookie
      .. automethod:: clear_all_cookies
      .. automethod:: get_secure_cookie
      .. automethod:: set_secure_cookie
      .. automethod:: create_signed_value

      **Other**



   Application configuration
   -----------------------------
   .. autoclass:: Application

   .. autoclass:: URLSpec

      The ``URLSpec`` class is also available under the name ``tornado.web.url``.

   Decorators
   ----------
   .. autofunction:: asynchronous
   .. autofunction:: authenticated
   .. autofunction:: addslash
   .. autofunction:: removeslash

   Everything else
   ---------------
