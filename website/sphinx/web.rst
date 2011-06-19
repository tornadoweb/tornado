``tornado.web`` --- ``RequestHandler`` and ``Application`` classes
==================================================================

.. automodule:: tornado.web

   Request handlers
   ----------------
   .. autoclass:: RequestHandler

   Entry points
   ^^^^^^^^^^^^
   
   .. automethod:: RequestHandler.initialize
   .. automethod:: RequestHandler.prepare

   Implement any of the following methods to handle the corresponding
   HTTP method.

   .. automethod:: RequestHandler.get
   .. automethod:: RequestHandler.post
   .. automethod:: RequestHandler.put
   .. automethod:: RequestHandler.delete
   .. automethod:: RequestHandler.head
   .. automethod:: RequestHandler.options

   Input
   ^^^^^

   .. automethod:: RequestHandler.get_argument
   .. automethod:: RequestHandler.get_arguments
   .. automethod:: RequestHandler.decode_argument
   .. attribute:: RequestHandler.request

      The `tornado.httpserver.HTTPRequest` object containing additional
      request parameters including e.g. headers and body data.

   Output
   ^^^^^^

   .. automethod:: RequestHandler.set_status
   .. automethod:: RequestHandler.set_header
   .. automethod:: RequestHandler.write
   .. automethod:: RequestHandler.flush
   .. automethod:: RequestHandler.finish
   .. automethod:: RequestHandler.render
   .. automethod:: RequestHandler.render_string
   .. automethod:: RequestHandler.redirect
   .. automethod:: RequestHandler.send_error
   .. automethod:: RequestHandler.get_error_html
   .. automethod:: RequestHandler.clear


   Cookies
   ^^^^^^^

   .. autoattribute:: RequestHandler.cookies
   .. automethod:: RequestHandler.get_cookie
   .. automethod:: RequestHandler.set_cookie
   .. automethod:: RequestHandler.clear_cookie
   .. automethod:: RequestHandler.clear_all_cookies
   .. automethod:: RequestHandler.get_secure_cookie
   .. automethod:: RequestHandler.set_secure_cookie
   .. automethod:: RequestHandler.create_signed_value

   Other
   ^^^^^

   .. attribute:: RequestHandler.application

      The `Application` object serving this request

   .. automethod:: RequestHandler.async_callback
   .. automethod:: RequestHandler.check_xsrf_cookie
   .. automethod:: RequestHandler.compute_etag
   .. automethod:: RequestHandler.get_browser_locale
   .. automethod:: RequestHandler.get_current_user
   .. automethod:: RequestHandler.get_login_url
   .. automethod:: RequestHandler.get_status
   .. automethod:: RequestHandler.get_template_path
   .. automethod:: RequestHandler.get_user_locale
   .. automethod:: RequestHandler.on_connection_close
   .. automethod:: RequestHandler.require_setting
   .. automethod:: RequestHandler.reverse_url
   .. autoattribute:: RequestHandler.settings
   .. automethod:: RequestHandler.static_url
   .. automethod:: RequestHandler.xsrf_form_html



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
