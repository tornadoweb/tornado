#!/usr/bin/env python
from __future__ import absolute_import, division, print_function

import contextlib
import errno
import os
import random
import signal
import socket
import subprocess
import sys
import time
import urllib2

try:
    xrange
except NameError:
    xrange = range

if __name__ == "__main__":
    tornado_root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                '../../..'))
    # dev_appserver doesn't seem to set SO_REUSEADDR
    port = random.randrange(10000, 11000)
    # does dev_appserver.py ever live anywhere but /usr/local/bin?
    proc = subprocess.Popen([sys.executable,
                             "/usr/local/bin/dev_appserver.py",
                             os.path.dirname(os.path.abspath(__file__)),
                             "--port=%d" % port,
                             "--skip_sdk_update_check",
                             ],
                            cwd=tornado_root)

    try:
        for i in xrange(50):
            with contextlib.closing(socket.socket()) as sock:
                err = sock.connect_ex(('localhost', port))
                if err == 0:
                    break
                elif err != errno.ECONNREFUSED:
                    raise Exception("Got unexpected socket error %d" % err)
                time.sleep(0.1)
        else:
            raise Exception("Server didn't start listening")

        resp = urllib2.urlopen("http://localhost:%d/" % port)
        print(resp.read())
    finally:
        # dev_appserver sometimes ignores SIGTERM (especially on 2.5),
        # so try a few times to kill it.
        for sig in [signal.SIGTERM, signal.SIGTERM, signal.SIGKILL]:
            os.kill(proc.pid, sig)
            res = os.waitpid(proc.pid, os.WNOHANG)
            if res != (0, 0):
                break
            time.sleep(0.1)
        else:
            os.waitpid(proc.pid, 0)
