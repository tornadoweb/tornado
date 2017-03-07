from __future__ import absolute_import, division, print_function

import os
import platform
import socket
import sys
import textwrap

from tornado.testing import bind_unused_port

# Encapsulate the choice of unittest or unittest2 here.
# To be used as 'from tornado.test.util import unittest'.
if sys.version_info < (2, 7):
    # In py26, we must always use unittest2.
    import unittest2 as unittest  # type: ignore
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

skipOnAppEngine = unittest.skipIf('APPENGINE_RUNTIME' in os.environ,
                                  'not available on Google App Engine')

# Set the environment variable NO_NETWORK=1 to disable any tests that
# depend on an external network.
skipIfNoNetwork = unittest.skipIf('NO_NETWORK' in os.environ,
                                  'network access disabled')

skipIfNoIPv6 = unittest.skipIf(not socket.has_ipv6, 'ipv6 support not present')


skipBefore33 = unittest.skipIf(sys.version_info < (3, 3), 'PEP 380 (yield from) not available')
skipBefore35 = unittest.skipIf(sys.version_info < (3, 5), 'PEP 492 (async/await) not available')
skipNotCPython = unittest.skipIf(platform.python_implementation() != 'CPython',
                                 'Not CPython implementation')


def refusing_port():
    """Returns a local port number that will refuse all connections.

    Return value is (cleanup_func, port); the cleanup function
    must be called to free the port to be reused.
    """
    # On travis-ci, port numbers are reassigned frequently. To avoid
    # collisions with other tests, we use an open client-side socket's
    # ephemeral port number to ensure that nothing can listen on that
    # port.
    server_socket, port = bind_unused_port()
    server_socket.setblocking(1)
    client_socket = socket.socket()
    client_socket.connect(("127.0.0.1", port))
    conn, client_addr = server_socket.accept()
    conn.close()
    server_socket.close()
    return (client_socket.close, client_addr[1])


def exec_test(caller_globals, caller_locals, s):
    """Execute ``s`` in a given context and return the result namespace.

    Used to define functions for tests in particular python
    versions that would be syntax errors in older versions.
    """
    # Flatten the real global and local namespace into our fake
    # globals: it's all global from the perspective of code defined
    # in s.
    global_namespace = dict(caller_globals, **caller_locals)  # type: ignore
    local_namespace = {}
    exec(textwrap.dedent(s), global_namespace, local_namespace)
    return local_namespace


def is_coverage_running():
    """Return whether coverage is currently running.
    """
    if 'coverage' not in sys.modules:
        return False
    tracer = sys.gettrace()
    if tracer is None:
        return False
    try:
        mod = tracer.__module__
    except AttributeError:
        try:
            mod = tracer.__class__.__module__
        except AttributeError:
            return False
    return mod.startswith('coverage')
