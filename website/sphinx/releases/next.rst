What's new in the next release of Tornado
=========================================

In progress
-----------

Backwards-incompatible changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* `tornado.process.fork_processes` now raises `SystemExit` if all child
  processes exit cleanly rather than returning ``None``.  The old behavior
  was surprising and inconsistent with most of the documented examples
  of this function (which did not check the return value).
* `tornado.websocket` no longer supports the older "draft 76" version
  of the websocket protocol by default, although this version can
  be enabled by overriding `tornado.websocket.WebSocketHandler.allow_draft76`.

``IOLoop`` and ``IOStream``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* `IOStream.write` now works correctly when given an empty string.
* `IOStream.read_until` (and ``read_until_regex``) now perform better
  when there is a lot of buffered data, which improves peformance of
  `SimpleAsyncHTTPClient` when downloading files with lots of
  chunks.
* Idle ``IOLoops`` no longer wake up several times a second.
* `tornado.ioloop.PeriodicCallback` no longer triggers duplicate callbacks
  when stopped and started repeatedly.

``tornado.template``
~~~~~~~~~~~~~~~~~~~~

* Exceptions in template code will now show better stack traces that
  reference lines from the original template file.
* ``{#`` and ``#}`` can now be used for comments (and unlike the old
  ``{% comment %}`` directive, these can wrap other template directives).
* Template directives may now span multiple lines.

``tornado.websocket``
~~~~~~~~~~~~~~~~~~~~~

* Updated to support the latest version of the protocol, as finalized
  in RFC 6455.
* `tornado.websocket` no longer supports the older "draft 76" version
  of the websocket protocol by default, although this version can
  be enabled by overriding `tornado.websocket.WebSocketHandler.allow_draft76`.
* `WebSocketHandler.write_message` now accepts a ``binary`` argument
  to send binary messages.

Other modules
~~~~~~~~~~~~~

* `SimpleAsyncHTTPClient` no longer hangs on ``HEAD`` requests,
  responses with no content, or empty ``POST``/``PUT`` response bodies.
* `tornado.platform.twisted` compatibility has been improved.  However,
  only Twisted version 11.0.0 is supported (and not 11.1.0).
* `tornado.web` now behaves better when given malformed ``Cookie`` headers
* `RequestHandler.redirect` now has a ``status`` argument to send
  status codes other than 301 and 302.
* `tornado.testing.main` supports a new flag ``--exception_on_interrupt``,
  which can be set to false to make ``Ctrl-C`` kill the process more
  reliably (at the expense of stack traces when it does so).
* `tornado.process.fork_processes` correctly reseeds the `random` module
  even when `os.urandom` is not implemented.
* `HTTPServer` with ``xheaders=True`` will no longer accept
  ``X-Real-IP`` headers that don't look like valid IP addresses.
* Exception handling in `tornado.gen` has been improved.  It is now possible
  to catch exceptions thrown by a ``Task``.
