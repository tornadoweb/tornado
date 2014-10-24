from __future__ import absolute_import, division, print_function, with_statement

import os
import socket
import sys

# Encapsulate the choice of unittest or unittest2 here.
# To be used as 'from tornado.test.util import unittest'.
if sys.version_info < (2, 7):
    # In py26, we must always use unittest2.
    import unittest2 as unittest
else:
    # Otherwise, use whichever version of unittest was imported in
    # tornado.testing.
    from tornado.testing import unittest

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

skipIfNoIPv6 = unittest.skipIf(not socket.has_ipv6, 'ipv6 support not present')
