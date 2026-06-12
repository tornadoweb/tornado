#
# Copyright 2014 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import getpass
import socket
import typing
import unittest
from contextlib import closing

from tornado.concurrent import Future
from tornado import gen
from tornado.gen import TimeoutError
from tornado.iostream import IOStream
from tornado.netutil import Resolver, bind_sockets
from tornado.queues import Queue
from tornado.tcpclient import TCPClient, _Connector
from tornado.tcpserver import TCPServer
from tornado.test.util import refusing_port, skipIfNoIPv6, skipIfNonUnix
import threading
from tornado.testing import AsyncTestCase, gen_test

# Fake address families for testing.  Used in place of AF_INET
# and AF_INET6 because some installations do not have AF_INET6.
AF1, AF2 = 1, 2


class TestTCPServer(TCPServer):
    def __init__(self, family):
        super().__init__()
        self.streams: list[IOStream] = []
        self.queue: Queue[IOStream] = Queue()
        sockets = bind_sockets(0, "localhost", family)
        self.add_sockets(sockets)
        self.port = sockets[0].getsockname()[1]

    def handle_stream(self, stream, address):
        self.streams.append(stream)
        self.queue.put(stream)

    def stop(self):
        super().stop()
        for stream in self.streams:
            stream.close()


class TCPClientTest(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.server = None
        self.client = TCPClient()

    def start_server(self, family):
        self.server = TestTCPServer(family)
        return self.server.port

    def stop_server(self):
        if self.server is not None:
            self.server.stop()
            self.server = None

    def tearDown(self):
        self.client.close()
        self.stop_server()
        super().tearDown()

    def skipIfLocalhostV4(self):
        # The port used here doesn't matter, but some systems require it
        # to be non-zero if we do not also pass AI_PASSIVE.
        addrinfo = self.io_loop.run_sync(lambda: Resolver().resolve("localhost", 80))
        families = {addr[0] for addr in addrinfo}
        if socket.AF_INET6 not in families:
            self.skipTest("localhost does not resolve to ipv6")

    @gen_test
    def do_test_connect(self, family, host, source_ip=None, source_port=None):
        port = self.start_server(family)
        stream = yield self.client.connect(
            host,
            port,
            source_ip=source_ip,
            source_port=source_port,
            af=family,
        )
        assert self.server is not None
        server_stream = yield self.server.queue.get()
        with closing(stream):
            stream.write(b"hello")
            data = yield server_stream.read_bytes(5)
            self.assertEqual(data, b"hello")

    def test_connect_ipv4_ipv4(self):
        self.do_test_connect(socket.AF_INET, "127.0.0.1")

    def test_connect_ipv4_dual(self):
        self.do_test_connect(socket.AF_INET, "localhost")

    @skipIfNoIPv6
    def test_connect_ipv6_ipv6(self):
        self.skipIfLocalhostV4()
        self.do_test_connect(socket.AF_INET6, "::1")

    @skipIfNoIPv6
    def test_connect_ipv6_dual(self):
        self.skipIfLocalhostV4()
        self.do_test_connect(socket.AF_INET6, "localhost")

    def test_connect_unspec_ipv4(self):
        self.do_test_connect(socket.AF_UNSPEC, "127.0.0.1")

    @skipIfNoIPv6
    def test_connect_unspec_ipv6(self):
        self.skipIfLocalhostV4()
        self.do_test_connect(socket.AF_UNSPEC, "::1")

    def test_connect_unspec_dual(self):
        self.do_test_connect(socket.AF_UNSPEC, "localhost")

    @gen_test
    def test_refused_ipv4(self):
        cleanup_func, port = refusing_port()
        self.addCleanup(cleanup_func)
        with self.assertRaises(IOError):
            yield self.client.connect("127.0.0.1", port)

    def test_source_ip_fail(self):
        """Fail when trying to use the source IP Address '8.8.8.8'."""
        self.assertRaises(
            socket.error,
            self.do_test_connect,
            socket.AF_INET,
            "127.0.0.1",
            source_ip="8.8.8.8",
        )

    def test_source_ip_success(self):
        """Success when trying to use the source IP Address '127.0.0.1'."""
        self.do_test_connect(socket.AF_INET, "127.0.0.1", source_ip="127.0.0.1")

    @skipIfNonUnix
    def test_source_port_fail(self):
        """Fail when trying to use source port 1."""
        if getpass.getuser() == "root":
            # Root can use any port so we can't easily force this to fail.
            # This is mainly relevant for docker.
            self.skipTest("running as root")
        self.assertRaises(
            socket.error,
            self.do_test_connect,
            socket.AF_INET,
            "127.0.0.1",
            source_port=1,
        )

    @gen_test
    def test_connect_timeout(self):
        timeout = 0.05

        class TimeoutResolver(Resolver):
            def resolve(self, *args, **kwargs):
                return Future()  # never completes

        with self.assertRaises(TimeoutError):
            yield TCPClient(resolver=TimeoutResolver()).connect(
                "1.2.3.4", 12345, timeout=timeout
            )


class TestConnectorSplit(unittest.TestCase):
    def test_one_family(self):
        # These addresses aren't in the right format, but split doesn't care.
        primary, secondary = _Connector.split([(AF1, "a"), (AF1, "b")])
        self.assertEqual(primary, [(AF1, "a"), (AF1, "b")])
        self.assertEqual(secondary, [])

    def test_mixed(self):
        primary, secondary = _Connector.split(
            [(AF1, "a"), (AF2, "b"), (AF1, "c"), (AF2, "d")]
        )
        self.assertEqual(primary, [(AF1, "a"), (AF1, "c")])
        self.assertEqual(secondary, [(AF2, "b"), (AF2, "d")])


class ConnectorTest(AsyncTestCase):
    class FakeStream:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    def setUp(self):
        super().setUp()
        self.connect_futures: dict[
            tuple[int, typing.Any], Future[ConnectorTest.FakeStream]
        ] = {}
        self.streams: dict[typing.Any, ConnectorTest.FakeStream] = {}
        self.addrinfo = [(AF1, "a"), (AF1, "b"), (AF2, "c"), (AF2, "d")]

    def tearDown(self):
        # Unless explicitly checked (and popped) in the test, we shouldn't
        # be closing any streams
        for stream in self.streams.values():
            self.assertFalse(stream.closed)
        super().tearDown()

    def create_stream(self, af, addr):
        stream = ConnectorTest.FakeStream()
        self.streams[addr] = stream
        future: Future[ConnectorTest.FakeStream] = Future()
        self.connect_futures[(af, addr)] = future
        return stream, future

    def assert_pending(self, *keys):
        self.assertEqual(sorted(self.connect_futures.keys()), sorted(keys))

    def resolve_connect(self, af, addr, success):
        future = self.connect_futures.pop((af, addr))
        if success:
            future.set_result(self.streams[addr])
        else:
            self.streams.pop(addr)
            future.set_exception(IOError())
        # Run the loop to allow callbacks to be run.
        self.io_loop.add_callback(self.stop)
        self.wait()

    def assert_connector_streams_closed(self, conn):
        for stream in conn.streams:
            self.assertTrue(stream.closed)

    def start_connect(self, addrinfo):
        conn = _Connector(addrinfo, self.create_stream)
        # Give it a huge timeout; we'll trigger timeouts manually.
        future = conn.start(3600, connect_timeout=self.io_loop.time() + 3600)
        return conn, future

    def test_immediate_success(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assertEqual(list(self.connect_futures.keys()), [(AF1, "a")])
        self.resolve_connect(AF1, "a", True)
        self.assertEqual(future.result(), (AF1, "a", self.streams["a"]))

    def test_immediate_failure(self):
        # Fail with just one address.
        conn, future = self.start_connect([(AF1, "a")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assertRaises(IOError, future.result)

    def test_one_family_second_try(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        self.resolve_connect(AF1, "b", True)
        self.assertEqual(future.result(), (AF1, "b", self.streams["b"]))

    def test_one_family_second_try_failure(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        self.resolve_connect(AF1, "b", False)
        self.assertRaises(IOError, future.result)

    def test_one_family_second_try_timeout(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        # trigger the timeout while the first lookup is pending;
        # nothing happens.
        conn.on_timeout()
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        self.resolve_connect(AF1, "b", True)
        self.assertEqual(future.result(), (AF1, "b", self.streams["b"]))

    def test_two_families_immediate_failure(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"), (AF2, "c"))
        self.resolve_connect(AF1, "b", False)
        self.resolve_connect(AF2, "c", True)
        self.assertEqual(future.result(), (AF2, "c", self.streams["c"]))

    def test_two_families_timeout(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_timeout()
        self.assert_pending((AF1, "a"), (AF2, "c"))
        self.resolve_connect(AF2, "c", True)
        self.assertEqual(future.result(), (AF2, "c", self.streams["c"]))
        # resolving 'a' after the connection has completed doesn't start 'b'
        self.resolve_connect(AF1, "a", False)
        self.assert_pending()

    def test_success_after_timeout(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_timeout()
        self.assert_pending((AF1, "a"), (AF2, "c"))
        self.resolve_connect(AF1, "a", True)
        self.assertEqual(future.result(), (AF1, "a", self.streams["a"]))
        # resolving 'c' after completion closes the connection.
        self.resolve_connect(AF2, "c", True)
        self.assertTrue(self.streams.pop("c").closed)

    def test_all_fail(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_timeout()
        self.assert_pending((AF1, "a"), (AF2, "c"))
        self.resolve_connect(AF2, "c", False)
        self.assert_pending((AF1, "a"), (AF2, "d"))
        self.resolve_connect(AF2, "d", False)
        # one queue is now empty
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        self.assertFalse(future.done())
        self.resolve_connect(AF1, "b", False)
        self.assertRaises(IOError, future.result)

    def test_one_family_timeout_after_connect_timeout(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        conn.on_connect_timeout()
        # the connector will close all streams on connect timeout, we
        # should explicitly pop the connect_future.
        self.connect_futures.pop((AF1, "a"))
        self.assertTrue(self.streams.pop("a").closed)
        conn.on_timeout()
        # if the future is set with TimeoutError, we will not iterate next
        # possible address.
        self.assert_pending()
        self.assertEqual(len(conn.streams), 1)
        self.assert_connector_streams_closed(conn)
        self.assertRaises(TimeoutError, future.result)

    def test_one_family_success_before_connect_timeout(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", True)
        conn.on_connect_timeout()
        self.assert_pending()
        self.assertFalse(self.streams["a"].closed)
        # success stream will be pop
        self.assertEqual(len(conn.streams), 0)
        # streams in connector should be closed after connect timeout
        self.assert_connector_streams_closed(conn)
        self.assertEqual(future.result(), (AF1, "a", self.streams["a"]))

    def test_one_family_second_try_after_connect_timeout(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        conn.on_connect_timeout()
        self.connect_futures.pop((AF1, "b"))
        self.assertTrue(self.streams.pop("b").closed)
        self.assert_pending()
        self.assertEqual(len(conn.streams), 2)
        self.assert_connector_streams_closed(conn)
        self.assertRaises(TimeoutError, future.result)

    def test_one_family_second_try_failure_before_connect_timeout(self):
        conn, future = self.start_connect([(AF1, "a"), (AF1, "b")])
        self.assert_pending((AF1, "a"))
        self.resolve_connect(AF1, "a", False)
        self.assert_pending((AF1, "b"))
        self.resolve_connect(AF1, "b", False)
        conn.on_connect_timeout()
        self.assert_pending()
        self.assertEqual(len(conn.streams), 2)
        self.assert_connector_streams_closed(conn)
        self.assertRaises(IOError, future.result)

    def test_two_family_timeout_before_connect_timeout(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_timeout()
        self.assert_pending((AF1, "a"), (AF2, "c"))
        conn.on_connect_timeout()
        self.connect_futures.pop((AF1, "a"))
        self.assertTrue(self.streams.pop("a").closed)
        self.connect_futures.pop((AF2, "c"))
        self.assertTrue(self.streams.pop("c").closed)
        self.assert_pending()
        self.assertEqual(len(conn.streams), 2)
        self.assert_connector_streams_closed(conn)
        self.assertRaises(TimeoutError, future.result)

    def test_two_family_success_after_timeout(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_timeout()
        self.assert_pending((AF1, "a"), (AF2, "c"))
        self.resolve_connect(AF1, "a", True)
        # if one of streams succeed, connector will close all other streams
        self.connect_futures.pop((AF2, "c"))
        self.assertTrue(self.streams.pop("c").closed)
        self.assert_pending()
        self.assertEqual(len(conn.streams), 1)
        self.assert_connector_streams_closed(conn)
        self.assertEqual(future.result(), (AF1, "a", self.streams["a"]))

    def test_two_family_timeout_after_connect_timeout(self):
        conn, future = self.start_connect(self.addrinfo)
        self.assert_pending((AF1, "a"))
        conn.on_connect_timeout()
        self.connect_futures.pop((AF1, "a"))
        self.assertTrue(self.streams.pop("a").closed)
        self.assert_pending()
        conn.on_timeout()
        # if the future is set with TimeoutError, connector will not
        # trigger secondary address.
        self.assert_pending()
        self.assertEqual(len(conn.streams), 1)
        self.assert_connector_streams_closed(conn)
        self.assertRaises(TimeoutError, future.result)


class TCPClientSSLTest(AsyncTestCase):
    """Tests for TCPClient SSL/TLS connect behavior."""

    def setUp(self):
        super().setUp()
        self.server_sock = None

    def tearDown(self):
        if self.server_sock is not None:
            try:
                self.server_sock.close()
            except OSError:
                pass
        super().tearDown()

    @gen_test
    def test_tls_handshake_timeout_closes_stream(self):
        """When a TLS handshake times out, the SSLIOStream must be closed to
        prevent socket file descriptor leaks (GitHub issue #3615).

        This test verifies that after a timeout during the TLS handshake,
        the underlying socket is properly closed (no fd leak).
        """
        import ssl as _ssl
        import asyncio

        # Set up a raw TCP server that accepts but never completes TLS.
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        port = self.server_sock.getsockname()[1]
        self.server_sock.listen(1)
        self.server_sock.settimeout(2)

        accepted_socket = [None]

        def accept_in_background():
            try:
                conn, _ = self.server_sock.accept()
                accepted_socket[0] = conn
                # Hold connection open without completing TLS handshake.
                _ssl.socket.setdefaulttimeout(5)
                time.sleep(5)
            except Exception:
                pass

        thread = threading.Thread(target=accept_in_background, daemon=True)
        thread.start()

        # Use a very short timeout to trigger TLS handshake timeout quickly.
        with self.assertRaises(TimeoutError):
            yield TCPClient().connect(
                "127.0.0.1",
                port,
                ssl_options=dict(cert_reqs=_ssl.CERT_NONE),
                timeout=0.05,
            )

        thread.join(timeout=2)

        # Give the IOLoop a chance to process the close callback.
        yield gen.moment

        # The key assertion: we don't care about data already in flight,
        # but the stream must be closed (no fd leak). We verify this
        # indirectly: if the stream wasn't closed, reading from the server
        # side would eventually get more TLS data or hang. If it was closed,
        # we get either empty bytes (FIN) or a connection reset error.
        if accepted_socket[0] is not None:
            # Drain any data already sent before the close (e.g., ClientHello).
            accepted_socket[0].settimeout(0.5)
            try:
                while True:
                    chunk = accepted_socket[0].recv(4096)
                    if not chunk:
                        break  # FIN received — stream was closed ✅
            except (ConnectionResetError, BrokenPipeError, OSError):
                pass  # Connection reset — stream was closed ✅

