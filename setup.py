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

import distutils.core
import sys
# Importing setuptools adds some features like "setup.py develop", but
# it's optional so swallow the error if it's not there.
try:
    import setuptools
except ImportError:
    pass

kwargs = {}

# Build the epoll extension for Linux systems with Python < 2.6
extensions = []
major, minor = sys.version_info[:2]
python_26 = (major > 2 or (major == 2 and minor >= 6))
if "linux" in sys.platform.lower() and not python_26:
    extensions.append(distutils.core.Extension(
        "tornado.epoll", ["tornado/epoll.c"]))

version = "2.3.post1"

if major >= 3:
    import setuptools  # setuptools is required for use_2to3
    kwargs["use_2to3"] = True

distutils.core.setup(
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
            "test.crt",
            "test.key",
            "static/robots.txt",
            "templates/utf8.html",
            "csv_translations/fr_FR.csv",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.mo",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.po",
            ],
        },
    ext_modules = extensions,
    author="Facebook",
    author_email="python-tornado@googlegroups.com",
    url="http://www.tornadoweb.org/",
    download_url="http://github.com/downloads/facebook/tornado/tornado-%s.tar.gz" % version,
    license="http://www.apache.org/licenses/LICENSE-2.0",
    description="Tornado is an open source version of the scalable, non-blocking web server and and tools that power FriendFeed",
    **kwargs
)
