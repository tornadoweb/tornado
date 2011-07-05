#!/usr/bin/env python

import functools
import os
import signal
from tornado.httpclient import HTTPClient
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.netutil import bind_sockets
from tornado.process import fork_processes, task_id
from tornado.testing import LogTrapTestCase, get_unused_port
from tornado.web import RequestHandler, Application

# Not using AsyncHTTPTestCase because we need control over the IOLoop.
class ProcessTest(LogTrapTestCase):
    def get_app(self):
        class ProcessHandler(RequestHandler):
            def get(self):
                if self.get_argument("exit", None):
                    # must use os._exit instead of sys.exit so unittest's
                    # exception handler doesn't catch it
                    IOLoop.instance().add_callback(functools.partial(
                            os._exit, int(self.get_argument("exit"))))
                if self.get_argument("signal", None):
                    IOLoop.instance().add_callback(functools.partial(
                            os.kill, os.getpid(),
                            int(self.get_argument("signal"))))
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

            # Make both processes exit abnormally
            client.fetch(get_url("/?exit=2"))
            client.fetch(get_url("/?exit=3"))

            # They've been restarted, so a new fetch will work
            int(client.fetch(get_url("/")).body)
            
            # Now the same with signals
            # Disabled because on the mac a process dying with a signal
            # can trigger an "Application exited abnormally; send error
            # report to Apple?" prompt.
            #client.fetch(get_url("/?signal=%d" % signal.SIGTERM))
            #client.fetch(get_url("/?signal=%d" % signal.SIGABRT))
            #int(client.fetch(get_url("/")).body)

            # Now kill them normally so they won't be restarted
            client.fetch(get_url("/?exit=0"))
            # One process left; watch it's pid change
            pid = int(client.fetch(get_url("/")).body)
            client.fetch(get_url("/?exit=1"))
            pid2 = int(client.fetch(get_url("/")).body)
            self.assertNotEqual(pid, pid2)

            # Kill the last one so we shut down cleanly
            client.fetch(get_url("/?exit=0"))
            
            os._exit(0)
            

if os.name != 'posix':
    # All sorts of unixisms here
    del ProcessTest
