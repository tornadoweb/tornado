#!/usr/bin/env python
"""Support classes for automated testing.

This module contains three parts:

* `AsyncTestCase`/`AsyncHTTPTestCase`:  Subclasses of unittest.TestCase
  with additional support for testing asynchronous (IOLoop-based) code.

* `LogTrapTestCase`:  Subclass of unittest.TestCase that discards log output
  from tests that pass and only produces output for failing tests.

* `main()`: A simple test runner (wrapper around unittest.main()) with support
  for the tornado.autoreload module to rerun the tests when code changes.

These components may be used together or independently.  In particular,
it is safe to combine AsyncTestCase and LogTrapTestCase via multiple
inheritance.  See the docstrings for each class/function below for more
information.
"""

from __future__ import absolute_import, division, with_statement

from cStringIO import StringIO
try:
    from tornado.httpclient import AsyncHTTPClient
    from tornado.httpserver import HTTPServer
    from tornado.simple_httpclient import SimpleAsyncHTTPClient
    from tornado.ioloop import IOLoop
    from tornado import netutil
except ImportError:
    # These modules are not importable on app engine.  Parts of this module
    # won't work, but e.g. LogTrapTestCase and main() will.
    AsyncHTTPClient = None
    HTTPServer = None
    IOLoop = None
    netutil = None
    SimpleAsyncHTTPClient = None
from tornado.log import gen_log
from tornado.stack_context import ExceptionStackContext
from tornado.util import raise_exc_info
import logging
import os
import re
import signal
import socket
import sys
import time

# Tornado's own test suite requires the updated unittest module
# (either py27+ or unittest2) so tornado.test.util enforces
# this requirement, but for other users of tornado.testing we want
# to allow the older version if unitest2 is not available.
try:
    import unittest2 as unittest
except ImportError:
    import unittest

_next_port = 10000


def get_unused_port():
    """Returns a (hopefully) unused port number.

    This function does not guarantee that the port it returns is available,
    only that a series of get_unused_port calls in a single process return
    distinct ports.

    **Deprecated**.  Use bind_unused_port instead, which is guaranteed
    to find an unused port.
    """
    global _next_port
    port = _next_port
    _next_port = _next_port + 1
    return port


def bind_unused_port():
    """Binds a server socket to an available port on localhost.

    Returns a tuple (socket, port).
    """
    [sock] = netutil.bind_sockets(0, 'localhost', family=socket.AF_INET)
    port = sock.getsockname()[1]
    return sock, port


class AsyncTestCase(unittest.TestCase):
    """TestCase subclass for testing IOLoop-based asynchronous code.

    The unittest framework is synchronous, so the test must be complete
    by the time the test method returns.  This method provides the stop()
    and wait() methods for this purpose.  The test method itself must call
    self.wait(), and asynchronous callbacks should call self.stop() to signal
    completion.

    By default, a new IOLoop is constructed for each test and is available
    as self.io_loop.  This IOLoop should be used in the construction of
    HTTP clients/servers, etc.  If the code being tested requires a
    global IOLoop, subclasses should override get_new_ioloop to return it.

    The IOLoop's start and stop methods should not be called directly.
    Instead, use self.stop self.wait.  Arguments passed to self.stop are
    returned from self.wait.  It is possible to have multiple
    wait/stop cycles in the same test.

    Example::

        # This test uses an asynchronous style similar to most async
        # application code.
        class MyTestCase(AsyncTestCase):
            def test_http_fetch(self):
                client = AsyncHTTPClient(self.io_loop)
                client.fetch("http://www.tornadoweb.org/", self.handle_fetch)
                self.wait()

            def handle_fetch(self, response):
                # Test contents of response (failures and exceptions here
                # will cause self.wait() to throw an exception and end the
                # test).
                # Exceptions thrown here are magically propagated to
                # self.wait() in test_http_fetch() via stack_context.
                self.assertIn("FriendFeed", response.body)
                self.stop()

        # This test uses the argument passing between self.stop and self.wait
        # for a simpler, more synchronous style.
        # This style is recommended over the preceding example because it
        # keeps the assertions in the test method itself, and is therefore
        # less sensitive to the subtleties of stack_context.
        class MyTestCase2(AsyncTestCase):
            def test_http_fetch(self):
                client = AsyncHTTPClient(self.io_loop)
                client.fetch("http://www.tornadoweb.org/", self.stop)
                response = self.wait()
                # Test contents of response
                self.assertIn("FriendFeed", response.body)
    """
    def __init__(self, *args, **kwargs):
        super(AsyncTestCase, self).__init__(*args, **kwargs)
        self.__stopped = False
        self.__running = False
        self.__failure = None
        self.__stop_args = None
        self.__timeout = None

    def setUp(self):
        super(AsyncTestCase, self).setUp()
        self.io_loop = self.get_new_ioloop()
        self.io_loop.make_current()

    def tearDown(self):
        self.io_loop.clear_current()
        if (not IOLoop.initialized() or
            self.io_loop is not IOLoop.instance()):
            # Try to clean up any file descriptors left open in the ioloop.
            # This avoids leaks, especially when tests are run repeatedly
            # in the same process with autoreload (because curl does not
            # set FD_CLOEXEC on its file descriptors)
            self.io_loop.close(all_fds=True)
        super(AsyncTestCase, self).tearDown()

    def get_new_ioloop(self):
        '''Creates a new IOLoop for this test.  May be overridden in
        subclasses for tests that require a specific IOLoop (usually
        the singleton).
        '''
        return IOLoop()

    def _handle_exception(self, typ, value, tb):
        self.__failure = sys.exc_info()
        self.stop()
        return True

    def __rethrow(self):
        if self.__failure is not None:
            failure = self.__failure
            self.__failure = None
            raise_exc_info(failure)

    def run(self, result=None):
        with ExceptionStackContext(self._handle_exception):
            super(AsyncTestCase, self).run(result)
        # In case an exception escaped super.run or the StackContext caught
        # an exception when there wasn't a wait() to re-raise it, do so here.
        self.__rethrow()

    def stop(self, _arg=None, **kwargs):
        '''Stops the ioloop, causing one pending (or future) call to wait()
        to return.

        Keyword arguments or a single positional argument passed to stop() are
        saved and will be returned by wait().
        '''
        assert _arg is None or not kwargs
        self.__stop_args = kwargs or _arg
        if self.__running:
            self.io_loop.stop()
            self.__running = False
        self.__stopped = True

    def wait(self, condition=None, timeout=5):
        """Runs the IOLoop until stop is called or timeout has passed.

        In the event of a timeout, an exception will be thrown.

        If condition is not None, the IOLoop will be restarted after stop()
        until condition() returns true.
        """
        if not self.__stopped:
            if timeout:
                def timeout_func():
                    try:
                        raise self.failureException(
                          'Async operation timed out after %s seconds' %
                          timeout)
                    except Exception:
                        self.__failure = sys.exc_info()
                    self.stop()
                if self.__timeout is not None:
                    self.io_loop.remove_timeout(self.__timeout)
                self.__timeout = self.io_loop.add_timeout(self.io_loop.time() + timeout, timeout_func)
            while True:
                self.__running = True
                self.io_loop.start()
                if (self.__failure is not None or
                    condition is None or condition()):
                    break
        assert self.__stopped
        self.__stopped = False
        self.__rethrow()
        result = self.__stop_args
        self.__stop_args = None
        return result


class AsyncHTTPTestCase(AsyncTestCase):
    '''A test case that starts up an HTTP server.

    Subclasses must override get_app(), which returns the
    tornado.web.Application (or other HTTPServer callback) to be tested.
    Tests will typically use the provided self.http_client to fetch
    URLs from this server.

    Example::

        class MyHTTPTest(AsyncHTTPTestCase):
            def get_app(self):
                return Application([('/', MyHandler)...])

            def test_homepage(self):
                # The following two lines are equivalent to
                #   response = self.fetch('/')
                # but are shown in full here to demonstrate explicit use
                # of self.stop and self.wait.
                self.http_client.fetch(self.get_url('/'), self.stop)
                response = self.wait()
                # test contents of response
    '''
    def setUp(self):
        super(AsyncHTTPTestCase, self).setUp()
        sock, port = bind_unused_port()
        self.__port = port

        self.http_client = self.get_http_client()
        self._app = self.get_app()
        self.http_server = self.get_http_server()
        self.http_server.add_sockets([sock])

    def get_http_client(self):
        return AsyncHTTPClient(io_loop=self.io_loop)

    def get_http_server(self):
        return HTTPServer(self._app, io_loop=self.io_loop,
                          **self.get_httpserver_options())

    def get_app(self):
        """Should be overridden by subclasses to return a
        tornado.web.Application or other HTTPServer callback.
        """
        raise NotImplementedError()

    def fetch(self, path, **kwargs):
        """Convenience method to synchronously fetch a url.

        The given path will be appended to the local server's host and port.
        Any additional kwargs will be passed directly to
        AsyncHTTPClient.fetch (and so could be used to pass method="POST",
        body="...", etc).
        """
        self.http_client.fetch(self.get_url(path), self.stop, **kwargs)
        return self.wait()

    def get_httpserver_options(self):
        """May be overridden by subclasses to return additional
        keyword arguments for the server.
        """
        return {}

    def get_http_port(self):
        """Returns the port used by the server.

        A new port is chosen for each test.
        """
        return self.__port

    def get_protocol(self):
        return 'http'

    def get_url(self, path):
        """Returns an absolute url for the given path on the test server."""
        return '%s://localhost:%s%s' % (self.get_protocol(),
                                        self.get_http_port(), path)

    def tearDown(self):
        self.http_server.stop()
        if (not IOLoop.initialized() or
            self.http_client.io_loop is not IOLoop.instance()):
            self.http_client.close()
        super(AsyncHTTPTestCase, self).tearDown()


class AsyncHTTPSTestCase(AsyncHTTPTestCase):
    """A test case that starts an HTTPS server.

    Interface is generally the same as `AsyncHTTPTestCase`.
    """
    def get_http_client(self):
        # Some versions of libcurl have deadlock bugs with ssl,
        # so always run these tests with SimpleAsyncHTTPClient.
        return SimpleAsyncHTTPClient(io_loop=self.io_loop, force_instance=True,
                                     defaults=dict(validate_cert=False))

    def get_httpserver_options(self):
        return dict(ssl_options=self.get_ssl_options())

    def get_ssl_options(self):
        """May be overridden by subclasses to select SSL options.

        By default includes a self-signed testing certificate.
        """
        # Testing keys were generated with:
        # openssl req -new -keyout tornado/test/test.key -out tornado/test/test.crt -nodes -days 3650 -x509
        module_dir = os.path.dirname(__file__)
        return dict(
                certfile=os.path.join(module_dir, 'test', 'test.crt'),
                keyfile=os.path.join(module_dir, 'test', 'test.key'))

    def get_protocol(self):
        return 'https'


class LogTrapTestCase(unittest.TestCase):
    """A test case that captures and discards all logging output
    if the test passes.

    Some libraries can produce a lot of logging output even when
    the test succeeds, so this class can be useful to minimize the noise.
    Simply use it as a base class for your test case.  It is safe to combine
    with AsyncTestCase via multiple inheritance
    ("class MyTestCase(AsyncHTTPTestCase, LogTrapTestCase):")

    This class assumes that only one log handler is configured and that
    it is a StreamHandler.  This is true for both logging.basicConfig
    and the "pretty logging" configured by tornado.options.
    """
    def run(self, result=None):
        logger = logging.getLogger()
        if len(logger.handlers) > 1:
            # Multiple handlers have been defined.  It gets messy to handle
            # this, especially since the handlers may have different
            # formatters.  Just leave the logging alone in this case.
            super(LogTrapTestCase, self).run(result)
            return
        if not logger.handlers:
            logging.basicConfig()
        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        old_stream = handler.stream
        try:
            handler.stream = StringIO()
            gen_log.info("RUNNING TEST: " + str(self))
            old_error_count = len(result.failures) + len(result.errors)
            super(LogTrapTestCase, self).run(result)
            new_error_count = len(result.failures) + len(result.errors)
            if new_error_count != old_error_count:
                old_stream.write(handler.stream.getvalue())
        finally:
            handler.stream = old_stream


class ExpectLog(logging.Filter):
    """Context manager to capture and suppress expected log output.

    Useful to make tests of error conditions less noisy, while still
    leaving unexpected log entries visible.  *Not thread safe.*

    Usage::

        with ExpectLog('tornado.application', "Uncaught exception"):
            error_response = self.fetch("/some_page")
    """
    def __init__(self, logger, regex, required=True):
        """Constructs an ExpectLog context manager.

        :param logger: Logger object (or name of logger) to watch.  Pass
            an empty string to watch the root logger.
        :param regex: Regular expression to match.  Any log entries on
            the specified logger that match this regex will be suppressed.
        :param required: If true, an exeption will be raised if the end of
            the ``with`` statement is reached without matching any log entries.
        """
        if isinstance(logger, basestring):
            logger = logging.getLogger(logger)
        self.logger = logger
        self.regex = re.compile(regex)
        self.required = required
        self.matched = False

    def filter(self, record):
        message = record.getMessage()
        if self.regex.match(message):
            self.matched = True
            return False
        return True

    def __enter__(self):
        self.logger.addFilter(self)

    def __exit__(self, typ, value, tb):
        self.logger.removeFilter(self)
        if not typ and self.required and not self.matched:
            raise Exception("did not get expected log message")


def main(**kwargs):
    """A simple test runner.

    This test runner is essentially equivalent to `unittest.main` from
    the standard library, but adds support for tornado-style option
    parsing and log formatting.

    The easiest way to run a test is via the command line::

        python -m tornado.testing tornado.test.stack_context_test

    See the standard library unittest module for ways in which tests can
    be specified.

    Projects with many tests may wish to define a test script like
    tornado/test/runtests.py.  This script should define a method all()
    which returns a test suite and then call tornado.testing.main().
    Note that even when a test script is used, the all() test suite may
    be overridden by naming a single test on the command line::

        # Runs all tests
        python -m tornado.test.runtests
        # Runs one test
        python -m tornado.test.runtests tornado.test.stack_context_test

    Additional keyword arguments passed through to ``unittest.main()``.
    For example, use ``tornado.testing.main(verbosity=2)``
    to show many test details as they are run.
    See http://docs.python.org/library/unittest.html#unittest.main
    for full argument list.
    """
    from tornado.options import define, options, parse_command_line

    define('exception_on_interrupt', type=bool, default=True,
           help=("If true (default), ctrl-c raises a KeyboardInterrupt "
                 "exception.  This prints a stack trace but cannot interrupt "
                 "certain operations.  If false, the process is more reliably "
                 "killed, but does not print a stack trace."))

    # support the same options as unittest's command-line interface
    define('verbose', type=bool)
    define('quiet', type=bool)
    define('failfast', type=bool)
    define('catch', type=bool)
    define('buffer', type=bool)

    argv = [sys.argv[0]] + parse_command_line(sys.argv)

    if not options.exception_on_interrupt:
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    if options.verbose is not None:
        kwargs['verbosity'] = 2
    if options.quiet is not None:
        kwargs['verbosity'] = 0
    if options.failfast is not None:
        kwargs['failfast'] = True
    if options.catch is not None:
        kwargs['catchbreak'] = True
    if options.buffer is not None:
        kwargs['buffer'] = True

    if __name__ == '__main__' and len(argv) == 1:
        print >> sys.stderr, "No tests specified"
        sys.exit(1)
    try:
        # In order to be able to run tests by their fully-qualified name
        # on the command line without importing all tests here,
        # module must be set to None.  Python 3.2's unittest.main ignores
        # defaultTest if no module is given (it tries to do its own
        # test discovery, which is incompatible with auto2to3), so don't
        # set module if we're not asking for a specific test.
        if len(argv) > 1:
            unittest.main(module=None, argv=argv, **kwargs)
        else:
            unittest.main(defaultTest="all", argv=argv, **kwargs)
    except SystemExit, e:
        if e.code == 0:
            gen_log.info('PASS')
        else:
            gen_log.error('FAIL')
        raise

if __name__ == '__main__':
    main()
