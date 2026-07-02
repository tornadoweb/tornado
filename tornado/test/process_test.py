import os
import signal
import subprocess
import sys
import time
import unittest

from tornado import gen
from tornado.process import Subprocess
from tornado.test.util import skipIfNonUnix
from tornado.testing import AsyncTestCase, gen_test

# Body of the multi-process test, factored out so it can be launched in a
# clean Python subprocess. fork_processes() calls os.fork(), which raises
# DeprecationWarning on Python 3.12+ if the process has more than one
# thread. Running here in a fresh interpreter avoids picking up threads
# left running by earlier tests in the suite (e.g. the default asyncio
# DNS resolver's thread pool), which would otherwise cause the test
# suite's warnings-as-errors configuration to fail this test.
_MULTI_PROCESS_TEST_SCRIPT = """\
import asyncio
import logging
import os
import signal
import sys

from tornado.httpclient import HTTPClient, HTTPError
from tornado.httpserver import HTTPServer
from tornado.log import gen_log
from tornado.process import fork_processes, task_id
from tornado.simple_httpclient import SimpleAsyncHTTPClient
from tornado.testing import ExpectLog, bind_unused_port
from tornado.web import Application, RequestHandler


class ProcessHandler(RequestHandler):
    def get(self):
        if self.get_argument("exit", None):
            # must use os._exit instead of sys.exit so unittest's
            # exception handler doesn't catch it
            os._exit(int(self.get_argument("exit")))
        if self.get_argument("signal", None):
            os.kill(os.getpid(), int(self.get_argument("signal")))
        self.write(str(os.getpid()))


def main():
    # This test doesn't work on twisted because we use the global
    # reactor and don't restore it to a sane state after the fork
    # (asyncio has the same issue, but we have a special case in
    # place for it).
    with ExpectLog(
        gen_log, "(Starting .* processes|child .* exited|uncaught exception)"
    ):
        sock, port = bind_unused_port()

        def get_url(path):
            return "http://127.0.0.1:%d%s" % (port, path)

        # ensure that none of these processes live too long
        signal.alarm(5)  # master process
        try:
            id = fork_processes(3, max_restarts=3)
            assert id is not None
            signal.alarm(5)  # child processes
        except SystemExit as e:
            # if we exit cleanly from fork_processes, all the child processes
            # finished with status 0
            assert e.code == 0, "fork_processes exited with %r" % (e.code,)
            assert task_id() is None
            sock.close()
            return
        try:
            if id in (0, 1):
                assert id == task_id()

                async def f():
                    server = HTTPServer(Application([("/", ProcessHandler)]))
                    server.add_sockets([sock])
                    await asyncio.Event().wait()

                asyncio.run(f())
            elif id == 2:
                assert id == task_id()
                sock.close()
                # Always use SimpleAsyncHTTPClient here; the curl
                # version appears to get confused sometimes if the
                # connection gets closed before it's had a chance to
                # switch from writing mode to reading mode.
                client = HTTPClient(SimpleAsyncHTTPClient)

                def fetch(url, fail_ok=False):
                    try:
                        return client.fetch(get_url(url))
                    except HTTPError as e:
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
                # fetch("/?signal=%d" % signal.SIGTERM, fail_ok=True)
                # fetch("/?signal=%d" % signal.SIGABRT, fail_ok=True)
                # int(fetch("/").body)

                # Now kill them normally so they won't be restarted
                fetch("/?exit=0", fail_ok=True)
                # One process left; watch it's pid change
                pid = int(fetch("/").body)
                fetch("/?exit=4", fail_ok=True)
                pid2 = int(fetch("/").body)
                assert pid != pid2

                # Kill the last one so we shut down cleanly
                fetch("/?exit=0", fail_ok=True)

                os._exit(0)
        except Exception:
            logging.error("exception in child process %d", id, exc_info=True)
            raise


if __name__ == "__main__":
    main()
"""


# Not using AsyncHTTPTestCase because we need control over the IOLoop.
@skipIfNonUnix
class ProcessTest(unittest.TestCase):
    def test_multi_process(self):
        # Run the test body in a fresh interpreter so fork_processes()
        # starts from a single-threaded state. See the comment on
        # _MULTI_PROCESS_TEST_SCRIPT.
        parts = [os.getcwd()]
        if "PYTHONPATH" in os.environ:
            parts += os.environ["PYTHONPATH"].split(os.pathsep)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(parts))

        result = subprocess.run(
            [sys.executable, "-c", _MULTI_PROCESS_TEST_SCRIPT],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode != 0:
            self.fail(
                "test_multi_process subprocess exited with status %d\n"
                "----- stdout -----\n%s"
                "----- stderr -----\n%s"
                % (
                    result.returncode,
                    result.stdout.decode("utf-8", errors="replace"),
                    result.stderr.decode("utf-8", errors="replace"),
                )
            )


@skipIfNonUnix
class SubprocessTest(AsyncTestCase):
    def term_and_wait(self, subproc):
        subproc.proc.terminate()
        subproc.proc.wait()

    @gen_test
    def test_subprocess(self):
        subproc = Subprocess(
            [sys.executable, "-u", "-i", "-I"],
            stdin=Subprocess.STREAM,
            stdout=Subprocess.STREAM,
            stderr=subprocess.STDOUT,
        )
        self.addCleanup(lambda: self.term_and_wait(subproc))
        self.addCleanup(subproc.stdout.close)
        self.addCleanup(subproc.stdin.close)
        yield subproc.stdout.read_until(b">>> ")
        subproc.stdin.write(b"print('hello')\n")
        data = yield subproc.stdout.read_until(b"\n")
        self.assertEqual(data, b"hello\n")

        yield subproc.stdout.read_until(b">>> ")
        subproc.stdin.write(b"raise SystemExit\n")
        data = yield subproc.stdout.read_until_close()
        self.assertEqual(data, b"")

    @gen_test
    def test_close_stdin(self):
        # Close the parent's stdin handle and see that the child recognizes it.
        subproc = Subprocess(
            [sys.executable, "-u", "-i", "-I"],
            stdin=Subprocess.STREAM,
            stdout=Subprocess.STREAM,
            stderr=subprocess.STDOUT,
        )
        self.addCleanup(lambda: self.term_and_wait(subproc))
        yield subproc.stdout.read_until(b">>> ")
        subproc.stdin.close()
        data = yield subproc.stdout.read_until_close()
        self.assertEqual(data, b"\n")

    @gen_test
    def test_stderr(self):
        # This test is mysteriously flaky on twisted: it succeeds, but logs
        # an error of EBADF on closing a file descriptor.
        subproc = Subprocess(
            [sys.executable, "-u", "-c", r"import sys; sys.stderr.write('hello\n')"],
            stderr=Subprocess.STREAM,
        )
        self.addCleanup(lambda: self.term_and_wait(subproc))
        data = yield subproc.stderr.read_until(b"\n")
        self.assertEqual(data, b"hello\n")
        # More mysterious EBADF: This fails if done with self.addCleanup instead of here.
        subproc.stderr.close()

    def test_sigchild(self):
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess([sys.executable, "-c", "pass"])
        subproc.set_exit_callback(self.stop)
        ret = self.wait()
        self.assertEqual(ret, 0)
        self.assertEqual(subproc.returncode, ret)

    @gen_test
    def test_sigchild_future(self):
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess([sys.executable, "-c", "pass"])
        ret = yield subproc.wait_for_exit()
        self.assertEqual(ret, 0)
        self.assertEqual(subproc.returncode, ret)

    def test_sigchild_signal(self):
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=Subprocess.STREAM,
        )
        self.addCleanup(subproc.stdout.close)
        subproc.set_exit_callback(self.stop)

        # For unclear reasons, killing a process too soon after
        # creating it can result in an exit status corresponding to
        # SIGKILL instead of the actual signal involved. This has been
        # observed on macOS 10.15 with Python 3.8 installed via brew,
        # but not with the system-installed Python 3.7.
        time.sleep(0.1)

        os.kill(subproc.pid, signal.SIGTERM)
        try:
            ret = self.wait()
        except AssertionError:
            # We failed to get the termination signal. This test is
            # occasionally flaky on pypy, so try to get a little more
            # information: did the process close its stdout
            # (indicating that the problem is in the parent process's
            # signal handling) or did the child process somehow fail
            # to terminate?
            fut = subproc.stdout.read_until_close()
            fut.add_done_callback(lambda f: self.stop())  # type: ignore
            try:
                self.wait()
            except AssertionError:
                raise AssertionError("subprocess failed to terminate")
            else:
                raise AssertionError(
                    "subprocess closed stdout but failed to " "get termination signal"
                )
        self.assertEqual(subproc.returncode, ret)
        self.assertEqual(ret, -signal.SIGTERM)

    @gen_test
    def test_wait_for_exit_raise(self):
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess([sys.executable, "-c", "import sys; sys.exit(1)"])
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            yield subproc.wait_for_exit()
        self.assertEqual(cm.exception.returncode, 1)

    @gen_test
    def test_wait_for_exit_raise_disabled(self):
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess([sys.executable, "-c", "import sys; sys.exit(1)"])
        ret = yield subproc.wait_for_exit(raise_error=False)
        self.assertEqual(ret, 1)

    @gen_test
    def test_wait_for_exit_after_proc_wait(self):
        # Issue #3364: if the caller reaps the child via Popen.wait() or
        # .communicate() before our SIGCHLD handler can pick it up, the
        # subsequent os.waitpid(WNOHANG) raises ChildProcessError. The
        # exit callback was previously dropped in that branch, so
        # wait_for_exit() never resolved. Now we fall back to the
        # returncode that Popen already observed, and the future resolves.
        Subprocess.initialize()
        self.addCleanup(Subprocess.uninitialize)
        subproc = Subprocess([sys.executable, "-c", "import sys; sys.exit(7)"])
        # Reap the child before our handler can: this is exactly the
        # sequence that previously left wait_for_exit() hanging.
        ret_code = subproc.proc.wait()
        self.assertEqual(ret_code, 7)
        # Give the IOLoop a turn so the signal handler can run.
        yield gen.sleep(0.05)
        ret = yield subproc.wait_for_exit(raise_error=False)
        self.assertEqual(ret, 7)
