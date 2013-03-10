``tornado.platform.twisted`` --- Bridges between Twisted and Tornado
========================================================================

.. module:: tornado.platform.twisted

This module lets you run applications and libraries written for
Twisted in a Tornado application.  It can be used in two modes,
depending on which library's underlying event loop you want to use.

Twisted on Tornado
------------------

`TornadoReactor` implements the Twisted reactor interface on top of
the Tornado IOLoop.  To use it, simply call `install` at the beginning
of the application::

    import tornado.platform.twisted
    tornado.platform.twisted.install()
    from twisted.internet import reactor

When the app is ready to start, call `IOLoop.instance().start()`
instead of `reactor.run()`.

It is also possible to create a non-global reactor by calling
`tornado.platform.twisted.TornadoReactor(io_loop)`.  However, if
the `IOLoop` and reactor are to be short-lived (such as those used in
unit tests), additional cleanup may be required.  Specifically, it is
recommended to call::

    reactor.fireSystemEvent('shutdown')
    reactor.disconnectAll()

before closing the `IOLoop`.

Tornado on Twisted
------------------

`TwistedIOLoop` implements the Tornado IOLoop interface on top of the Twisted
reactor.  Recommended usage::

    from tornado.platform.twisted import TwistedIOLoop
    from twisted.internet import reactor
    TwistedIOLoop().install()
    # Set up your tornado application as usual using `IOLoop.instance`
    reactor.run()

`TwistedIOLoop` always uses the global Twisted reactor.

This module has been tested with Twisted versions 11.0.0 and newer.
