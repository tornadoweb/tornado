What's new in the next version of Tornado
=========================================

In Progress
-----------

Backwards-compatibility notes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``SSLIOStream.connect`` and `.IOStream.start_tls` now validate certificates
  by default.
* Certificate validation will now use the system CA root certificates instead
  of ``certifi`` when possible (i.e. Python 2.7.9+ or 3.4+). This includes
  `.IOStream` and ``simple_httpclient``, but not ``curl_httpclient``.
* The default SSL configuration has become stricter, using
  `ssl.create_default_context` where available.
* The deprecated classes in the `tornado.auth` module, ``GoogleMixin``,
  ``FacebookMixin``, and ``FriendFeedMixin`` have been removed.

`tornado.autoreload`
~~~~~~~~~~~~~~~~~~~~

* Improved compatibility with Windows.

`tornado.gen`
~~~~~~~~~~~~~

* On Python 3, catching an exception in a coroutine no longer leads to
  leaks via ``Exception.__context__``.

`tornado.httpclient`
~~~~~~~~~~~~~~~~~~~~

* The ``raise_error`` argument now works correctly with the synchronous
  `.HTTPClient`.

`tornado.httpserver`
~~~~~~~~~~~~~~~~~~~~

* `.HTTPServer` is now a subclass of `tornado.util.Configurable`.

`tornado.ioloop`
~~~~~~~~~~~~~~~~

* `.PeriodicCallback` is now more efficient when the clock jumps forward
  by a large amount.

`tornado.iostream`
~~~~~~~~~~~~~~~~~~

* ``SSLIOStream.connect`` and `.IOStream.start_tls` now validate certificates
  by default.
* New method `.SSLIOStream.wait_for_handshake` allows server-side applications
  to wait for the handshake to complete in order to verify client certificates
  or use NPN/ALPN.
* The `.Future` returned by ``SSLIOStream.connect`` now resolves after the
  handshake is complete instead of as soon as the TCP connection is
  established.
* Reduced logging of SSL errors.
* `.BaseIOStream.read_until_close` now works correctly when a
  ``streaming_callback`` is given but ``callback`` is None (i.e. when
  it returns a `.Future`)

`tornado.locale`
~~~~~~~~~~~~~~~~

* New method `.GettextLocale.pgettext` allows additional context to be
  supplied for gettext translations.

`tornado.locks`
~~~~~~~~~~~~~~~

* New module contains locking and synchronization functionality imported
  from `Toro <http://toro.readthedocs.org>`_.

`tornado.log`
~~~~~~~~~~~~~

* `.define_logging_options` now works correctly when given a non-default
  ``options`` object.

`tornado.process`
~~~~~~~~~~~~~~~~~

* New method `.Subprocess.wait_for_exit` is a coroutine-friendly
  version of `.Subprocess.set_exit_callback`.

``tornado.simple_httpclient``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Improved performance on Python 3 by reusing a single `ssl.SSLContext`.

`tornado.queues`
~~~~~~~~~~~~~~~~

* New module contains queues imported from `Toro
  <http://toro.readthedocs.org>`_.

`tornado.tcpserver`
~~~~~~~~~~~~~~~~~~~

* `.TCPServer.handle_stream` may be a coroutine (so that any exceptions
  it raises will be logged).

`tornado.util`
~~~~~~~~~~~~~~

* `.import_object` now supports unicode strings on Python 2.
* `.Configurable.initialize` now supports positional arguments.

`tornado.web`
~~~~~~~~~~~~~

* Passing ``secure=False`` or ``httponly=False`` to
  `.RequestHandler.set_cookie` now works as expected (previously only the
  presence of the argument was considered and its value was ignored).
* Parsing of the ``If-None-Match`` header now follows the RFC and supports
  weak validators.
* `.RequestHandler.get_arguments` now requires that its ``strip`` argument
  be of type bool. This helps prevent errors caused by the slightly dissimilar
  interfaces between the singular and plural methods.
* Errors raised in ``_handle_request_exception`` are now logged more reliably.
* `.RequestHandler.redirect` now works correctly when called from a handler
  whose path begins with two slashes.
* Passing messages containing ``%`` characters to `tornado.web.HTTPError`
  no longer causes broken error messages.
* Key versioning support for cookie signing. ``cookie_secret`` application
  setting can now contain a dict of valid keys with version as key. The
  current signing key then must be specified via ``key_version`` setting.

`tornado.websocket`
~~~~~~~~~~~~~~~~~~~

* The ``on_close`` method will no longer be called more than once.
