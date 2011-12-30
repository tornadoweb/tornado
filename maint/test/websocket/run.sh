#!/bin/sh
#
# Runs the autobahn websocket conformance test against tornado in both
# python2 and python3.  Output goes in ./reports/servers/index.html.
#
# The --cases and --exclude arguments can be used to run only part of
# the suite.  --exclude="9.*" is useful to skip the relatively slow
# performance tests.

set -e

# build/update the virtualenvs
tox

.tox/py27/bin/python server.py --port=9001 &
PY27_SERVER_PID=$!

.tox/py32/bin/python server.py --port=9002 &
PY32_SERVER_PID=$!

sleep 1

.tox/py27/bin/python ./client.py --servers=Tornado/py27=ws://localhost:9001,Tornado/py32=ws://localhost:9002 "$@"

kill $PY27_SERVER_PID
kill $PY32_SERVER_PID
