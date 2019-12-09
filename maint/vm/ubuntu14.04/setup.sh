#!/bin/sh

set -e

apt-get update

# libcurl4-gnutls-dev is the default if you ask for libcurl4-dev, but it
# has bugs that make our tests deadlock (the relevant tests detect this and
# disable themselves, but it means that to get full coverage we have to use
# the openssl version).
APT_PACKAGES="
python-pip
python-dev
python3-pycurl
libcurl4-openssl-dev
"

apt-get -y install $APT_PACKAGES

# Ubuntu 14.04 includes python 2.7 and 3.4.

PIP_PACKAGES="
futures
pycurl
tox
twisted
virtualenv
"

pip install $PIP_PACKAGES

/tornado/maint/vm/shared-setup.sh
