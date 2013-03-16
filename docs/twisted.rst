``tornado.platform.twisted`` --- Bridges between Twisted and Tornado
========================================================================

.. module:: tornado.platform.twisted

This module lets you run applications and libraries written for
Twisted in a Tornado application.  It can be used in two modes,
depending on which library's underlying event loop you want to use.

This module has been tested with Twisted versions 11.0.0 and newer.

Twisted on Tornado
------------------

.. py:class:: TornadoReactor

    ``TornadoReactor`` implements the Twisted reactor interface on top of
    the Tornado IOLoop.  To use it, simply call ``install`` at the beginning
    of the application::

        import tornado.platform.twisted
        tornado.platform.twisted.install()
        from twisted.internet import reactor

    When the app is ready to start, call ``IOLoop.instance().start()``
    instead of ``reactor.run()``.

    It is also possible to create a non-global reactor by calling
    ``tornado.platform.twisted.TornadoReactor(io_loop)``.  However, if
    the `.IOLoop` and reactor are to be short-lived (such as those used in
    unit tests), additional cleanup may be required.  Specifically, it is
    recommended to call::

        reactor.fireSystemEvent('shutdown')
        reactor.disconnectAll()

    before closing the `.IOLoop`.

Tornado on Twisted
------------------

.. py:class:: TwistedIOLoop

    ``TwistedIOLoop`` implements the Tornado IOLoop interface on top
    of the Twisted reactor.  Recommended usage::

        from tornado.platform.twisted import TwistedIOLoop
        from twisted.internet import reactor
        TwistedIOLoop().install()
        # Set up your tornado application as usual using `IOLoop.instance`
        reactor.run()

    ``TwistedIOLoop`` always uses the global Twisted reactor.

Twisted DNS resolver
--------------------

.. py:class:: TwistedResolver

    This is a non-blocking and non-threaded resolver.  It is
    recommended only when threads cannot be used, since it has
    limitations compared to the standard ``getaddrinfo``-based
    `~tornado.netutil.Resolver` and
    `~tornado.netutil.ThreadedResolver`.  Specifically, it returns at
    most one result, and arguments other than ``host`` and ``family``
    are ignored.  It may fail to resolve when ``family`` is not
    ``socket.AF_UNSPEC``.

    Requires Twisted 12.1 or newer.
