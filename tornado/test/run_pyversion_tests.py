#!/usr/bin/env python
"""Runs the tornado test suite with all supported python interpreters."""

import os
import subprocess
import sys

INTERPRETERS = [
    "python2.5",
    "python2.6",
    "python2.7",
    "auto2to3",
    "pypy",
    ]

def exists_on_path(filename):
    for dir in os.environ["PATH"].split(":"):
        if os.path.exists(os.path.join(dir, filename)):
            return True
    return False

def main():
    for interpreter in INTERPRETERS:
        print "=================== %s =======================" % interpreter
        if not exists_on_path(interpreter):
            print "Interpreter not found, skipping..."
            continue
        args = [interpreter, "-m", "tornado.test.runtests"] + sys.argv[1:]
        ret = subprocess.call(args)
        if ret != 0:
            print "Tests on %s failed with exit code %d" % (interpreter, ret)
            sys.exit(ret)
    print "All tests passed"

if __name__ == "__main__":
    main()
