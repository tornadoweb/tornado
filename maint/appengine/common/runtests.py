#!/usr/bin/env python

import os
import random
import signal
import subprocess
import sys
import time
import urllib2

if __name__ == "__main__":
    tornado_root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                '../../..'))
    # dev_appserver doesn't seem to set SO_REUSEADDR
    port = random.randrange(10000, 11000)
    # does dev_appserver.py ever live anywhere but /usr/local/bin?
    proc = subprocess.Popen([sys.executable,
                             "/usr/local/bin/dev_appserver.py",
                             os.path.dirname(__file__),
                             "--port=%d" % port
                             ],
                            cwd=tornado_root)
    time.sleep(3)
    try:
        resp = urllib2.urlopen("http://localhost:%d/" % port)
        print resp.read()
    finally:
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait()
