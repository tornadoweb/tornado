What's new in the next release of Tornado
=========================================

In progress
-----------

* The Tornado test suite now requires ``unittest2`` when run on Python 2.5
  or 2.6.
* `tornado.testing.AsyncTestCase` and friends now extend ``unittest2.TestCase``
  when it is available (and continue to use the standard ``unittest`` module
  when ``unittest2`` is not available)
* `tornado.netutil.bind_sockets` no longer sets ``AI_ADDRCONFIG``; this will
  cause it to bind to both ipv4 and ipv6 more often than before.
* `tornado.netutil.bind_sockets` has a new ``flags`` argument that can
  be used to pass additional flags to ``getaddrinfo``.
