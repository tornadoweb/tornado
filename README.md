Tornado
=======
Tornado is an open source version of the scalable, non-blocking web server
and and tools that power FriendFeed. Documentation and downloads are
available at http://www.tornadoweb.org/

Tornado is licensed under the Apache Licence, Version 2.0
(http://www.apache.org/licenses/LICENSE-2.0.html).

Automatic installation
----------------------

 Tornado is listed in PyPI and can be installed with pip or
easy_install. Note that the source distribution includes demo
applications that are not present when Tornado is installed in this
way, so you may wish to download a copy of the source tarball as well.

Manual installation
-------------------

Download the latest release from http://pypi.python.org/pypi/tornado

    tar xvzf tornado-$VERSION.tar.gz
    cd tornado-$VERSION
    python setup.py build
    sudo python setup.py install

The Tornado source code is hosted on GitHub: https://github.com/facebook/tornado

On Python 2.6 and 2.7, it is also possible to simply add the tornado
directory to your PYTHONPATH instead of building with setup.py, since
the standard library includes epoll support.

Prerequisites
-------------

Tornado runs on Python 2.6+ and 3.2+.  Both CPython and PyPy are supported.

There are no required dependencies outside the Python standard library,
although unittest2 is required to run Tornado's unittest suite on
Python 2.6.

Certain optional features require additional third-party modules:

* tornado.curl_httpclient needs PycURL (version 7.18.2 or higher required;
  version 7.21.1 or higher recommended)
* Multithreading support requires the concurrent.futures module,
  which is in the standard library for Python 3.2+ and available
  at http://pypi.python.org/pypi/futures for older versions.

Platforms
---------

Tornado should run on any Unix-like platform, although for the best
performance and scalability only Linux and BSD (including BSD
derivatives like Mac OS X) are recommended.
