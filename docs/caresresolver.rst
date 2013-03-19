``tornado.platform.caresresolver`` --- Asynchronous DNS Resolver using C-Ares
=============================================================================

.. module:: tornado.platform.caresresolver

This module contains a DNS resolver using the c-ares library (and its
wrapper ``pycares``).

.. py:class:: CaresResolver

    Name resolver based on the c-ares library.

    This is a non-blocking and non-threaded resolver.  It may not produce
    the same results as the system resolver, but can be used for non-blocking
    resolution when threads cannot be used.

    c-ares fails to resolve some names when ``family`` is ``AF_UNSPEC``,
    so it is only recommended for use in ``AF_INET`` (i.e. IPv4).  This is
    the default for ``tornado.simple_httpclient``, but other libraries
    may default to ``AF_UNSPEC``.
