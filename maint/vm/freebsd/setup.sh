#!/bin/sh

chsh -s bash vagrant

# This doesn't get created automatically for freebsd since virtualbox
# shared folders don't work.
ln -snf /tornado/maint/vm/freebsd /vagrant

PORTS="
lang/python27
devel/py-pip
devel/py-virtualenv
ftp/curl
"

PIP_PACKAGES="
tox
pycurl
"

cd /usr/ports

for port in $PORTS; do
    make -C $port -DBATCH install
done

pip install $PIP_PACKAGES

/tornado/maint/vm/shared-setup.sh

