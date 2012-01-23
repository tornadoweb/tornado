``tornado.platform.twisted`` --- Run code written for Twisted on Tornado
========================================================================

.. module:: tornado.platform.twisted

This module contains a Twisted reactor build on the Tornado IOLoop,
which lets you run applications and libraries written for Twisted in a
Tornado application.  To use it, simply call `install` at the
beginning of the application::

    import tornado.platform.twisted
    tornado.platform.twisted.install()
    from twisted.internet import reactor

When the app is ready to start, call `IOLoop.instance().start()`
instead of `reactor.run()`.  This will allow you to use a mixture of
Twisted and Tornado code in the same process.

It is also possible to create a non-global reactor by calling
`tornado.platform.twisted.TornadoReactor(io_loop)`.  However, if
the `IOLoop` and reactor are to be short-lived (such as those used in
unit tests), additional cleanup may be required.  Specifically, it is
recommended to call::

    reactor.fireSystemEvent('shutdown')
    reactor.disconnectAll()

before closing the `IOLoop`.

This module has been tested with Twisted versions 11.0.0 and 11.1.0.

.. function:: install(io_loop=None)

Install this package as the default Twisted reactor.

.. class:: TornadoReactor(io_loop=None)

Twisted reactor built on the Tornado IOLoop.

Since it is intented to be used in applications where the top-level
event loop is ``io_loop.start()`` rather than ``reactor.run()``,
it is implemented a little differently than other Twisted reactors.
We override `mainLoop` instead of `doIteration` and must implement
timed call functionality on top of `IOLoop.add_timeout` rather than
using the implementation in `PosixReactorBase`.
