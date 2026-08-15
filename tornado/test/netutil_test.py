import errno
import signal
import socket
import sys
import time
import typing
import unittest
from subprocess import Popen

from tornado.netutil import (
    BlockingResolver,
    OverrideResolver,
    ThreadedResolver,
    _resolve_addr,
    bind_sockets,
    is_valid_ip,
)
from tornado.test.util import abstract_base_test, skipIfNoNetwork
from tornado.testing import AsyncTestCase, bind_unused_port, gen_test

try:
    import pycares  # type: ignore
except ImportError:
    pycares = None
else:
    from tornado.platform.caresresolver import CaresResolver


@abstract_base_test
class _ResolverTestMixin(AsyncTestCase):
    resolver: typing.Any = None

    @gen_test
    def test_localhost(self):
        addrinfo = yield self.resolver.resolve("localhost", 80, socket.AF_UNSPEC)
        # Most of the time localhost resolves to either the ipv4 loopback
        # address alone, or ipv4+ipv6. But some versions of pycares will only
        # return the ipv6 version, so we have to check for either one alone.
        self.assertTrue(
            ((socket.AF_INET, ("127.0.0.1", 80)) in addrinfo)
            or ((socket.AF_INET6, ("::1", 80)) in addrinfo),
            f"loopback address not found in {addrinfo}",
        )


# It is impossible to quickly and consistently generate an error in name
# resolution, so test this case separately, using mocks as needed.
@abstract_base_test
class _ResolverErrorTestMixin(AsyncTestCase):
    resolver: typing.Any = None

    @gen_test
    def test_bad_host(self):
        with self.assertRaises(IOError):
            yield self.resolver.resolve("an invalid domain", 80, socket.AF_UNSPEC)


def _failing_getaddrinfo(*args):
    """Dummy implementation of getaddrinfo for use in mocks"""
    raise socket.gaierror(errno.EIO, "mock: lookup failed")


@skipIfNoNetwork
class BlockingResolverTest(_ResolverTestMixin):
    def setUp(self):
        super().setUp()
        self.resolver = BlockingResolver()


# getaddrinfo-based tests need mocking to reliably generate errors;
# some configurations are slow to produce errors and take longer than
# our default timeout.
class BlockingResolverErrorTest(_ResolverErrorTestMixin):
    def setUp(self):
        super().setUp()
        self.resolver = BlockingResolver()
        self.real_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _failing_getaddrinfo

    def tearDown(self):
        socket.getaddrinfo = self.real_getaddrinfo
        super().tearDown()


class OverrideResolverTest(_ResolverTestMixin):
    def setUp(self):
        super().setUp()
        mapping = {
            ("google.com", 80): ("1.2.3.4", 80),
            ("google.com", 80, socket.AF_INET): ("1.2.3.4", 80),
            ("google.com", 80, socket.AF_INET6): (
                "2a02:6b8:7c:40c:c51e:495f:e23a:3",
                80,
            ),
        }
        self.resolver = OverrideResolver(BlockingResolver(), mapping)

    @gen_test
    def test_resolve_multiaddr(self):
        result = yield self.resolver.resolve("google.com", 80, socket.AF_INET)
        self.assertIn((socket.AF_INET, ("1.2.3.4", 80)), result)

        result = yield self.resolver.resolve("google.com", 80, socket.AF_INET6)
        self.assertIn(
            (socket.AF_INET6, ("2a02:6b8:7c:40c:c51e:495f:e23a:3", 80, 0, 0)), result
        )


@skipIfNoNetwork
class ThreadedResolverTest(_ResolverTestMixin):
    def setUp(self):
        super().setUp()
        self.resolver = ThreadedResolver()

    def tearDown(self):
        self.resolver.close()
        # ThreadedResolver uses a global thread pool, so we have to shut it down
        if ThreadedResolver._threadpool is not None:
            ThreadedResolver._threadpool.shutdown(wait=True)
            ThreadedResolver._threadpool = None
        super().tearDown()


class ThreadedResolverErrorTest(_ResolverErrorTestMixin):
    def setUp(self):
        super().setUp()
        self.resolver = BlockingResolver()
        self.real_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _failing_getaddrinfo

    def tearDown(self):
        socket.getaddrinfo = self.real_getaddrinfo
        super().tearDown()


@skipIfNoNetwork
@unittest.skipIf(sys.platform == "win32", "preexec_fn not available on win32")
class ThreadedResolverImportTest(unittest.TestCase):
    def test_import(self):
        TIMEOUT = 5

        # Test for a deadlock when importing a module that runs the
        # ThreadedResolver at import-time. See resolve_test.py for
        # full explanation.
        command = [sys.executable, "-c", "import tornado.test.resolve_test_helper"]

        start = time.time()
        popen = Popen(command, preexec_fn=lambda: signal.alarm(TIMEOUT))
        while time.time() - start < TIMEOUT:
            return_code = popen.poll()
            if return_code is not None:
                self.assertEqual(0, return_code)
                return  # Success.
            time.sleep(0.05)

        self.fail("import timed out")


# We do not test errors with CaresResolver:
# Some DNS-hijacking ISPs (e.g. Time Warner) return non-empty results
# with an NXDOMAIN status code.  Most resolvers treat this as an error;
# C-ares returns the results, making the "bad_host" tests unreliable.
# C-ares will try to resolve even malformed names, such as the
# name with spaces used in this test.
@skipIfNoNetwork
@unittest.skipIf(pycares is None, "pycares module not present")
@unittest.skipIf(sys.platform == "win32", "pycares doesn't return loopback on windows")
@unittest.skipIf(sys.platform == "darwin", "pycares doesn't return 127.0.0.1 on darwin")
class CaresResolverTest(_ResolverTestMixin):
    def setUp(self):
        super().setUp()
        self.resolver = CaresResolver()


class IsValidIPTest(unittest.TestCase):
    def test_is_valid_ip(self):
        self.assertTrue(is_valid_ip("127.0.0.1"))
        self.assertTrue(is_valid_ip("4.4.4.4"))
        self.assertTrue(is_valid_ip("::1"))
        self.assertTrue(is_valid_ip("2620:0:1cfe:face:b00c::3"))
        self.assertFalse(is_valid_ip("www.google.com"))
        self.assertFalse(is_valid_ip("localhost"))
        self.assertFalse(is_valid_ip("4.4.4.4<"))
        self.assertFalse(is_valid_ip(" 127.0.0.1"))
        self.assertFalse(is_valid_ip(""))
        self.assertFalse(is_valid_ip(" "))
        self.assertFalse(is_valid_ip("\n"))
        self.assertFalse(is_valid_ip("\x00"))
        self.assertFalse(is_valid_ip("a" * 100))


class TestPortAllocation(unittest.TestCase):
    def test_same_port_allocation(self):
        sockets = bind_sockets(0, "localhost")
        try:
            port = sockets[0].getsockname()[1]
            self.assertTrue(all(s.getsockname()[1] == port for s in sockets[1:]))
        finally:
            for sock in sockets:
                sock.close()

    @unittest.skipIf(
        not hasattr(socket, "SO_REUSEPORT"), "SO_REUSEPORT is not supported"
    )
    def test_reuse_port(self):
        sockets: list[socket.socket] = []
        sock, port = bind_unused_port(reuse_port=True)
        try:
            sockets = bind_sockets(port, "127.0.0.1", reuse_port=True)
            self.assertTrue(all(s.getsockname()[1] == port for s in sockets))
        finally:
            sock.close()
            for sock in sockets:
                sock.close()


class ResolveAddrIPFastPathTest(unittest.TestCase):
    """Verify the numeric-only short-circuit in ``_resolve_addr``.

    Issue #3113: when the host is already a literal IP, ``_resolve_addr``
    should pass ``AI_NUMERICHOST | AI_NUMERICSERV`` to ``getaddrinfo`` so
    the resolver does not have to acquire the resolver lock or walk the
    DNS subsystem for a value it already knows.
    """

    def test_ipv4_host_matches_normal_path(self):
        # The numeric-only path should produce the same address tuple as the
        # default path for the same literal IPv4 address.
        fast = _resolve_addr("127.0.0.1", 80)
        normal = _resolve_addr("127.0.0.1", 80)
        self.assertIn((socket.AF_INET, ("127.0.0.1", 80)), fast)
        self.assertEqual(fast, normal)

    def test_ipv6_host_matches_normal_path(self):
        fast = _resolve_addr("::1", 80)
        normal = _resolve_addr("::1", 80)
        self.assertIn(
            (socket.AF_INET6, ("::1", 80, 0, 0)),
            fast,
        )
        self.assertEqual(fast, normal)

    def test_hostname_fallback(self):
        # For hostnames, the numeric-only path should not be used.
        fast = _resolve_addr("localhost", 80)
        normal = _resolve_addr("localhost", 80)
        self.assertEqual(fast, normal)

    def test_ip_host_uses_numeric_flags(self):
        # When the host is a literal IP, the resolver must pass
        # AI_NUMERICHOST|AI_NUMERICSERV to getaddrinfo. Verify by mocking
        # socket.getaddrinfo and asserting on the ``flags`` argument.
        import socket as _socket

        captured = {}

        def fake_getaddrinfo(host, port, *args, **kwargs):
            captured["host"] = host
            captured["port"] = port
            captured["args"] = args
            captured["kwargs"] = kwargs
            # Return a single AF_INET result for the literal address.
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (host, port))]

        real = _socket.getaddrinfo
        _socket.getaddrinfo = fake_getaddrinfo
        try:
            _resolve_addr("127.0.0.1", 80)
        finally:
            _socket.getaddrinfo = real

        # The 6th positional arg is ``flags``; verify AI_NUMERICHOST was set.
        self.assertEqual(len(captured["args"]), 4)
        self.assertEqual(captured["args"][0], _socket.AF_UNSPEC)
        self.assertEqual(captured["args"][1], _socket.SOCK_STREAM)
        self.assertEqual(captured["args"][2], 0)
        flags = captured["args"][3]
        self.assertTrue(
            flags & _socket.AI_NUMERICHOST,
            f"AI_NUMERICHOST not set in flags={flags!r}",
        )
        self.assertTrue(
            flags & _socket.AI_NUMERICSERV,
            f"AI_NUMERICSERV not set in flags={flags!r}",
        )

    def test_hostname_uses_no_flags(self):
        # For a hostname, the resolver should not pass AI_NUMERICHOST (or
        # it would raise EAI_NONAME). Verify by mocking.
        import socket as _socket

        captured = {}

        def fake_getaddrinfo(host, port, *args, **kwargs):
            flags = args[3] if len(args) > 3 else kwargs.get("flags", 0)
            captured["flags"] = flags
            # Make is_valid_ip fail for non-numeric hosts by raising
            # EAI_NONAME whenever AI_NUMERICHOST is set and the host is
            # not a literal IP. For literal IP hosts we return a
            # success result.
            if flags & _socket.AI_NUMERICHOST and host not in ("127.0.0.1", "::1"):
                raise _socket.gaierror(_socket.EAI_NONAME, "Name or service not known")
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (host, port))]

        real = _socket.getaddrinfo
        _socket.getaddrinfo = fake_getaddrinfo
        try:
            _resolve_addr("localhost", 80)
        finally:
            _socket.getaddrinfo = real
        self.assertEqual(captured["flags"], 0)

    def test_invalid_ip_falls_back_to_default(self):
        # A host that is_valid_ip rejects should fall through to the
        # default getaddrinfo path. Mock getaddrinfo to capture both
        # the AI_NUMERICHOST probe and the default call.
        import socket as _socket

        captured = []

        def fake_getaddrinfo(host, port, *args, **kwargs):
            flags = args[3] if len(args) > 3 else kwargs.get("flags", 0)
            captured.append((host, port, flags))
            if flags & _socket.AI_NUMERICHOST:
                # Treat the AI_NUMERICHOST probe as a no-op so we can
                # see the second call (the actual resolution).
                raise _socket.gaierror(
                    _socket.EAI_NONAME, "Name or service not known"
                )
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (host, port))]

        real = _socket.getaddrinfo
        _socket.getaddrinfo = fake_getaddrinfo
        try:
            _resolve_addr("not an ip", 80)
        finally:
            _socket.getaddrinfo = real
        # The first call should have been the AI_NUMERICHOST probe (raised
        # EAI_NONAME above), and the second call should have been the
        # default resolution with flags=0.
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0][0], "not an ip")
        self.assertEqual(captured[0][2], _socket.AI_NUMERICHOST)
        self.assertEqual(captured[1][0], "not an ip")
        self.assertEqual(captured[1][2], 0)
