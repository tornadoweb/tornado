What's new in the next release of Tornado
=========================================

In progress
-----------

New features
~~~~~~~~~~~~

* New method `tornado.iostream.IOStream.read_until_close`

Bug fixes
~~~~~~~~~

* `HTTPServer`: fixed exception at startup when ``socket.AI_ADDRCONFIG`` is
  not available, as on Windows XP
* `tornado.websocket`: now works on Python 3
* `SimpleAsyncHTTPClient`: now works with HTTP 1.0 servers that don't send
  a Content-Length header
