#!/bin/sh

# Runs autopep8 in the configuration used for tornado.
#
# W602 is "deprecated form of raising exception", but the fix is incorrect
# (and I'm not sure if the three-argument form of raise is really deprecated
# in the first place)
autopep8 --ignore=W602 -i tornado/*.py tornado/platform/*.py tornado/test/*.py
