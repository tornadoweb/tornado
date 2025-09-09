#!/bin/sh

# max/min_python_minor are the range of Python 3.x versions we support.
# max_min_python_threaded_minor are the range of free-threaded python
# versions we support.
# default_python_minor is used in various parts of the build/CI pipeline,
# most significantly in the docs and lint builds which can be sensitive
# to minor version changes. We use the same version for all miscellaneous
# tasks for consistency.
# dev_python_minor is the version of Python that is currently under development
# and is used to install pre-release versions of Python in CI.
uvx --from cogapp cog \
    -D min_python_minor=10 \
    -D max_python_minor=14 \
    -D min_python_threaded_minor=14 \
    -D max_python_threaded_minor=14 \
    -D default_python_minor=13 \
    -D dev_python_minor=14 \
    -r $(git grep -l '\[\[\[cog')
