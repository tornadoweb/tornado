#!/bin/sh

# Runs autopep8 in the configuration used for tornado.
#
# W602 is "deprecated form of raising exception", but the fix is incorrect
# (and I'm not sure if the three-argument form of raise is really deprecated
# in the first place)
# E501 is "line longer than 80 chars" but the automated fix is ugly.
# E301 adds a blank line between docstring and first method
# E309 adds a blank line between class declaration and docstring (?)
autopep8 --ignore=W602,E501,E301,E309 -i tornado/*.py tornado/platform/*.py tornado/test/*.py
