#!/bin/sh
# Run the Tornado test suite.
#
# Also consider using tox, which uses virtualenv to run the test suite
# under multiple versions of python.

cd $(dirname $0)

# "python -m" differs from "python tornado/test/runtests.py" in how it sets
# up the default python path.  "python -m" uses the current directory,
# while "python file.py" uses the directory containing "file.py" (which is
# not what you want if file.py appears within a package you want to import
# from)
python -m tornado.test.runtests "$@"
