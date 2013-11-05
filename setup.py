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

import sys

try:
    # Use setuptools if available, for install_requires (among other things).
    import setuptools
    from setuptools import setup
except ImportError:
    setuptools = None
    from distutils.core import setup

try:
    from Cython.Build import cythonize
except ImportError:
    cythonize = None

kwargs = {}

version = "3.2.dev2"

with open('README.rst') as f:
    kwargs['long_description'] = f.read()

if cythonize is not None:
    kwargs['ext_modules'] = cythonize('tornado/speedups.pyx')

if setuptools is not None:
    # If setuptools is not available, you're on your own for dependencies.
    if sys.version_info < (3, 2):
        kwargs['install_requires'] = ['backports.ssl_match_hostname']

setuptools.setup(
    name="tornado",
    version=version,
    packages = ["tornado", "tornado.test", "tornado.platform"],
    package_data = {
        "tornado": ["ca-certificates.crt"],
        # data files need to be listed both here (which determines what gets
        # installed) and in MANIFEST.in (which determines what gets included
        # in the sdist tarball)
        "tornado.test": [
            "README",
            "csv_translations/fr_FR.csv",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.mo",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.po",
            "options_test.cfg",
            "static/robots.txt",
            "static/dir/index.html",
            "templates/utf8.html",
            "test.crt",
            "test.key",
            ],
        },
    author="Facebook",
    author_email="python-tornado@googlegroups.com",
    url="http://www.tornadoweb.org/",
    license="http://www.apache.org/licenses/LICENSE-2.0",
    description="Tornado is a Python web framework and asynchronous networking library, originally developed at FriendFeed.",
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        ],
    **kwargs
)
