from __future__ import absolute_import, division, print_function
import os
import subprocess
from subprocess import Popen
import sys
from tempfile import mkdtemp

from tornado.test.util import unittest


MAIN = """\
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


class AutoreloadTest(unittest.TestCase):
    def test_reload_module(self):
        # Create temporary test application
        path = mkdtemp()
        os.mkdir(os.path.join(path, 'testapp'))
        open(os.path.join(path, 'testapp/__init__.py'), 'w').close()
        with open(os.path.join(path, 'testapp/__main__.py'), 'w') as f:
            f.write(MAIN)

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
