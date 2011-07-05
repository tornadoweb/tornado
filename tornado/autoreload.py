#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A module to automatically restart the server when a module is modified.

Most applications should not call this module directly.  Instead, pass the
keyword argument ``debug=True`` to the `tornado.web.Application` constructor.
This will enable autoreload mode as well as checking for changes to templates
and static resources.

This module depends on IOLoop, so it will not work in WSGI applications
and Google AppEngine.  It also will not work correctly when HTTPServer's
multi-process mode is used.
"""

from __future__ import with_statement

import functools
import logging
import os
import sys
import types

from tornado import ioloop
from tornado import process

try:
    import signal
except ImportError:
    signal = None

def start(io_loop=None, check_time=500):
    """Restarts the process automatically when a module is modified.

    We run on the I/O loop, and restarting is a destructive operation,
    so will terminate any pending requests.
    """
    io_loop = io_loop or ioloop.IOLoop.instance()
    modify_times = {}
    callback = functools.partial(_reload_on_update, io_loop, modify_times)
    scheduler = ioloop.PeriodicCallback(callback, check_time, io_loop=io_loop)
    scheduler.start()

def wait():
    """Wait for a watched file to change, then restart the process.

    Intended to be used at the end of scripts like unit test runners,
    to run the tests again after any source file changes (but see also
    the command-line interface in `main`)
    """
    io_loop = ioloop.IOLoop()
    start(io_loop)
    io_loop.start()

_watched_files = set()

def watch(filename):
    """Add a file to the watch list.

    All imported modules are watched by default.
    """
    _watched_files.add(filename)

_reload_attempted = False

def _reload_on_update(io_loop, modify_times):
    global _reload_attempted
    if _reload_attempted:
        # We already tried to reload and it didn't work, so don't try again.
        return
    if process.task_id() is not None:
        # We're in a child process created by fork_processes.  If child
        # processes restarted themselves, they'd all restart and then
        # all call fork_processes again.
        return
    for module in sys.modules.values():
        # Some modules play games with sys.modules (e.g. email/__init__.py
        # in the standard library), and occasionally this can cause strange
        # failures in getattr.  Just ignore anything that's not an ordinary
        # module.
        if not isinstance(module, types.ModuleType): continue
        path = getattr(module, "__file__", None)
        if not path: continue
        if path.endswith(".pyc") or path.endswith(".pyo"):
            path = path[:-1]
        _check_file(io_loop, modify_times, path)
    for path in _watched_files:
        _check_file(io_loop, modify_times, path)

def _check_file(io_loop, modify_times, path):
        try:
            modified = os.stat(path).st_mtime
        except Exception:
            return
        if path not in modify_times:
            modify_times[path] = modified
            return
        if modify_times[path] != modified:
            logging.info("%s modified; restarting server", path)
            _reload_attempted = True
            for fd in io_loop._handlers.keys():
                try:
                    os.close(fd)
                except Exception:
                    pass
            if hasattr(signal, "setitimer"):
                # Clear the alarm signal set by
                # ioloop.set_blocking_log_threshold so it doesn't fire
                # after the exec.
                signal.setitimer(signal.ITIMER_REAL, 0, 0)
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except OSError:
                # Mac OS X versions prior to 10.6 do not support execv in
                # a process that contains multiple threads.  Instead of
                # re-executing in the current process, start a new one
                # and cause the current process to exit.  This isn't
                # ideal since the new process is detached from the parent
                # terminal and thus cannot easily be killed with ctrl-C,
                # but it's better than not being able to autoreload at
                # all.
                # Unfortunately the errno returned in this case does not
                # appear to be consistent, so we can't easily check for
                # this error specifically.
                os.spawnv(os.P_NOWAIT, sys.executable,
                          [sys.executable] + sys.argv)
                sys.exit(0)

_USAGE = """\
Usage:
  python -m tornado.autoreload -m module.to.run [args...]
  python -m tornado.autoreload path/to/script.py [args...]
"""
def main():
    """Command-line wrapper to re-run a script whenever its source changes.
    
    Scripts may be specified by filename or module name::

        python -m tornado.autoreload -m tornado.test.runtests
        python -m tornado.autoreload tornado/test/runtests.py

    Running a script with this wrapper is similar to calling
    `tornado.autoreload.wait` at the end of the script, but this wrapper
    can catch import-time problems like syntax errors that would otherwise
    prevent the script from reaching its call to `wait`.
    """
    original_argv = sys.argv
    sys.argv = sys.argv[:]
    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        mode = "module"
        module = sys.argv[2]
        del sys.argv[1:3]
    elif len(sys.argv) >= 2:
        mode = "script"
        script = sys.argv[1]
        sys.argv = sys.argv[1:]
    else:
        print >>sys.stderr, _USAGE
        sys.exit(1)

    try:
        if mode == "module":
            import runpy
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        elif mode == "script":
            with open(script) as f:
                global __file__
                __file__ = script
                # Use globals as our "locals" dictionary so that
                # something that tries to import __main__ (e.g. the unittest
                # module) will see the right things.
                exec f.read() in globals(), globals()
    except SystemExit, e:
        logging.info("Script exited with status %s", e.code)
    except Exception, e:
        logging.warning("Script exited with uncaught exception", exc_info=True)
        if isinstance(e, SyntaxError):
            watch(e.filename)
    else:
        logging.info("Script exited normally")
    # restore sys.argv so subsequent executions will include autoreload
    sys.argv = original_argv
    wait()
    

if __name__ == "__main__":
    main()
