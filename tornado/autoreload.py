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

"""Automatically restart the server when a source file is modified.

Most applications should not access this module directly.  Instead,
pass the keyword argument ``autoreload=True`` to the
`tornado.web.Application` constructor (or ``debug=True``, which
enables this setting and several others).  This will enable autoreload
mode as well as checking for changes to templates and static
resources.  Note that restarting is a destructive operation and any
requests in progress will be aborted when the process restarts.  (If
you want to disable autoreload while using other debug-mode features,
pass both ``debug=True`` and ``autoreload=False``).

This module can also be used as a command-line wrapper around scripts
such as unit test runners.  See the `main` method for details.

The command-line wrapper and Application debug modes can be used together.
This combination is encouraged as the wrapper catches syntax errors and
other import-time failures, while debug mode catches changes once
the server has started.

This module will not work correctly when `.HTTPServer`'s multi-process
mode is used.

Reloading loses any Python interpreter command-line arguments (e.g. ``-u``)
because it re-executes Python using ``sys.executable`` and ``sys.argv``.
Additionally, modifying these variables will cause reloading to behave
incorrectly.

"""

import os
import sys

# sys.path handling
# -----------------
#
# If a module is run with "python -m", the current directory (i.e. "")
# is automatically prepended to sys.path, but not if it is run as
# "path/to/file.py".  The processing for "-m" rewrites the former to
# the latter, so subsequent executions won't have the same path as the
# original.
#
# Conversely, when run as path/to/file.py, the directory containing
# file.py gets added to the path, which can cause confusion as imports
# may become relative in spite of the future import.
#
# We address the former problem by reconstructing the original command
# line before re-execution so the new process will
# see the correct path.  We attempt to address the latter problem when
# tornado.autoreload is run as __main__.

if __name__ == "__main__":
    # This sys.path manipulation must come before our imports (as much
    # as possible - if we introduced a tornado.sys or tornado.os
    # module we'd be in trouble), or else our imports would become
    # relative again despite the future import.
    #
    # There is a separate __main__ block at the end of the file to call main().
    if sys.path[0] == os.path.dirname(__file__):
        del sys.path[0]

import functools
import importlib.abc
import os
import pkgutil
import sys
import traceback
import types
import subprocess
import weakref

from tornado import ioloop
from tornado.log import gen_log
from tornado import process

try:
    import signal
except ImportError:
    signal = None  # type: ignore

from typing import Callable, Dict, Optional, List, Union

# os.execv is broken on Windows and can't properly parse command line
# arguments and executable name if they contain whitespaces. subprocess
# fixes that behavior.
_has_execv = sys.platform != "win32"

_watched_files = set()
_reload_hooks = []
_reload_attempted = False
_io_loops: "weakref.WeakKeyDictionary[ioloop.IOLoop, bool]" = (
    weakref.WeakKeyDictionary()
)
_autoreload_is_main = False
_original_argv: Optional[List[str]] = None
_original_spec = None


autoreload_start_dict = {
    "start_1": False,
    "start_2": False,
}
autoreload_reload_on_update_dict = {
    "reload_on_update_1": False,
    "reload_on_update_2": False, 
    "reload_on_update_3": False,  
    "reload_on_update_4": False,  
    "reload_on_update_5": False,  
}
autoreload_check_file_dict = {
    "check_file_1": False,  
    "check_file_2": False,  
}
autoreload_reload_dict = {
    "reload_1": False,
    "reload_2": False,
    "reload_3": False,
    "reload_4": False,
    "reload_5": False,
    "reload_6": False
}
autoreload_main_dict = {
    "main_1": False,
    "main_2": False,
    "main_3": False,
    "main_4": False,
    "main_5": False,
    "main_6": False,
    "main_7": False,
    "main_8": False,
    "main_9": False,
    "main_10 ": False,
    "main_11": False,
    "main_12": False,
    "main_13": False, 
    "main_14": False,
}

def start(check_time: int = 500) -> None:
    """Begins watching source files for changes.

    .. versionchanged:: 5.0
       The io_loop argument (deprecated since version 4.1) has been removed.
    """
    io_loop = ioloop.IOLoop.current()
    if io_loop in _io_loops:
        autoreload_start_dict["start_1"] = True
        with open('autoreload_start.txt', 'a') as file:
            file.write(str(autoreload_start_dict) + "\n")
        return
    _io_loops[io_loop] = True
    if len(_io_loops) > 1:
        autoreload_start_dict["start_2"] = True
        gen_log.warning("tornado.autoreload started more than once in the same process")
    modify_times: Dict[str, float] = {}
    callback = functools.partial(_reload_on_update, modify_times)
    scheduler = ioloop.PeriodicCallback(callback, check_time)
    scheduler.start()

def wait() -> None:
    """Wait for a watched file to change, then restart the process.

    Intended to be used at the end of scripts like unit test runners,
    to run the tests again after any source file changes (but see also
    the command-line interface in `main`)
    """
    io_loop = ioloop.IOLoop()
    io_loop.add_callback(start)
    io_loop.start()


def watch(filename: str) -> None:
    """Add a file to the watch list.

    All imported modules are watched by default.
    """
    _watched_files.add(filename)


def add_reload_hook(fn: Callable[[], None]) -> None:
    """Add a function to be called before reloading the process.

    Note that for open file and socket handles it is generally
    preferable to set the ``FD_CLOEXEC`` flag (using `fcntl` or
    `os.set_inheritable`) instead of using a reload hook to close them.
    """
    _reload_hooks.append(fn)


def _reload_on_update(modify_times: Dict[str, float]) -> None:
    if _reload_attempted:
        autoreload_reload_on_update_dict["reload_on_update_1"] = True
        # We already tried to reload and it didn't work, so don't try again.
        return
    if process.task_id() is not None:
        autoreload_reload_on_update_dict["reload_on_update_2"] = True
        # We're in a child process created by fork_processes.  If child
        # processes restarted themselves, they'd all restart and then
        # all call fork_processes again.
        return
    for module in list(sys.modules.values()):
        # Some modules play games with sys.modules (e.g. email/__init__.py
        # in the standard library), and occasionally this can cause strange
        # failures in getattr.  Just ignore anything that's not an ordinary
        # module.
        if not isinstance(module, types.ModuleType):
            autoreload_reload_on_update_dict["reload_on_update_3"] = True
            continue
        path = getattr(module, "__file__", None)
        if not path:
            autoreload_reload_on_update_dict["reload_on_update_4"] = True
            continue
        if path.endswith(".pyc") or path.endswith(".pyo"):
            autoreload_reload_on_update_dict["reload_on_update_5"] = True
            path = path[:-1]
        _check_file(modify_times, path)
    for path in _watched_files:
        _check_file(modify_times, path)
    with open('autoreload_reloadonupdate.txt', 'a') as file:
            file.write(str(autoreload_reload_on_update_dict) + "\n")


def _check_file(modify_times: Dict[str, float], path: str) -> None:
    try:
        modified = os.stat(path).st_mtime
    except Exception:
        return
    if path not in modify_times:
        autoreload_check_file_dict["check_file_1"] = True
        modify_times[path] = modified
        return
    if modify_times[path] != modified:
        autoreload_check_file_dict["check_file_1"] = True
        gen_log.info("%s modified; restarting server", path)
        _reload()
    with open('autoreload_checkfile.txt', 'a') as file:
            file.write(str(autoreload_check_file_dict) + "\n")


def _reload() -> None:
    global _reload_attempted
    _reload_attempted = True
    for fn in _reload_hooks:
        fn()
    if sys.platform != "win32":
        autoreload_reload_dict["reload_1"] = True
        # Clear the alarm signal set by
        # ioloop.set_blocking_log_threshold so it doesn't fire
        # after the exec.
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
    # sys.path fixes: see comments at top of file.  If __main__.__spec__
    # exists, we were invoked with -m and the effective path is about to
    # change on re-exec.  Reconstruct the original command line to
    # ensure that the new process sees the same path we did.
    if _autoreload_is_main:
        autoreload_reload_dict["reload_2"] = True
        assert _original_argv is not None
        spec = _original_spec
        argv = _original_argv
    else:
        autoreload_reload_dict["reload_3"] = True
        spec = getattr(sys.modules["__main__"], "__spec__", None)
        argv = sys.argv
    if spec and spec.name != "__main__":
        autoreload_reload_dict["reload_4"] = True
        # __spec__ is set in two cases: when running a module, and when running a directory. (when
        # running a file, there is no spec). In the former case, we must pass -m to maintain the
        # module-style behavior (setting sys.path), even though python stripped -m from its argv at
        # startup. If sys.path is exactly __main__, we're running a directory and should fall
        # through to the non-module behavior.
        #
        # Some of this, including the use of exactly __main__ as a spec for directory mode,
        # is documented at https://docs.python.org/3/library/runpy.html#runpy.run_path
        argv = ["-m", spec.name] + argv[1:]

    if not _has_execv:
        autoreload_reload_dict["reload_5"] = True
        subprocess.Popen([sys.executable] + argv)
        os._exit(0)
    else:
        autoreload_reload_dict["reload_6"] = True
        os.execv(sys.executable, [sys.executable] + argv)

    with open('autoreload_reload.txt', 'a') as file:
            file.write(str(autoreload_reload_dict) + "\n")


_USAGE = """
  python -m tornado.autoreload -m module.to.run [args...]
  python -m tornado.autoreload path/to/script.py [args...]
"""


def main() -> None:
    """Command-line wrapper to re-run a script whenever its source changes.

    Scripts may be specified by filename or module name::

        python -m tornado.autoreload -m tornado.test.runtests
        python -m tornado.autoreload tornado/test/runtests.py

    Running a script with this wrapper is similar to calling
    `tornado.autoreload.wait` at the end of the script, but this wrapper
    can catch import-time problems like syntax errors that would otherwise
    prevent the script from reaching its call to `wait`.
    """
    # Remember that we were launched with autoreload as main.
    # The main module can be tricky; set the variables both in our globals
    # (which may be __main__) and the real importable version.
    #
    # We use optparse instead of the newer argparse because we want to
    # mimic the python command-line interface which requires stopping
    # parsing at the first positional argument. optparse supports
    # this but as far as I can tell argparse does not.
    import optparse
    import tornado.autoreload

    global _autoreload_is_main
    global _original_argv, _original_spec
    tornado.autoreload._autoreload_is_main = _autoreload_is_main = True
    original_argv = sys.argv
    tornado.autoreload._original_argv = _original_argv = original_argv
    original_spec = getattr(sys.modules["__main__"], "__spec__", None)
    tornado.autoreload._original_spec = _original_spec = original_spec

    parser = optparse.OptionParser(
        prog="python -m tornado.autoreload",
        usage=_USAGE,
        epilog="Either -m or a path must be specified, but not both",
    )
    parser.disable_interspersed_args()
    parser.add_option("-m", dest="module", metavar="module", help="module to run")
    parser.add_option(
        "--until-success",
        action="store_true",
        help="stop reloading after the program exist successfully (status code 0)",
    )
    opts, rest = parser.parse_args()
    if opts.module is None:
        autoreload_main_dict["main_1"] = True
        if not rest:
            autoreload_main_dict["main_2"] = True
            print("Either -m or a path must be specified", file=sys.stderr)
            sys.exit(1)
        path = rest[0]
        sys.argv = rest[:]
    else:
        autoreload_main_dict["main_3"] = True
        path = None
        sys.argv = [sys.argv[0]] + rest

    # SystemExit.code is typed funny: https://github.com/python/typeshed/issues/8513
    # All we care about is truthiness
    exit_status: Union[int, str, None] = 1
    try:
        autoreload_main_dict["main_4"] = True
        import runpy

        if opts.module is not None:
            autoreload_main_dict["main_5"] = True
            runpy.run_module(opts.module, run_name="__main__", alter_sys=True)
        else:
            autoreload_main_dict["main_6"] = True
            assert path is not None
            runpy.run_path(path, run_name="__main__")
    except SystemExit as e:
        autoreload_main_dict["main_7"] = True
        exit_status = e.code
        gen_log.info("Script exited with status %s", e.code)
    except Exception as e:
        autoreload_main_dict["main_8"] = True
        gen_log.warning("Script exited with uncaught exception", exc_info=True)
        # If an exception occurred at import time, the file with the error
        # never made it into sys.modules and so we won't know to watch it.
        # Just to make sure we've covered everything, walk the stack trace
        # from the exception and watch every file.
        for filename, lineno, name, line in traceback.extract_tb(sys.exc_info()[2]):
            watch(filename)
        if isinstance(e, SyntaxError):
            autoreload_main_dict["main_9"] = True
            # SyntaxErrors are special:  their innermost stack frame is fake
            # so extract_tb won't see it and we have to get the filename
            # from the exception object.
            if e.filename is not None:
                autoreload_main_dict["main_10"] = True
                watch(e.filename)
    else:
        autoreload_main_dict["main_11"] = True
        exit_status = 0
        gen_log.info("Script exited normally")
    # restore sys.argv so subsequent executions will include autoreload
    sys.argv = original_argv

    if opts.module is not None:
        autoreload_main_dict["main_12"] = True
        assert opts.module is not None
        # runpy did a fake import of the module as __main__, but now it's
        # no longer in sys.modules.  Figure out where it is and watch it.
        loader = pkgutil.get_loader(opts.module)
        if loader is not None and isinstance(loader, importlib.abc.FileLoader):
            autoreload_main_dict["main_13"] = True
            watch(loader.get_filename())
    if opts.until_success and not exit_status:
        autoreload_main_dict["main_14"] = True
        return
    
    with open('autoreload_main.txt', 'a') as file:
            file.write(str(autoreload_main_dict) + "\n")
    wait()

if __name__ == "__main__":
    # See also the other __main__ block at the top of the file, which modifies
    # sys.path before our imports
    main()
