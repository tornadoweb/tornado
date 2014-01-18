What's new in the next version of Tornado
=========================================

In progress
-----------

Backwards-compatibility notes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Authors of alternative `.IOLoop` implementations should see the changes
  to `.IOLoop.add_handler` in this release.

`tornado.ioloop`
~~~~~~~~~~~~~~~~

* `.IOLoop.add_handler` and related methods now accept file-like objects
  in addition to raw file descriptors.  Passing the objects is recommended
  (when possible) to avoid a garbage-collection-related problem in unit tests.

`tornado.websocket`
~~~~~~~~~~~~~~~~~~~

* The C speedup module now builds correctly with MSVC, and can support
  messages larger than 2GB on 64-bit systems.
