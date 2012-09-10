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
* Tornado no longer logs to the root logger.  Details on the new logging
  scheme can be found under the `tornado.log` module.  Note that in some
  cases this will require that you add an explicit logging configuration
  in ordre to see any output (perhaps just calling ``logging.basicConfig()``),
  although both `IOLoop.start()` and `tornado.options.parse_command_line`
  will do this for you.
* Errors while rendering templates no longer log the generated code,
  since the enhanced stack traces (from version 2.1) should make this
  unnecessary.
* `tornado.testing.ExpectLog` can be used as a finer-grained alternative
  to `tornado.testing.LogTrapTestCase`
