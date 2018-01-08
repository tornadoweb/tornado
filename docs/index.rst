.. title:: Tornado Web Server

.. meta::
    :google-site-verification: g4bVhgwbVO1d9apCUsT-eKlApg31Cygbp8VGZY8Rf0g

|Tornado Web Server|
====================

.. |Tornado Web Server| image:: tornado.png
    :alt: Tornado Web Server

`Tornado <http://www.tornadoweb.org>`_ is a Python web framework and
asynchronous networking library, originally developed at `FriendFeed
<http://friendfeed.com>`_.  By using non-blocking network I/O, Tornado
can scale to tens of thousands of open connections, making it ideal for
`long polling <http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_,
`WebSockets <http://en.wikipedia.org/wiki/WebSocket>`_, and other
applications that require a long-lived connection to each user.

Quick links
-----------

* Current version: |version| (`download from PyPI <https://pypi.python.org/pypi/tornado>`_, :doc:`release notes <releases>`)
* `Source (github) <https://github.com/tornadoweb/tornado>`_
* Mailing lists: `discussion <http://groups.google.com/group/python-tornado>`_ and `announcements <http://groups.google.com/group/python-tornado-announce>`_
* `Stack Overflow <http://stackoverflow.com/questions/tagged/tornado>`_
* `Wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_

Hello, world
------------

Here is a simple "Hello, world" example web app for Tornado::

    import tornado.ioloop
    import tornado.web

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    def make_app():
        return tornado.web.Application([
            (r"/", MainHandler),
        ])

    if __name__ == "__main__":
        app = make_app()
        app.listen(8888)
        tornado.ioloop.IOLoop.current().start()

This example does not use any of Tornado's asynchronous features; for
that see this `simple chat room
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_.

Installation
------------

::

    pip install tornado

Tornado is listed in `PyPI <http://pypi.python.org/pypi/tornado>`_ and
can be installed with ``pip``. Note that the source distribution
includes demo applications that are not present when Tornado is
installed in this way, so you may wish to download a copy of the
source tarball or clone the `git repository
<https://github.com/tornadoweb/tornado>`_ as well.

**Prerequisites**: Tornado runs on Python 2.7, and 3.4+.
The updates to the `ssl` module in Python 2.7.9 are required
(in some distributions, these updates may be available in
older python versions). In addition to the requirements
which will be installed automatically by ``pip`` or ``setup.py install``,
the following optional packages may be useful:

* `pycurl <http://pycurl.sourceforge.net>`_ is used by the optional
  ``tornado.curl_httpclient``.  Libcurl version 7.22 or higher is required.
* `Twisted <http://www.twistedmatrix.com>`_ may be used with the classes in
  `tornado.platform.twisted`.
* `pycares <https://pypi.python.org/pypi/pycares>`_ is an alternative
  non-blocking DNS resolver that can be used when threads are not
  appropriate.
* `monotonic <https://pypi.python.org/pypi/monotonic>`_ or `Monotime
  <https://pypi.python.org/pypi/Monotime>`_ add support for a
  monotonic clock, which improves reliability in environments where
  clock adjustments are frequent. No longer needed in Python 3.

**Platforms**: Tornado should run on any Unix-like platform, although
for the best performance and scalability only Linux (with ``epoll``)
and BSD (with ``kqueue``) are recommended for production deployment
(even though Mac OS X is derived from BSD and supports kqueue, its
networking performance is generally poor so it is recommended only for
development use).  Tornado will also run on Windows, although this
configuration is not officially supported and is recommended only for
development use. Without reworking Tornado IOLoop interface, it's not
possible to add a native Tornado Windows IOLoop implementation or
leverage Windows' IOCP support from frameworks like AsyncIO or Twisted.

Documentation
-------------

This documentation is also available in `PDF and Epub formats
<https://readthedocs.org/projects/tornado/downloads/>`_.

.. toctree::
   :titlesonly:

   guide
   webframework
   http
   networking
   coroutine
   integration
   utilities
   faq
   releases

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Discussion and support
----------------------

You can discuss Tornado on `the Tornado developer mailing list
<http://groups.google.com/group/python-tornado>`_, and report bugs on
the `GitHub issue tracker
<https://github.com/tornadoweb/tornado/issues>`_.  Links to additional
resources can be found on the `Tornado wiki
<https://github.com/tornadoweb/tornado/wiki/Links>`_.  New releases are
announced on the `announcements mailing list
<http://groups.google.com/group/python-tornado-announce>`_.

Tornado is available under
the `Apache License, Version 2.0
<http://www.apache.org/licenses/LICENSE-2.0.html>`_.

This web site and all documentation is licensed under `Creative
Commons 3.0 <http://creativecommons.org/licenses/by/3.0/>`_.
