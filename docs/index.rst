.. title:: Tornado Web Server

.. meta::
    :google-site-verification: g4bVhgwbVO1d9apCUsT-eKlApg31Cygbp8VGZY8Rf0g

|Tornado Web Server|
====================

.. |Tornado Web Server| image:: tornado.png
    :alt: Tornado Web Server

`Tornado <https://www.tornadoweb.org>`_ is a Python web framework and
asynchronous networking library, originally developed at `FriendFeed
<https://en.wikipedia.org/wiki/FriendFeed>`_.  By using non-blocking network I/O, Tornado
can scale to tens of thousands of open connections, making it ideal for
`long polling <https://en.wikipedia.org/wiki/Push_technology#Long_polling>`_,
`WebSockets <https://en.wikipedia.org/wiki/WebSocket>`_, and other
applications that require a long-lived connection to each user.

Quick links
-----------

* Current version: |version| (`download from PyPI <https://pypi.python.org/pypi/tornado>`_, :doc:`release notes <releases>`)
* `Source (GitHub) <https://github.com/tornadoweb/tornado>`_
* Mailing lists: `discussion <https://groups.google.com/forum/#!forum/python-tornado>`_ and `announcements <https://groups.google.com/forum/#!forum/python-tornado-announce>`_
* `Stack Overflow <https://stackoverflow.com/questions/tagged/tornado>`_
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

Threads and WSGI
----------------

Tornado is different from most Python web frameworks. It is not based
on `WSGI <https://wsgi.readthedocs.io/en/latest/>`_, and it is
typically run with only one thread per process. See the :doc:`guide`
for more on Tornado's approach to asynchronous programming.

While some support of WSGI is available in the `tornado.wsgi` module,
it is not a focus of development and most applications should be
written to use Tornado's own interfaces (such as `tornado.web`)
directly instead of using WSGI.

In general, Tornado code is not thread-safe. The only method in
Tornado that is safe to call from other threads is
`.IOLoop.add_callback`. You can also use `.IOLoop.run_in_executor` to
asynchronously run a blocking function on another thread, but note
that the function passed to ``run_in_executor`` should avoid
referencing any Tornado objects. ``run_in_executor`` is the
recommended way to interact with blocking code.

``asyncio`` Integration
-----------------------

Tornado is integrated with the standard library `asyncio` module and
shares the same event loop (by default since Tornado 5.0). In general,
libraries designed for use with `asyncio` can be mixed freely with
Tornado.


Installation
------------

::

    pip install tornado

Tornado is listed in `PyPI <https://pypi.org/project/tornado/>`_ and
can be installed with ``pip``. Note that the source distribution
includes demo applications that are not present when Tornado is
installed in this way, so you may wish to download a copy of the
source tarball or clone the `git repository
<https://github.com/tornadoweb/tornado>`_ as well.

**Prerequisites**: Tornado 6.0 requires Python 3.5.2 or newer (See
`Tornado 5.1 <https://www.tornadoweb.org/en/branch5.1/>`_ if
compatibility with Python 2.7 is required). The following optional
packages may be useful:

* `pycurl <http://pycurl.io/>`_ is used by the optional
  ``tornado.curl_httpclient``.  Libcurl version 7.22 or higher is required.
* `Twisted <https://www.twistedmatrix.com/>`_ may be used with the classes in
  `tornado.platform.twisted`.
* `pycares <https://pypi.org/project/pycares/>`_ is an alternative
  non-blocking DNS resolver that can be used when threads are not
  appropriate.

**Platforms**: Tornado is designed for Unix-like platforms, with best
performance and scalability on systems supporting ``epoll`` (Linux),
``kqueue`` (BSD/macOS), or ``/dev/poll`` (Solaris).

Tornado will also run on Windows, although this configuration is not
officially supported or recommended for production use. Some features
are missing on Windows (including multi-process mode) and scalability
is limited (Even though Tornado is built on ``asyncio``, which
supports Windows, Tornado does not use the APIs that are necessary for
scalable networking on Windows).

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
<https://groups.google.com/forum/#!forum/python-tornado>`_, and report bugs on
the `GitHub issue tracker
<https://github.com/tornadoweb/tornado/issues>`_.  Links to additional
resources can be found on the `Tornado wiki
<https://github.com/tornadoweb/tornado/wiki/Links>`_.  New releases are
announced on the `announcements mailing list
<https://groups.google.com/forum/#!forum/python-tornado-announce>`_.

Tornado is available under
the `Apache License, Version 2.0
<http://www.apache.org/licenses/LICENSE-2.0.html>`_.

This web site and all documentation is licensed under `Creative
Commons 3.0 <https://creativecommons.org/licenses/by/3.0/>`_.
