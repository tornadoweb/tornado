What's new in the next release of Tornado
=========================================

In progress
-----------

``tornado.template``
~~~~~~~~~~~~~~~~~~~~

* Exceptions in template code will now show better stack traces that
  reference lines from the original template file.
* ``{#`` and ``#}`` can now be used for comments (and unlike the old
  ``{% comment %}`` directive, these can wrap other template directives).
* Template directives may now span multiple lines.

Other modules
~~~~~~~~~~~~~

* `tornado.iostream.IOStream.write` now works correctly when given an
  empty string.
* `tornado.simple_httpclient` no longer hangs on ``HEAD`` requests,
  responses with no content, or empty ``POST``/``PUT`` response bodies.
* `tornado.websocket` has been updated to support the latest protocol
  (as finalized in RFC 6455).
* `tornado.platform.twisted` compatibility has been improved.  However,
  only Twisted version 11.0.0 is supported (and not 11.1.0).
* `tornado.ioloop.PeriodicCallback` no longer triggers duplicate callbacks
  when stopped and started repeatedly.
* `tornado.web` now behaves better when given malformed ``Cookie`` headers
* `tornado.testing.main` supports a new flag ``--exception_on_interrupt``,
  which can be set to false to make ``Ctrl-C`` kill the process more
  reliably (at the expense of stack traces when it does so).
* `tornado.process.fork_processes` correctly reseeds the `random` module
  even when `os.urandom` is not implemented.
