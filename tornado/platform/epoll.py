#!/usr/bin/env python
#
# Copyright 2012 Facebook
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
"""EPoll-based IOLoop implementation for Linux systems.

Supports the standard library's `select.epoll` function for Python 2.6+,
and our own C module for Python 2.5.
"""
from __future__ import absolute_import, division, with_statement

import os
import select

from tornado.ioloop import PollIOLoop

if hasattr(select, 'epoll'):
    # Python 2.6+
    class EPollIOLoop(PollIOLoop):
        def initialize(self, **kwargs):
            super(EPollIOLoop, self).initialize(impl=select.epoll(), **kwargs)
else:
    # Python 2.5
    from tornado import epoll
    
    class _EPoll(object):
        """An epoll-based event loop using our C module for Python 2.5 systems"""
        _EPOLL_CTL_ADD = 1
        _EPOLL_CTL_DEL = 2
        _EPOLL_CTL_MOD = 3

        def __init__(self):
            self._epoll_fd = epoll.epoll_create()

        def fileno(self):
            return self._epoll_fd

        def close(self):
            os.close(self._epoll_fd)

        def register(self, fd, events):
            epoll.epoll_ctl(self._epoll_fd, self._EPOLL_CTL_ADD, fd, events)

        def modify(self, fd, events):
            epoll.epoll_ctl(self._epoll_fd, self._EPOLL_CTL_MOD, fd, events)

        def unregister(self, fd):
            epoll.epoll_ctl(self._epoll_fd, self._EPOLL_CTL_DEL, fd, 0)

        def poll(self, timeout):
            return epoll.epoll_wait(self._epoll_fd, int(timeout * 1000))


    class EPollIOLoop(PollIOLoop):
        def initialize(self, **kwargs):
            super(EPollIOLoop, self).initialize(impl=_EPoll(), **kwargs)

