from __future__ import absolute_import, division, print_function, with_statement

import os
import sys

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

# Set the environment variable NO_NETWORK=1 to disable any tests that
# depend on an external network.
skipIfNoNetwork = unittest.skipIf('NO_NETWORK' in os.environ,
                                  'network access disabled')
