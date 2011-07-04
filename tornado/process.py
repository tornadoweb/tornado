#!/usr/bin/env python
#
# Copyright 2011 Facebook
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

"""Utilities for working with multiple processes."""

import logging
import os
import time

from tornado import ioloop

try:
    import multiprocessing # Python 2.6+
except ImportError:
    multiprocessing = None

def cpu_count():
    """Returns the number of processors on this machine."""
    if multiprocessing is not None:
        try:
            return multiprocessing.cpu_count()
        except NotImplementedError:
            pass
    try:
        return os.sysconf("SC_NPROCESSORS_CONF")
    except ValueError:
        pass
    logging.error("Could not detect number of processors; assuming 1")
    return 1

_processes_forked = False

def fork_processes(num_processes):
    """Starts multiple worker processes.

    If num_processes is None or <= 0, we detect the number of cores
    available on this machine and fork that number of child
    processes. If num_processes is given and > 0, we fork that
    specific number of sub-processes.

    Since we use processes and not threads, there is no shared memory
    between any server code.

    Note that multiple processes are not compatible with the autoreload
    module (or the debug=True option to tornado.web.Application).
    When using multiple processes, no IOLoops can be created or
    referenced until after the call to fork_processes.
    """
    global _processes_forked
    assert not _processes_forked
    _processes_forked = True
    if num_processes is None or num_processes <= 0:
        num_processes = cpu_count()
    if ioloop.IOLoop.initialized():
        raise RuntimeError("Cannot run in multiple processes: IOLoop instance "
                           "has already been initialized. You cannot call "
                           "IOLoop.instance() before calling start_processes()")
    logging.info("Starting %d server processes", num_processes)
    for i in range(num_processes):
        if os.fork() == 0:
            import random
            from binascii import hexlify
            try:
                # If available, use the same method as
                # random.py
                seed = long(hexlify(os.urandom(16)), 16)
            except NotImplementedError:
                # Include the pid to avoid initializing two
                # processes to the same value
                seed(int(time.time() * 1000) ^ os.getpid())
            random.seed(seed)
            return
    os.waitpid(-1, 0)
