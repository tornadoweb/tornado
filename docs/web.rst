``tornado.web`` --- ``RequestHandler`` and ``Application`` classes
==================================================================

.. testsetup::

   from tornado.web import *

.. automodule:: tornado.web

   Request handlers
   ----------------
   .. autoclass:: RequestHandler(...)

   Entry points
   ^^^^^^^^^^^^

   .. automethod:: RequestHandler.initialize
   .. automethod:: RequestHandler.prepare
   .. automethod:: RequestHandler.on_finish

   .. _verbs:

   Implement any of the following methods (collectively known as the
   HTTP verb methods) to handle the corresponding HTTP method. These
   methods can be made asynchronous with the ``async def`` keyword or
   `.gen.coroutine` decorator.

   The arguments to these methods come from the `.URLSpec`: Any
   capturing groups in the regular expression become arguments to the
   HTTP verb methods (keyword arguments if the group is named,
   positional arguments if it's unnamed).

   To support a method not on this list, override the class variable
   ``SUPPORTED_METHODS``::

     class WebDAVHandler(RequestHandler):
         SUPPORTED_METHODS = RequestHandler.SUPPORTED_METHODS + ('PROPFIND',)

         def propfind(self):
             pass

   .. automethod:: RequestHandler.get
   .. automethod:: RequestHandler.head
   .. automethod:: RequestHandler.post
   .. automethod:: RequestHandler.delete
   .. automethod:: RequestHandler.patch
   .. automethod:: RequestHandler.put
   .. automethod:: RequestHandler.options

   Input
   ^^^^^

   The ``argument`` methods provide support for HTML form-style
   arguments. These methods are available in both singular and plural
   forms because HTML forms are ambiguous and do not distinguish
   between a singular argument and a list containing one entry. If you
   wish to use other formats for arguments (for example, JSON), parse
   ``self.request.body`` yourself::

       def prepare(self):
           if self.request.headers['Content-Type'] == 'application/x-json':
               self.args = json_decode(self.request.body)
           # Access self.args directly instead of using self.get_argument.


   .. automethod:: RequestHandler.get_argument(name: str, default: Union[None, str, RAISE] = RAISE, strip: bool = True) -> Optional[str]
   .. automethod:: RequestHandler.get_arguments
   .. automethod:: RequestHandler.get_query_argument(name: str, default: Union[None, str, RAISE] = RAISE, strip: bool = True) -> Optional[str]
   .. automethod:: RequestHandler.get_query_arguments
   .. automethod:: RequestHandler.get_body_argument(name: str, default: Union[None, str, RAISE] = RAISE, strip: bool = True) -> Optional[str]
   .. automethod:: RequestHandler.get_body_arguments
   .. automethod:: RequestHandler.decode_argument
   .. attribute:: RequestHandler.request

      The `tornado.httputil.HTTPServerRequest` object containing additional
      request parameters including e.g. headers and body data.

   .. attribute:: RequestHandler.path_args
   .. attribute:: RequestHandler.path_kwargs

      The ``path_args`` and ``path_kwargs`` attributes contain the
      positional and keyword arguments that are passed to the
      :ref:`HTTP verb methods <verbs>`.  These attributes are set
      before those methods are called, so the values are available
      during `prepare`.

   .. automethod:: RequestHandler.data_received

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
   .. automethod:: RequestHandler.render_linked_js
   .. automethod:: RequestHandler.render_embed_js
   .. automethod:: RequestHandler.render_linked_css
   .. automethod:: RequestHandler.render_embed_css

   Cookies
   ^^^^^^^

   .. autoattribute:: RequestHandler.cookies
   .. automethod:: RequestHandler.get_cookie
   .. automethod:: RequestHandler.set_cookie
   .. automethod:: RequestHandler.clear_cookie
   .. automethod:: RequestHandler.clear_all_cookies
   .. automethod:: RequestHandler.get_signed_cookie
   .. automethod:: RequestHandler.get_signed_cookie_key_version
   .. automethod:: RequestHandler.set_signed_cookie
   .. method:: RequestHandler.get_secure_cookie

      Deprecated alias for ``get_signed_cookie``.

      .. deprecated:: 6.3

   .. method:: RequestHandler.get_secure_cookie_key_version

      Deprecated alias for ``get_signed_cookie_key_version``.

      .. deprecated:: 6.3

   .. method:: RequestHandler.set_secure_cookie

      Deprecated alias for ``set_signed_cookie``.

      .. deprecated:: 6.3

   .. automethod:: RequestHandler.create_signed_value
   .. autodata:: MIN_SUPPORTED_SIGNED_VALUE_VERSION
   .. autodata:: MAX_SUPPORTED_SIGNED_VALUE_VERSION
   .. autodata:: DEFAULT_SIGNED_VALUE_VERSION
   .. autodata:: DEFAULT_SIGNED_VALUE_MIN_VERSION

   Other
   ^^^^^

   .. attribute:: RequestHandler.application

      The `Application` object serving this request

   .. automethod:: RequestHandler.check_etag_header
   .. automethod:: RequestHandler.check_xsrf_cookie
   .. automethod:: RequestHandler.compute_etag
   .. automethod:: RequestHandler.create_template_loader
   .. autoattribute:: RequestHandler.current_user
   .. automethod:: RequestHandler.detach
   .. automethod:: RequestHandler.get_browser_locale
   .. automethod:: RequestHandler.get_current_user
   .. automethod:: RequestHandler.get_login_url
   .. automethod:: RequestHandler.get_status
   .. automethod:: RequestHandler.get_template_path
   .. automethod:: RequestHandler.get_user_locale
   .. autoattribute:: RequestHandler.locale
   .. automethod:: RequestHandler.log_exception
   .. automethod:: RequestHandler.on_connection_close
   .. automethod:: RequestHandler.require_setting
   .. automethod:: RequestHandler.reverse_url
   .. automethod:: RequestHandler.set_etag_header
   .. autoattribute:: RequestHandler.settings
   .. automethod:: RequestHandler.static_url
   .. automethod:: RequestHandler.xsrf_form_html
   .. autoattribute:: RequestHandler.xsrf_token



   Application configuration
   -------------------------

   .. autoclass:: Application(handlers: Optional[List[Union[Rule, Tuple]]] = None, default_host: Optional[str] = None, transforms: Optional[List[Type[OutputTransform]]] = None, **settings)

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

         * ``autoreload``: If ``True``, the server process will restart
           when any source files change, as described in :ref:`debug-mode`.
           This option is new in Tornado 3.2; previously this functionality
           was controlled by the ``debug`` setting.
         * ``debug``: Shorthand for several debug mode settings,
           described in :ref:`debug-mode`.  Setting ``debug=True`` is
           equivalent to ``autoreload=True``, ``compiled_template_cache=False``,
           ``static_hash_cache=False``, ``serve_traceback=True``.
         * ``default_handler_class`` and ``default_handler_args``:
           This handler will be used if no other match is found;
           use this to implement custom 404 pages (new in Tornado 3.2).
         * ``compress_response``: If ``True``, responses in textual formats
           will be compressed automatically.  New in Tornado 4.0.
         * ``gzip``: Deprecated alias for ``compress_response`` since
           Tornado 4.0.
         * ``log_function``: This function will be called at the end
           of every request to log the result (with one argument, the
           `RequestHandler` object).  The default implementation
           writes to the `logging` module's root logger.  May also be
           customized by overriding `Application.log_request`.
         * ``serve_traceback``: If ``True``, the default error page
           will include the traceback of the error.  This option is new in
           Tornado 3.2; previously this functionality was controlled by
           the ``debug`` setting.
         * ``ui_modules`` and ``ui_methods``: May be set to a mapping
           of `UIModule` or UI methods to be made available to templates.
           May be set to a module, dictionary, or a list of modules
           and/or dicts.  See :ref:`ui-modules` for more details.
         * ``websocket_ping_interval``: If the ping interval has a non-zero
           value, a ping will be sent periodically every
           ``websocket_ping_interval`` seconds, and the connection will be
           closed if a response is not received before the
           ``websocket_ping_timeout``.
           This can help keep the connection alive through certain proxy
           servers which close idle connections, and it can detect if the
           websocket has failed without being properly closed.
         * ``websocket_ping_timeout``: For use with ``websocket_ping_interval``,
           if the server does not receive a pong within this many seconds, it
           will close the websocket_ping_timeout.
           The default timeout is equal to the ping interval. The ping timeout
           will be turned off if the ping interval is not set or if the
           timeout is set to ``0``.
           This can help to detect disconnected clients to avoid keeping
           inactive connections open.

         Authentication and security settings:

         * ``cookie_secret``: Used by `RequestHandler.get_signed_cookie`
           and `.set_signed_cookie` to sign cookies.
         * ``key_version``: Used by requestHandler `.set_signed_cookie`
           to sign cookies with a specific key when ``cookie_secret``
           is a key dictionary.
         * ``login_url``: The `authenticated` decorator will redirect
           to this url if the user is not logged in.  Can be further
           customized by overriding `RequestHandler.get_login_url`
         * ``xsrf_cookies``: If ``True``, :ref:`xsrf` will be enabled.
         * ``xsrf_cookie_version``: Controls the version of new XSRF
           cookies produced by this server.  Should generally be left
           at the default (which will always be the highest supported
           version), but may be set to a lower value temporarily
           during version transitions.  New in Tornado 3.2.2, which
           introduced XSRF cookie version 2.
         * ``xsrf_cookie_kwargs``: May be set to a dictionary of
           additional arguments to be passed to `.RequestHandler.set_cookie`
           for the XSRF cookie.
         * ``xsrf_cookie_name``: Controls the name used for the XSRF
           cookie (default ``_xsrf``). The intended use is to take
           advantage of `cookie prefixes`_. Note that cookie prefixes
           interact with other cookie flags, so they must be combined
           with ``xsrf_cookie_kwargs``, such as
           ``{"xsrf_cookie_name": "__Host-xsrf", "xsrf_cookie_kwargs":
           {"secure": True}}``
         * ``twitter_consumer_key``, ``twitter_consumer_secret``,
           ``friendfeed_consumer_key``, ``friendfeed_consumer_secret``,
           ``google_consumer_key``, ``google_consumer_secret``,
           ``facebook_api_key``, ``facebook_secret``:  Used in the
           `tornado.auth` module to authenticate to various APIs.

         .. _cookie prefixes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#cookie_prefixes

         Template settings:

         * ``autoescape``: Controls automatic escaping for templates.
           May be set to ``None`` to disable escaping, or to the *name*
           of a function that all output should be passed through.
           Defaults to ``"xhtml_escape"``.  Can be changed on a per-template
           basis with the ``{% autoescape %}`` directive.
         * ``compiled_template_cache``: Default is ``True``; if ``False``
           templates will be recompiled on every request.  This option
           is new in Tornado 3.2; previously this functionality was controlled
           by the ``debug`` setting.
         * ``template_path``: Directory containing template files.  Can be
           further customized by overriding `RequestHandler.get_template_path`
         * ``template_loader``: Assign to an instance of
           `tornado.template.BaseLoader` to customize template loading.
           If this setting is used the ``template_path`` and ``autoescape``
           settings are ignored.  Can be further customized by overriding
           `RequestHandler.create_template_loader`.
         * ``template_whitespace``: Controls handling of whitespace in
           templates; see `tornado.template.filter_whitespace` for allowed
           values. New in Tornado 4.3.

         Static file settings:

         * ``static_hash_cache``: Default is ``True``; if ``False``
           static urls will be recomputed on every request.  This option
           is new in Tornado 3.2; previously this functionality was controlled
           by the ``debug`` setting.
         * ``static_path``: Directory from which static files will be
           served.
         * ``static_url_prefix``:  Url prefix for static files,
           defaults to ``"/static/"``.
         * ``static_handler_class``, ``static_handler_args``: May be set to
           use a different handler for static files instead of the default
           `tornado.web.StaticFileHandler`.  ``static_handler_args``, if set,
           should be a dictionary of keyword arguments to be passed to the
           handler's ``initialize`` method.

   .. automethod:: Application.listen
   .. automethod:: Application.add_handlers(handlers: List[Union[Rule, Tuple]])
   .. automethod:: Application.get_handler_delegate
   .. automethod:: Application.reverse_url
   .. automethod:: Application.log_request

   .. autoclass:: URLSpec

      The ``URLSpec`` class is also available under the name ``tornado.web.url``.

   Decorators
   ----------
   .. autofunction:: authenticated
   .. autofunction:: addslash
   .. autofunction:: removeslash
   .. autofunction:: stream_request_body

   Everything else
   ---------------
   .. autoexception:: HTTPError
   .. autoexception:: Finish
   .. autoexception:: MissingArgumentError
   .. autoclass:: UIModule
      :members:

   .. autoclass:: ErrorHandler
   .. autoclass:: FallbackHandler
   .. autoclass:: RedirectHandler
   .. autoclass:: StaticFileHandler
      :members:
