Tornado Web Server
==================

.. image:: tornado.png
    :alt: Tornado Web Server

`Tornado <http://www.tornadoweb.org/>`_ is an open source version of
the scalable, non-blocking web server and tools that power `FriendFeed
<http://friendfeed.com/>`_. The FriendFeed application is written
using a web framework that looks a bit like `web.py
<http://webpy.org/>`_ or `Google's webapp
<http://code.google.com/appengine/docs/python/tools/webapp/>`_, but
with additional tools and optimizations to take advantage of the
underlying non-blocking infrastructure.

The framework is distinct from most mainstream web server frameworks
(and certainly most Python frameworks) because it is non-blocking and
reasonably fast. Because it is non-blocking and uses `epoll
<http://www.kernel.org/doc/man-pages/online/pages/man4/epoll.4.html>`_
or ``kqueue``, it can handle thousands of simultaneous standing
connections, which means it is ideal for real-time web services. We
built the web server specifically to handle FriendFeed's real-time
features &mdash; every active user of FriendFeed maintains an open
connection to the FriendFeed servers. (For more information on scaling
servers to support thousands of clients, see The `C10K problem
<http://www.kegel.com/c10k.html>`_.)

Upgrading from Tornado 1.x
--------------------------

Tornado 2.0 introduces several potentially backwards-incompatible
changes, including in particular automatic escaping of template
output.  Users who are upgrading from Tornado 1.x should see the
`version 2.0 release notes </documentation/releases/v2.0.0.html>`_ for
information about backwards compatibility.

Quick links
-----------

* `Documentation <documentation.html>`_
* `Download version |version| <https://github.com/downloads/facebook/tornado/tornado-|version|.tar.gz>`_ (`release notes </documentation/releases.html>`_)
* `Source (github) <https://github.com/facebook/tornado>`_
* `Mailing list <http://groups.google.com/group/python-tornado>`_
* `Wiki <https://github.com/facebook/tornado/wiki/Links>`_

Hello, world
------------

Here is the canonical "Hello, world" example app for Tornado::

    import tornado.ioloop
    import tornado.web

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    application = tornado.web.Application([
        (r"/", MainHandler),
    ])

    if __name__ == "__main__":
        application.listen(8888)
        tornado.ioloop.IOLoop.instance().start()</code></pre>

See the `Tornado documentation </documentation/index.html>`_ for a
detailed walkthrough of the framework.

Installation
------------

**Automatic installation:** Tornado is listed in `PyPI
<http://pypi.python.org/pypi/tornado>`_ and can be installed with
``pip`` or ``easy_install``.  Note that the source distribution
includes demo applications that are not present when Tornado is
installed in this way, so you may wish to download a copy of the
source tarball as well.

**Manual installation:** Download `tornado-|version|.tar.gz <https://github.com/downloads/facebook/tornado/tornado-{{version}}.tar.gz>`_::

    tar xvzf tornado-|version|.tar.gz
    cd tornado-|version|
    python setup.py build
    sudo python setup.py install

The Tornado source code is `hosted on GitHub
<https://github.com/facebook/tornado>`_.  On Python 2.6 and 2.7, it is
also possible to simply add the tornado directory to your
``PYTHONPATH`` instead of building with ``setup.py``, since the
standard library includes ``epoll`` support.

**Prerequisites:** Tornado runs on Python 2.5, 2.6, 2.7 and 3.2.

* On Python 2.6 and 2.7, there are no dependencies outside the Python
  standard library, although `PycURL
  <http://pycurl.sourceforge.net/>`_ (version 7.18.2 or higher
  required; version 7.21.1 or higher recommended) may be used if
  desired.
* On Python 2.5, PycURL is required, along with `simplejson
  <http://pypi.python.org/pypi/simplejson/>`_ and the Python
  development headers (typically obtained by installing a package
  named something like ``python-dev`` from your operating system).
* On Python 3.2, the `distribute
  <http://pypi.python.org/pypi/distribute>`_ package is required.
  Note that Python 3 support is relatively new and may have bugs.

**Platforms:** Tornado should run on any Unix-like platform, although
for the best performance and scalability only Linux and BSD (including
BSD derivatives like Mac OS X) are recommended.

Discussion and support
----------------------

You can discuss Tornado and report bugs on `the Tornado developer
mailing list <http://groups.google.com/group/python-tornado>`_.  Links
to additional resources can be found on the `Tornado wiki
<https://github.com/facebook/tornado/wiki/Links>`_.

Tornado is one of `Facebook's open source technologies
<http://developers.facebook.com/opensource/>`_. It is available under
the `Apache License, Version 2.0
<http://www.apache.org/licenses/LICENSE-2.0.html>`_.

This web site and all documentation is licensed under `Creative
Commons 3.0 <http://creativecommons.org/licenses/by/3.0/>`_.

.. toctree::
   :hidden:

   documentation

