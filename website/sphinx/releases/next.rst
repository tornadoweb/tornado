What's new in the next version of Tornado
=========================================

In progress
-----------

* ``setup.py`` no longer imports setuptools on Python 2.x.
* Colored logging configuration in `tornado.options` is compatible with
  the upcoming release of Python 3.3.
* `tornado.simple_httpclient` is better about closing its sockets
  instead of leaving them for garbage collection.
* Repeated calls to `RequestHandler.set_cookie` with the same name now
  overwrite the previous cookie instead of producing additional copies.
