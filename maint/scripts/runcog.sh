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
default_python_minor=13
# Run cog itself with the default python version too (otherwise uvx uses
# whatever python it finds first, which may be too old for the f-strings
# in some of our cog blocks).
uvx --python "3.${default_python_minor}" --from cogapp cog \
    -D min_python_minor=11 \
    -D max_python_minor=15 \
    -D min_python_threaded_minor=14 \
    -D max_python_threaded_minor=15 \
    -D default_python_minor="${default_python_minor}" \
    -D dev_python_minor=15 \
    -r $(git grep -l '\[\[\[cog')
