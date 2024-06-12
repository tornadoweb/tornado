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
