#!/bin/sh

# libcurl4-gnutls-dev is the default if you ask for libcurl4-dev, but it
# has bugs that make our tests deadlock (the relevant tests detect this and
# disable themselves, but it means that to get full coverage we have to use
# the openssl version)
APT_PACKAGES="
python-pip
python-virtualenv
python-dev
libmysqlclient-dev
libcurl4-openssl-dev
"

PIP_PACKAGES="
tox
MySQL-python
pycurl
twisted
"

apt-get -y install $APT_PACKAGES
pip install $PIP_PACKAGES

/tornado/maint/vm/shared-setup.sh
