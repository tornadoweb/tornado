``tornado.platform.twisted`` --- Run code written for Twisted on Tornado
========================================================================

.. module:: tornado.platform.twisted

This module contains an implementation of the Twisted Reactor built
on the Tornado IOLoop.  This lets you run applications and libraries
written for Twisted in a Tornado application.  To use it, simply call
`install` at the beginnging of the application::

    import tornado.platform.twisted
    tornado.platform.twisted.install()

    from twisted.internet import reactor
    ...

.. function:: install(io_loop=None)

   Installs this package as the default Twisted reactor.
