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


`tornado.gen`
~~~~~~~~~~~~~

* On Python 3, catching an exception in a coroutine no longer leads to
  leaks via ``Exception.__context__``.

`tornado.ioloop`
~~~~~~~~~~~~~~~~

* `.PeriodicCallback` is now more efficient when the clock jumps forward
  by a large amount.

`tornado.iostream`
~~~~~~~~~~~~~~~~~~

* ``SSLIOStream.connect`` and `.IOStream.start_tls` now validate certificates
  by default.

`tornado.log`
~~~~~~~~~~~~~

* `.define_logging_options` now works correctly when given a non-default
  ``options`` object.

``tornado.simple_httpclient``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Improved performance on Python 3 by reusing a single `ssl.SSLContext`.

`tornado.util`
~~~~~~~~~~~~~~

* `.import_object` now supports unicode strings on Python 2.

`tornado.web`
~~~~~~~~~~~~~

* Passing ``secure=False`` or ``httponly=False`` to
  `.RequestHandler.set_cookie` now works as expected (previously only the
  presence of the argument was considered and its value was ignored).

`tornado.websocket`
~~~~~~~~~~~~~~~~~~~

* The ``on_close`` method will no longer be called more than once.
