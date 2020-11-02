``tornado.platform.twisted`` --- Bridges between Twisted and Tornado
====================================================================

.. module:: tornado.platform.twisted

.. deprecated:: 6.0

   This module is no longer recommended for new code. Instead of using
   direct integration between Tornado and Twisted, new applications should
   rely on the integration with ``asyncio`` provided by both packages.

Importing this module has the side effect of registering Twisted's ``Deferred``
class with Tornado's ``@gen.coroutine`` so that ``Deferred`` objects can be
used with ``yield`` in coroutines using this decorator (importing this module has
no effect on native coroutines using ``async def``). 

.. function:: install()

    Install ``AsyncioSelectorReactor`` as the default Twisted reactor.

    .. deprecated:: 5.1

       This function is provided for backwards compatibility; code
       that does not require compatibility with older versions of
       Tornado should use
       ``twisted.internet.asyncioreactor.install()`` directly.

    .. versionchanged:: 6.0.3

       In Tornado 5.x and before, this function installed a reactor
       based on the Tornado ``IOLoop``. When that reactor
       implementation was removed in Tornado 6.0.0, this function was
       removed as well. It was restored in Tornado 6.0.3 using the
       ``asyncio`` reactor instead.

Twisted DNS resolver
--------------------

.. class:: TwistedResolver

    Twisted-based asynchronous resolver.

    This is a non-blocking and non-threaded resolver.  It is
    recommended only when threads cannot be used, since it has
    limitations compared to the standard ``getaddrinfo``-based
    `~tornado.netutil.Resolver` and
    `~tornado.netutil.DefaultExecutorResolver`.  Specifically, it returns at
    most one result, and arguments other than ``host`` and ``family``
    are ignored.  It may fail to resolve when ``family`` is not
    ``socket.AF_UNSPEC``.

    Requires Twisted 12.1 or newer.

    .. versionchanged:: 5.0
       The ``io_loop`` argument (deprecated since version 4.1) has been removed.
