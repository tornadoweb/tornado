#!/bin/sh

set -e

tox

.tox/py27/bin/wstest -m fuzzingserver &
FUZZING_SERVER_PID=$!

sleep 1

.tox/py27/bin/python client.py --name='Tornado/py27'
.tox/py39/bin/python client.py --name='Tornado/py39'
.tox/pypy/bin/python client.py --name='Tornado/pypy'

kill $FUZZING_SERVER_PID
wait

echo "Tests complete.  Output is in ./reports/clients/index.html"
