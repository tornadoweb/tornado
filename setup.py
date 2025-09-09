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

# type: ignore

import os
import platform
import setuptools
import sysconfig


kwargs = {}

with open("tornado/__init__.py") as f:
    ns = {}
    exec(f.read(), ns)
    version = ns["version"]

with open("README.rst") as f:
    kwargs["long_description"] = f.read()
    kwargs["long_description_content_type"] = "text/x-rst"

if (
    platform.python_implementation() == "CPython"
    and os.environ.get("TORNADO_EXTENSION") != "0"
):

    can_use_limited_api = not sysconfig.get_config_var("Py_GIL_DISABLED")

    if can_use_limited_api:
        # [[[cog
        #   cog.out(f"define_macros = [(\"Py_LIMITED_API\", ")
        #   cog.out(f"\"0x03{int(min_python_minor):02x}0000\"")
        #   cog.outl(")]")
        #   cog.outl(f"bdist_wheel_options = {{\"py_limited_api\": \"cp3{min_python_minor}\"}}")
        #   ]]]
        define_macros = [("Py_LIMITED_API", "0x030a0000")]
        bdist_wheel_options = {"py_limited_api": "cp310"}
        # [[[end]]]
    else:
        define_macros = []
        bdist_wheel_options = {}

    # This extension builds and works on pypy as well, although pypy's jit
    # produces equivalent performance.
    kwargs["ext_modules"] = [
        setuptools.Extension(
            "tornado.speedups",
            sources=["tornado/speedups.c"],
            # Unless the user has specified that the extension is mandatory,
            # fall back to the pure-python implementation on any build failure.
            optional=os.environ.get("TORNADO_EXTENSION") != "1",
            # Use the stable ABI so our wheels are compatible across python
            # versions.
            py_limited_api=can_use_limited_api,
            define_macros=define_macros,
        )
    ]

    if bdist_wheel_options:
        kwargs["options"] = {"bdist_wheel": bdist_wheel_options}


setuptools.setup(
    name="tornado",
    version=version,
    # [[[cog cog.outl(f"python_requires=\">= 3.{min_python_minor}\",")]]]
    python_requires=">= 3.10",
    # [[[end]]]
    packages=["tornado", "tornado.test", "tornado.platform"],
    package_data={
        # data files need to be listed both here (which determines what gets
        # installed) and in MANIFEST.in (which determines what gets included
        # in the sdist tarball)
        "tornado": ["py.typed"],
        "tornado.test": [
            "README",
            "csv_translations/fr_FR.csv",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.mo",
            "gettext_translations/fr_FR/LC_MESSAGES/tornado_test.po",
            "options_test.cfg",
            "options_test_types.cfg",
            "options_test_types_str.cfg",
            "static/robots.txt",
            "static/sample.xml",
            "static/sample.xml.gz",
            "static/sample.xml.bz2",
            "static/dir/index.html",
            "static_foo.txt",
            "templates/utf8.html",
            "test.crt",
            "test.key",
        ],
    },
    author="Facebook",
    author_email="python-tornado@googlegroups.com",
    url="http://www.tornadoweb.org/",
    project_urls={
        "Source": "https://github.com/tornadoweb/tornado",
    },
    license="Apache-2.0",
    description=(
        "Tornado is a Python web framework and asynchronous networking library,"
        " originally developed at FriendFeed."
    ),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        # [[[cog
        #   for minor in range(int(min_python_minor), int(max_python_minor) + 1):
        #     cog.outl(f"\"Programming Language :: Python :: 3.{minor}\"")
        #   ]]]
        "Programming Language :: Python :: 3.10"
        "Programming Language :: Python :: 3.11"
        "Programming Language :: Python :: 3.12"
        "Programming Language :: Python :: 3.13"
        "Programming Language :: Python :: 3.14"
        # [[[end]]]
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    **kwargs,
)
