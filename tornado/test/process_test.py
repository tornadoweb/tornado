#!/usr/bin/env python

import logging
import os
import signal
from tornado.httpclient import HTTPClient, HTTPError
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from tornado.process import fork_processes, task_id
from tornado.testing import LogTrapTestCase, get_unused_port
from tornado.web import RequestHandler, Application

# Not using AsyncHTTPTestCase because we need control over the IOLoop.
# Logging is tricky here so you may want to replace LogTrapTestCase
# with unittest.TestCase when debugging.
class ProcessTest(LogTrapTestCase):
    def get_app(self):
        class ProcessHandler(RequestHandler):
            def get(self):
                if self.get_argument("exit", None):
                    # must use os._exit instead of sys.exit so unittest's
                    # exception handler doesn't catch it
                    os._exit(int(self.get_argument("exit")))
                if self.get_argument("signal", None):
                    os.kill(os.getpid(),
                            int(self.get_argument("signal")))
                self.write(str(os.getpid()))
        return Application([("/", ProcessHandler)])

    def tearDown(self):
        if task_id() is not None:
            # We're in a child process, and probably got to this point
            # via an uncaught exception.  If we return now, both
            # processes will continue with the rest of the test suite.
            # Exit now so the parent process will restart the child
            # (since we don't have a clean way to signal failure to
            # the parent that won't restart)
            logging.error("aborting child process from tearDown")
            logging.shutdown()
            os._exit(1)
        super(ProcessTest, self).tearDown()

    def test_multi_process(self):
        self.assertFalse(IOLoop.initialized())
        port = get_unused_port()
        def get_url(path):
            return "http://127.0.0.1:%d%s" % (port, path)
        sockets = bind_sockets(port, "127.0.0.1")
        # ensure that none of these processes live too long
        signal.alarm(5)  # master process
        id = fork_processes(3, max_restarts=3)
        if id is None:
            # back in the master process; everything worked!
            self.assertTrue(task_id() is None)
            for sock in sockets: sock.close()
            signal.alarm(0)
            return
        signal.alarm(5)  # child process
        try:
            if id in (0, 1):
                signal.alarm(5)
                self.assertEqual(id, task_id())
                server = HTTPServer(self.get_app())
                server.add_sockets(sockets)
                IOLoop.instance().start()
            elif id == 2:
                signal.alarm(5)
                self.assertEqual(id, task_id())
                for sock in sockets: sock.close()
                client = HTTPClient()

                def fetch(url, fail_ok=False):
                    try:
                        return client.fetch(get_url(url))
                    except HTTPError, e:
                        if not (fail_ok and e.code == 599):
                            raise

                # Make two processes exit abnormally
                fetch("/?exit=2", fail_ok=True)
                fetch("/?exit=3", fail_ok=True)

                # They've been restarted, so a new fetch will work
                int(fetch("/").body)

                # Now the same with signals
                # Disabled because on the mac a process dying with a signal
                # can trigger an "Application exited abnormally; send error
                # report to Apple?" prompt.
                #fetch("/?signal=%d" % signal.SIGTERM, fail_ok=True)
                #fetch("/?signal=%d" % signal.SIGABRT, fail_ok=True)
                #int(fetch("/").body)

                # Now kill them normally so they won't be restarted
                fetch("/?exit=0", fail_ok=True)
                # One process left; watch it's pid change
                pid = int(fetch("/").body)
                fetch("/?exit=4", fail_ok=True)
                pid2 = int(fetch("/").body)
                self.assertNotEqual(pid, pid2)

                # Kill the last one so we shut down cleanly
                fetch("/?exit=0", fail_ok=True)

                os._exit(0)
        except Exception:
            logging.error("exception in child process %d", id, exc_info=True)
            raise
            

if os.name != 'posix':
    # All sorts of unixisms here
    del ProcessTest
