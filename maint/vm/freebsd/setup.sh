#!/bin/sh

chsh -s bash vagrant

PACKAGES="
curl
python
python34
py27-pip
py27-virtualenv
"

PIP_PACKAGES="
futures
pycurl
tox
"

ASSUME_ALWAYS_YES=true pkg install $PACKAGES

pip install $PIP_PACKAGES

/tornado/maint/vm/shared-setup.sh
