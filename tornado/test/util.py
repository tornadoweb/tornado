from __future__ import absolute_import, division, print_function, with_statement

import os
import sys

# Tornado's own test suite requires the updated unittest module
# (either py27+ or unittest2) so tornado.test.util enforces
# this requirement, but for other users of tornado.testing we want
# to allow the older version if unitest2 is not available.
# Encapsulate the choice of unittest or unittest2 here.
# To be used as 'from tornado.test.util import unittest'.
if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest

skipIfNonUnix = unittest.skipIf(os.name != 'posix' or sys.platform == 'cygwin',
                                "non-unix platform")

# travis-ci.org runs our tests in an overworked virtual machine, which makes
# timing-related tests unreliable.
skipOnTravis = unittest.skipIf('TRAVIS' in os.environ,
                               'timing tests unreliable on travis')
