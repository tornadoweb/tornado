What's new in the next version of Tornado
=========================================

In progress
-----------

Highlights
~~~~~~~~~~

* The new async/await keywords in Python 3.5 are supported. TODO: say more.

`tornado.auth`
~~~~~~~~~~~~~~

* New method `.OAuth2Mixin.oauth2_request` can be used to make authenticated
  requests with an access token.

`tornado.autoreload`
~~~~~~~~~~~~~~~~~~~~

* Fixed an issue with the autoreload command-line wrapper in which
  imports would be incorrectly interpreted as relative.

`tornado.httputil`
~~~~~~~~~~~~~~~~~~

* `.HTTPHeaders` can now be pickled and unpickled.

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

`tornado.options`
~~~~~~~~~~~~~~~~~

* Dashes and underscores are now fully interchangeable in option names.

`tornado.template`
~~~~~~~~~~~~~~~~~~

* `tornado.template.ParseError` now includes the filename in addition to
  line number.

`tornado.testing`
~~~~~~~~~~~~~~~~~

* `.ExpectLog` objects now have a boolean ``logged_stack`` attribute to
  make it easier to test whether an exception stack trace was logged.
