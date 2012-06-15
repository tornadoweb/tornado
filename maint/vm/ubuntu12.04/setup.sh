#!/bin/sh

set -e

apt-get update

# libcurl4-gnutls-dev is the default if you ask for libcurl4-dev, but it
# has bugs that make our tests deadlock (the relevant tests detect this and
# disable themselves, but it means that to get full coverage we have to use
# the openssl version).
# The oddly-named python-software-properties includes add-apt-repository.
APT_PACKAGES="
python-pip
python-dev
libmysqlclient-dev
libcurl4-openssl-dev
python-software-properties
"

apt-get -y install $APT_PACKAGES


# Ubuntu 12.04 has python 2.7 as default; install more from here.
# The most important thing is to have both 2.5 and a later version so we
# test with both tornado.epoll and 2.6+ stdlib's select.epoll.
add-apt-repository ppa:fkrull/deadsnakes
apt-get update

DEADSNAKES_PACKAGES="
python2.5
python2.5-dev
python3.2
python3.2-dev
"
apt-get -y install $DEADSNAKES_PACKAGES


PIP_PACKAGES="
virtualenv
tox
MySQL-python
pycurl
twisted
"

pip install $PIP_PACKAGES

/tornado/maint/vm/shared-setup.sh
