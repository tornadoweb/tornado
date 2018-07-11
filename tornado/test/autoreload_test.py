from __future__ import absolute_import, division, print_function
import os
import shutil
import subprocess
from subprocess import Popen
import sys
from tempfile import mkdtemp
import time

from tornado.test.util import unittest


class AutoreloadTest(unittest.TestCase):

    def test_reload_module(self):
        main = """\
import os
import sys

from tornado import autoreload

# This import will fail if path is not set up correctly
import testapp

print('Starting')
if 'TESTAPP_STARTED' not in os.environ:
    os.environ['TESTAPP_STARTED'] = '1'
    sys.stdout.flush()
    autoreload._reload()
"""

        # Create temporary test application
        path = mkdtemp()
        self.addCleanup(shutil.rmtree, path)
        os.mkdir(os.path.join(path, 'testapp'))
        open(os.path.join(path, 'testapp/__init__.py'), 'w').close()
        with open(os.path.join(path, 'testapp/__main__.py'), 'w') as f:
            f.write(main)

        # Make sure the tornado module under test is available to the test
        # application
        pythonpath = os.getcwd()
        if 'PYTHONPATH' in os.environ:
            pythonpath += os.pathsep + os.environ['PYTHONPATH']

        p = Popen(
            [sys.executable, '-m', 'testapp'], stdout=subprocess.PIPE,
            cwd=path, env=dict(os.environ, PYTHONPATH=pythonpath),
            universal_newlines=True)
        out = p.communicate()[0]
        self.assertEqual(out, 'Starting\nStarting\n')

    def test_reload_wrapper_preservation(self):
        # This test verifies that when `python -m tornado.autoreload`
        # is used on an application that also has an internal
        # autoreload, the reload wrapper is preserved on restart.
        main = """\
import os
import sys

# This import will fail if path is not set up correctly
import testapp

if 'tornado.autoreload' not in sys.modules:
    raise Exception('started without autoreload wrapper')

import tornado.autoreload

print('Starting')
sys.stdout.flush()
if 'TESTAPP_STARTED' not in os.environ:
    os.environ['TESTAPP_STARTED'] = '1'
    # Simulate an internal autoreload (one not caused
    # by the wrapper).
    tornado.autoreload._reload()
else:
    # Exit directly so autoreload doesn't catch it.
    os._exit(0)
"""

        # Create temporary test application
        path = mkdtemp()
        os.mkdir(os.path.join(path, 'testapp'))
        self.addCleanup(shutil.rmtree, path)
        init_file = os.path.join(path, 'testapp', '__init__.py')
        open(init_file, 'w').close()
        main_file = os.path.join(path, 'testapp', '__main__.py')
        with open(main_file, 'w') as f:
            f.write(main)

        # Make sure the tornado module under test is available to the test
        # application
        pythonpath = os.getcwd()
        if 'PYTHONPATH' in os.environ:
            pythonpath += os.pathsep + os.environ['PYTHONPATH']

        autoreload_proc = Popen(
            [sys.executable, '-m', 'tornado.autoreload', '-m', 'testapp'],
            stdout=subprocess.PIPE, cwd=path,
            env=dict(os.environ, PYTHONPATH=pythonpath),
            universal_newlines=True)

        # This timeout needs to be fairly generous for pypy due to jit
        # warmup costs.
        for i in range(40):
            if autoreload_proc.poll() is not None:
                break
            time.sleep(0.1)
        else:
            autoreload_proc.kill()
            raise Exception("subprocess failed to terminate")

        out = autoreload_proc.communicate()[0]
        self.assertEqual(out, 'Starting\n' * 2)
