What's new in the next version of Tornado
=========================================

In progress
-----------

Highlights
~~~~~~~~~~

* The new async/await keywords in Python 3.5 are supported. In most cases,
  ``async def`` can be used in place of the ``@gen.coroutine`` decorator.
  Inside a function defined with ``async def``, use ``await`` instead of
  ``yield`` to wait on an asynchronous operation. Coroutines defined with
  async/await will be faster than those defined with ``@gen.coroutine`` and
  ``yield``, but do not support some features including `.Callback`/`.Wait` or
  the ability to yield a Twisted ``Deferred``.

`tornado.auth`
~~~~~~~~~~~~~~

* New method `.OAuth2Mixin.oauth2_request` can be used to make authenticated
  requests with an access token.

`tornado.autoreload`
~~~~~~~~~~~~~~~~~~~~

* Fixed an issue with the autoreload command-line wrapper in which
  imports would be incorrectly interpreted as relative.

`tornado.gen`
~~~~~~~~~~~~~

* `.WaitIterator` now supports the ``async for`` statement on Python 3.5.

`tornado.httputil`
~~~~~~~~~~~~~~~~~~

* `.HTTPHeaders` can now be pickled and unpickled.

`tornado.ioloop`
~~~~~~~~~~~~~~~~

* ``IOLoop(make_current=True)`` now works as intended instead
  of raising an exception.
* The Twisted and asyncio IOLoop implementations now clear
  ``current()`` when they exit, like the standard IOLoops.

`tornado.iostream`
~~~~~~~~~~~~~~~~~~

* Coroutine-style usage of `.IOStream` now converts most errors into
  `.StreamClosedError`, which has the effect of reducing log noise from
  exceptions that are outside the application's control (especially
  SSL errors).
* `.StreamClosedError` now has a ``real_error`` attribute which indicates
  why the stream was closed. It is the same as the ``error`` attribute of
  `.IOStream` but may be more easily accessible than the `.IOStream` itself.

`tornado.locale`
~~~~~~~~~~~~~~~~

* `tornado.locale.load_translations` now accepts encodings other than
  UTF-8. UTF-16 and UTF-8 will be detected automatically if a BOM is
  present; for other encodings `.load_translations` has an ``encoding``
  parameter.

`tornado.locks`
~~~~~~~~~~~~~~~

* `.Lock` and `.Semaphore` now support the ``async with`` statement on
  Python 3.5.

`tornado.options`
~~~~~~~~~~~~~~~~~

* Dashes and underscores are now fully interchangeable in option names.

`tornado.queues`
~~~~~~~~~~~~~~~~

* `.Queue` now supports the ``async with`` statement on Python 3.5.

`tornado.template`
~~~~~~~~~~~~~~~~~~

* `tornado.template.ParseError` now includes the filename in addition to
  line number.
* Whitespace handling has become more configurable. The `.Loader`
  constructor now has a ``whitespace`` argument, there is a new
  ``template_whitespace`` `.Application` setting, and there is a new
  ``{% whitespace %}`` template directive. All of these options take
  a mode name defined in the `tornado.template.filter_whitespace` function.
  The default mode is ``single``, which is the same behavior as prior
  versions of Tornado.

`tornado.testing`
~~~~~~~~~~~~~~~~~

* `.ExpectLog` objects now have a boolean ``logged_stack`` attribute to
  make it easier to test whether an exception stack trace was logged.

`tornado.web`
~~~~~~~~~~~~~

* The hard limit of 4000 bytes per outgoing header has been removed.
* `.StaticFileHandler` returns the correct ``Content-Type`` for files
  with ``.gz``, ``.bz2``, and ``.xz`` extensions.
* Responses smaller than 1000 bytes will no longer be compressed.
* The default gzip compression level is now 6 (was 9).
