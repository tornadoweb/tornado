``tornado.web``
===============

.. automodule:: tornado.web

   Request handlers
   ----------------
   .. autoclass:: RequestHandler

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
      .. automethod:: redirect
      .. automethod:: send_error
      .. automethod:: get_error_html
      .. automethod:: clear


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

      .. automethod:: async_callback
      .. automethod:: check_xsrf_cookie
      .. automethod:: compute_etag
      .. automethod:: get_browser_locale
      .. automethod:: get_current_user
      .. automethod:: get_login_url
      .. automethod:: get_status
      .. automethod:: get_template_path
      .. automethod:: get_user_locale
      .. automethod:: on_connection_close
      .. automethod:: require_setting
      .. automethod:: static_url
      .. automethod:: xsrf_form_html



   Application configuration
   -----------------------------
   .. autoclass:: Application
      :members:

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
   .. autoexception:: HTTPError
   .. autoclass:: UIModule
      :members:

   .. autoclass:: ErrorHandler
   .. autoclass:: FallbackHandler
   .. autoclass:: RedirectHandler
   .. autoclass:: StaticFileHandler
      :members:
