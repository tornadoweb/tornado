#!/usr/bin/env python

r"""Installs files needed for tornado testing on windows.

These instructions are compatible with the VMs provided by http://modern.ie.
The bootstrapping script works on the WinXP/IE6 and Win8/IE10 configurations,
although tornado's tests do not pass on XP.

1) Install virtualbox guest additions (from the device menu in virtualbox)
2) Set up a shared folder to the root of your tornado repo.  It must be a
   read-write mount to use tox, although the tests can be run directly
   in a read-only mount.  This will probably assign drive letter E:.
3) Install Python 2.7 from python.org.
4) Run this script by double-clicking it, or running
   "c:\python27\python.exe bootstrap.py" in a shell.

To run the tests by hand, cd to e:\ and run
  c:\python27\python.exe -m tornado.test.runtests
To run the tests with tox, cd to e:\maint\vm\windows and run
  c:\python27\scripts\tox
To run under cygwin (which must be installed separately), run
  cd /cygdrive/e; python -m tornado.test.runtests
"""
from __future__ import absolute_import, division, print_function

import os
import subprocess
import sys
import urllib

TMPDIR = r'c:\tornado_bootstrap'

PYTHON_VERSIONS = [
    (r'c:\python27\python.exe', 'http://www.python.org/ftp/python/2.7.3/python-2.7.3.msi'),
    (r'c:\python36\python.exe', 'http://www.python.org/ftp/python/3.6.0/python-3.6.0.msi'),
]

SCRIPTS_DIR = r'c:\python27\scripts'
EASY_INSTALL = os.path.join(SCRIPTS_DIR, 'easy_install.exe')

PY_PACKAGES = ['tox', 'virtualenv', 'pip']


def download_to_cache(url, local_name=None):
    if local_name is None:
        local_name = url.split('/')[-1]
    filename = os.path.join(TMPDIR, local_name)
    if not os.path.exists(filename):
        data = urllib.urlopen(url).read()
        with open(filename, 'wb') as f:
            f.write(data)
    return filename


def main():
    if not os.path.exists(TMPDIR):
        os.mkdir(TMPDIR)
    os.chdir(TMPDIR)
    for exe, url in PYTHON_VERSIONS:
        if os.path.exists(exe):
            print("%s already exists, skipping" % exe)
            continue
        print("Installing %s" % url)
        filename = download_to_cache(url)
        # http://blog.jaraco.com/2012/01/how-i-install-python-on-windows.html
        subprocess.check_call(['msiexec', '/i', filename,
                               'ALLUSERS=1', '/passive'])

    if not os.path.exists(EASY_INSTALL):
        filename = download_to_cache('http://python-distribute.org/distribute_setup.py')
        subprocess.check_call([sys.executable, filename])

    subprocess.check_call([EASY_INSTALL] + PY_PACKAGES)

    # cygwin's setup.exe doesn't like being run from a script (looks
    # UAC-related).  If it did, something like this might install it.
    # (install python, python-setuptools, python3, and easy_install
    # unittest2 (cygwin's python 2 is 2.6))
    #filename = download_to_cache('http://cygwin.com/setup.exe')
    #CYGTMPDIR = os.path.join(TMPDIR, 'cygwin')
    #if not os.path.exists(CYGTMPDIR):
    #    os.mkdir(CYGTMPDIR)
    ## http://www.jbmurphy.com/2011/06/16/powershell-script-to-install-cygwin/
    #CYGWIN_ARGS = [filename, '-q', '-l', CYGTMPDIR,
    #               '-s', 'http://mirror.nyi.net/cygwin/', '-R', r'c:\cygwin']
    #subprocess.check_call(CYGWIN_ARGS)


if __name__ == '__main__':
    main()
