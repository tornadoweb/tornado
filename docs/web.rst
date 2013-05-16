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
   .. automethod:: RequestHandler.on_finish

   .. _verbs:

   Implement any of the following methods (collectively known as the
   HTTP verb methods) to handle the corresponding HTTP method.
   These methods can be made asynchronous with one of the following
   decorators: `.gen.coroutine`, `.return_future`, or `asynchronous`.

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

   .. attribute:: RequestHandler.path_args
   .. attribute:: RequestHandler.path_kwargs

      The ``path_args`` and ``path_kwargs`` attributes contain the
      positional and keyword arguments that are passed to the
      :ref:`HTTP verb methods <verbs>`.  These attributes are set
      before those methods are called, so the values are available
      during `prepare`.

   Output
   ^^^^^^

   .. automethod:: RequestHandler.set_status
   .. automethod:: RequestHandler.set_header
   .. automethod:: RequestHandler.add_header
   .. automethod:: RequestHandler.clear_header
   .. automethod:: RequestHandler.set_default_headers
   .. automethod:: RequestHandler.write
   .. automethod:: RequestHandler.flush
   .. automethod:: RequestHandler.finish
   .. automethod:: RequestHandler.render
   .. automethod:: RequestHandler.render_string
   .. automethod:: RequestHandler.get_template_namespace
   .. automethod:: RequestHandler.redirect
   .. automethod:: RequestHandler.send_error
   .. automethod:: RequestHandler.write_error
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
   .. automethod:: RequestHandler.create_template_loader
   .. automethod:: RequestHandler.get_browser_locale
   .. automethod:: RequestHandler.get_current_user
   .. automethod:: RequestHandler.get_login_url
   .. automethod:: RequestHandler.get_status
   .. automethod:: RequestHandler.get_template_path
   .. automethod:: RequestHandler.get_user_locale
   .. automethod:: RequestHandler.log_exception
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

      .. attribute:: settings

         Additional keyword arguments passed to the constructor are
         saved in the `settings` dictionary, and are often referred to
         in documentation as "application settings".  Settings are
         used to customize various aspects of Tornado (although in
         some cases richer customization is possible by overriding
         methods in a subclass of `RequestHandler`).  Some
         applications also like to use the `settings` dictionary as a
         way to make application-specific settings available to
         handlers without using global variables.  Settings used in
         Tornado are described below.

         General settings:

         * ``debug``: If ``True`` the application runs in debug mode,
           described in :ref:`debug-mode`.
         * ``gzip``: If ``True``, responses in textual formats will be
           gzipped automatically.
         * ``log_function``: This function will be called at the end
           of every request to log the result (with one argument, the
           `RequestHandler` object).  The default implementation
           writes to the `logging` module's root logger.  May also be
           customized by overriding `Application.log_request`.
         * ``ui_modules`` and ``ui_methods``: May be set to a mapping
           of `UIModule` or UI methods to be made available to templates.
           May be set to a module, dictionary, or a list of modules
           and/or dicts.  See :ref:`ui-modules` for more details.

         Authentication and security settings:

         * ``cookie_secret``: Used by `RequestHandler.get_secure_cookie`
           and `.set_secure_cookie` to sign cookies.
         * ``login_url``: The `authenticated` decorator will redirect
           to this url if the user is not logged in.  Can be further
           customized by overriding `RequestHandler.get_login_url`
         * ``xsrf_cookies``: If true, :ref:`xsrf` will be enabled.
         * ``twitter_consumer_key``, ``twitter_consumer_secret``,
           ``friendfeed_consumer_key``, ``friendfeed_consumer_secret``,
           ``google_consumer_key``, ``google_consumer_secret``,
           ``facebook_api_key``, ``facebook_secret``:  Used in the
           `tornado.auth` module to authenticate to various APIs.

         Template settings:

         * ``autoescape``: Controls automatic escaping for templates.
           May be set to ``None`` to disable escaping, or to the *name*
           of a function that all output should be passed through.
           Defaults to ``"xhtml_escape"``.  Can be changed on a per-template
           basis with the ``{% autoescape %}`` directive.
         * ``template_path``: Directory containing template files.  Can be
           further customized by overriding `RequestHandler.get_template_path`
         * ``template_loader``: Assign to an instance of
           `tornado.template.BaseLoader` to customize template loading.
           If this setting is used the ``template_path`` and ``autoescape``
           settings are ignored.  Can be further customized by overriding
           `RequestHandler.create_template_loader`.

         Static file settings:

         * ``static_path``: Directory from which static files will be
           served.
         * ``static_url_prefix``:  Url prefix for static files,
           defaults to ``"/static/"``.
         * ``static_handler_class``, ``static_handler_args``: May be set to
           use a different handler for static files instead of the default
           `tornado.web.StaticFileHandler`.  ``static_handler_args``, if set,
           should be a dictionary of keyword arguments to be passed to the
           handler's ``initialize`` method.

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
   .. autoexception:: MissingArgumentError
   .. autoclass:: UIModule
      :members:

   .. autoclass:: ErrorHandler
   .. autoclass:: FallbackHandler
   .. autoclass:: RedirectHandler
   .. autoclass:: StaticFileHandler
      :members:
