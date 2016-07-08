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

* |Download current version|: :current_tarball:`z` (:doc:`release notes <releases>`)
* `Source (github) <https://github.com/tornadoweb/tornado>`_
* Mailing lists: `discussion <http://groups.google.com/group/python-tornado>`_ and `announcements <http://groups.google.com/group/python-tornado-announce>`_
* `Stack Overflow <http://stackoverflow.com/questions/tagged/tornado>`_
* `Wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_

.. |Download current version| replace:: Download version |version|

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

**Automatic installation**::

    pip install tornado

Tornado is listed in `PyPI <http://pypi.python.org/pypi/tornado>`_ and
can be installed with ``pip`` or ``easy_install``.  Note that the
source distribution includes demo applications that are not present
when Tornado is installed in this way, so you may wish to download a
copy of the source tarball as well.

**Manual installation**: Download :current_tarball:`z`:

.. parsed-literal::

    tar xvzf tornado-|version|.tar.gz
    cd tornado-|version|
    python setup.py build
    sudo python setup.py install

The Tornado source code is `hosted on GitHub
<https://github.com/tornadoweb/tornado>`_.

**Prerequisites**: Tornado 4.3 runs on Python 2.7, and 3.3+
For Python 2, version 2.7.9 or newer is *strongly*
recommended for the improved SSL support. In addition to the requirements
which will be installed automatically by ``pip`` or ``setup.py install``,
the following optional packages may be useful:

* `concurrent.futures <https://pypi.python.org/pypi/futures>`_ is the
  recommended thread pool for use with Tornado and enables the use of
  `~tornado.netutil.ThreadedResolver`.  It is needed only on Python 2;
  Python 3 includes this package in the standard library.
* `pycurl <http://pycurl.sourceforge.net>`_ is used by the optional
  ``tornado.curl_httpclient``.  Libcurl version 7.19.3.1 or higher is required;
  version 7.21.1 or higher is recommended.
* `Twisted <http://www.twistedmatrix.com>`_ may be used with the classes in
  `tornado.platform.twisted`.
* `pycares <https://pypi.python.org/pypi/pycares>`_ is an alternative
  non-blocking DNS resolver that can be used when threads are not
  appropriate.
* `monotonic <https://pypi.python.org/pypi/monotonic>`_ or `Monotime
  <https://pypi.python.org/pypi/Monotime>`_ add support for a
  monotonic clock, which improves reliability in environments where
  clock adjustements are frequent. No longer needed in Python 3.3.

**Platforms**: Tornado should run on any Unix-like platform, although
for the best performance and scalability only Linux (with ``epoll``)
and BSD (with ``kqueue``) are recommended for production deployment
(even though Mac OS X is derived from BSD and supports kqueue, its
networking performance is generally poor so it is recommended only for
development use).  Tornado will also run on Windows, although this
configuration is not officially supported and is recommended only for
development use.

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
