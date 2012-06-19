#!/bin/sh
#
# Runs the autobahn websocket conformance test against tornado in both
# python2 and python3.  Output goes in ./reports/servers/index.html.
#
# The --cases and --exclude arguments can be used to run only part of
# the suite.  The default is --exclude="9.*" to skip the relatively slow
# performance tests; pass --exclude="" to override and include them.

set -e

# build/update the virtualenvs
tox

.tox/py25/bin/python server.py --port=9001 &
PY25_SERVER_PID=$!

.tox/py27/bin/python server.py --port=9002 &
PY27_SERVER_PID=$!

.tox/py32/bin/python server.py --port=9003 &
PY32_SERVER_PID=$!

.tox/pypy/bin/python server.py --port=9004 &
PYPY_SERVER_PID=$!

sleep 1

.tox/py27/bin/python ./client.py --servers=Tornado/py25=ws://localhost:9001,Tornado/py27=ws://localhost:9002,Tornado/py32=ws://localhost:9003,Tornado/pypy=ws://localhost:9004 "$@" || true

kill $PY25_SERVER_PID
kill $PY27_SERVER_PID
kill $PY32_SERVER_PID
kill $PYPY_SERVER_PID
wait

echo "Tests complete. Output is in ./reports/servers/index.html"