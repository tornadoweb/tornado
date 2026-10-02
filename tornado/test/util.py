import contextlib
import gc
import os
import platform
import socket
import sys
import sysconfig
import textwrap
import time
import typing
import unittest
import warnings
from collections.abc import Callable

import tornado.testing
from tornado.testing import bind_unused_port

_TestCaseType = typing.TypeVar("_TestCaseType", bound=type[unittest.TestCase])


class TestCase(unittest.TestCase):
    """`unittest.TestCase` that fails if the test logs anything unexpected.

    The check is registered with `unittest.TestCase.enterContext` before
    ``super().setUp()`` runs, so it covers ``setUp`` as well as the test
    itself. Cleanups run in LIFO order after ``tearDown``, so it covers
    ``tearDown`` too.

    Note that ``assertNoLogs`` replaces the root logger's handlers for the
    duration of the test, so unexpected log output appears in the failure
    message instead of being printed as it happens.
    """

    def setUp(self) -> None:
        self.enterContext(self.assertNoLogs())
        super().setUp()


class AsyncTestCase(tornado.testing.AsyncTestCase):
    """`tornado.testing.AsyncTestCase` with the `TestCase` log check.

    Covering ``tearDown`` matters here in particular: it is
    `tornado.testing.AsyncTestCase.tearDown` that closes the `.IOLoop`, which
    is itself a common source of stray log output.
    """

    def setUp(self) -> None:
        self.enterContext(self.assertNoLogs())
        super().setUp()


# These two list their tornado.testing base first so that it keeps its place
# ahead of any mixin in the method resolution order of the concrete test
# classes (see the comment on TestIOStreamWebMixin in iostream_test.py). The
# log check is inherited from AsyncTestCase, which stays late in the MRO, so
# it is set up exactly once.
class AsyncHTTPTestCase(tornado.testing.AsyncHTTPTestCase, AsyncTestCase):
    pass


class AsyncHTTPSTestCase(tornado.testing.AsyncHTTPSTestCase, AsyncHTTPTestCase):
    pass


skipIfNonUnix = unittest.skipIf(
    os.name != "posix" or sys.platform == "cygwin", "non-unix platform"
)

# Set the environment variable NO_NETWORK=1 to disable any tests that
# depend on an external network.
skipIfNoNetwork = unittest.skipIf("NO_NETWORK" in os.environ, "network access disabled")

# Set the environment variable EMULATION=1 to disable any tests that
# are unreliable under emulation
skipIfEmulated = unittest.skipIf(
    "EMULATION" in os.environ, "test unreliable under emulation"
)

skipNotCPython = unittest.skipIf(
    # "CPython" here essentially refers to the traditional synchronous refcounting GC,
    # so we skip these tests in free-threading builds of cpython too.
    platform.python_implementation() != "CPython"
    or sysconfig.get_config_var("Py_GIL_DISABLED"),
    "Not CPython implementation",
)


def _detect_ipv6():
    if not socket.has_ipv6:
        # socket.has_ipv6 check reports whether ipv6 was present at compile
        # time. It's usually true even when ipv6 doesn't work for other reasons.
        return False
    sock = None
    try:
        sock = socket.socket(socket.AF_INET6)
        sock.bind(("::1", 0))
    except OSError:
        return False
    finally:
        if sock is not None:
            sock.close()
    return True


skipIfNoIPv6 = unittest.skipIf(not _detect_ipv6(), "ipv6 support not present")


def refusing_port():
    """Returns a local port number that will refuse all connections.

    Return value is (cleanup_func, port); the cleanup function
    must be called to free the port to be reused.
    """
    # On travis-ci port numbers are reassigned frequently. To avoid
    # collisions with other tests, we use an open client-side socket's
    # ephemeral port number to ensure that nothing can listen on that
    # port.
    server_socket, port = bind_unused_port()
    server_socket.setblocking(True)
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
    local_namespace: dict[str, typing.Any] = {}
    exec(textwrap.dedent(s), global_namespace, local_namespace)
    return local_namespace


@contextlib.contextmanager
def ignore_deprecation():
    """Context manager to ignore deprecation warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


ABT_SKIP_MESSAGE = "abstract base class"


def abstract_base_test(cls: _TestCaseType) -> _TestCaseType:
    """Decorator to mark a test class as an "abstract" base class.

    This is different from a regular abstract base class because
    we do not limit instantiation of the class. (If we did, it would
    interfere with test discovery). Instead, we prevent the tests from
    being run.

    Subclasses of an abstract base test are run as normal. There is
    no support for the ``@abstractmethod`` decorator so there is no runtime
    check that all such methods are implemented.

    Note that while it is semantically cleaner to modify the test loader
    to exclude abstract base tests, this is more complicated and would
    interfere with third-party test runners. This approach degrades
    gracefully to other tools such as editor-integrated testing.
    """

    # Type-checking fails due to https://github.com/python/mypy/issues/14458
    # @functools.wraps(cls)
    class AbstractBaseWrapper(cls):  # type: ignore
        @classmethod
        def setUpClass(cls):
            if cls is AbstractBaseWrapper:
                raise unittest.SkipTest(ABT_SKIP_MESSAGE)
            super().setUpClass()

    return AbstractBaseWrapper  # type: ignore


# The minimum duration of a single timing measurement in
# assert_linear_scaling. Short measurements are dominated by timer
# granularity (on Windows, time.process_time is based on the scheduler's
# clock, with a resolution of about 16ms) and by whatever else the operating
# system happens to be doing at the time, so the operation being measured is
# repeated until it has run for at least this long.
_MIN_MEASUREMENT_TIME = 0.1


def _time_calls(func: Callable[[int], object], n: int, iterations: int) -> float:
    """Return the CPU time used by ``iterations`` calls of ``func(n)``.

    `time.process_time` is used instead of `time.perf_counter` because it
    counts only the time this process spends running on a CPU. On a busy CI
    worker a process may spend more time waiting to be scheduled than
    running, and that waiting tells us nothing about the algorithmic
    complexity we're trying to measure.
    """
    start = time.process_time()
    for _ in range(iterations):
        func(n)
    return time.process_time() - start


def _calibrate(func: Callable[[int], object], n: int) -> tuple[int, float]:
    """Return a usable iteration count for ``func(n)``, and its timing.

    The count is doubled until the measurement lasts at least
    `_MIN_MEASUREMENT_TIME`, in the same way as `timeit.Timer.autorange`. The
    discarded measurements also serve as a warmup. The last measurement is
    returned along with the count so that the caller can use it as one of its
    samples.
    """
    iterations = 1
    while True:
        elapsed = _time_calls(func, n, iterations)
        if elapsed >= _MIN_MEASUREMENT_TIME:
            return iterations, elapsed
        iterations *= 2


def assert_linear_scaling(
    func: Callable[[int], object],
    n1: int,
    n2: int,
    *,
    max_ratio: float,
    msg: str,
    rounds: int = 3,
    attempts: int = 3,
) -> None:
    """Fail if ``func(n2)`` takes disproportionately longer than ``func(n1)``.

    This is for regression tests of accidentally quadratic (or worse) code,
    where the larger input is expected to exceed ``max_ratio`` times the cost
    of the smaller one by a wide margin. ``max_ratio`` should be set well
    above the expected ratio of ``n2 / n1``: the goal is to detect a change in
    complexity class, not to measure constant factors.

    Timing tests are vulnerable to interference from everything else
    happening on the machine, which on an overloaded CI worker can be a lot.
    Widening ``max_ratio`` is a blunt instrument for this: it makes the test
    both less flaky and less useful. Instead, this function attacks the noise
    itself:

    * Only CPU time used by this process is measured (see `_time_calls`).
    * Each operation is repeated enough times to be measured reliably (see
      `_MIN_MEASUREMENT_TIME`).
    * The garbage collector is disabled during the measurements. Collections
      are triggered by allocation counts, and their cost depends on the
      number of live objects, so leaving it enabled charges an arbitrary and
      unevenly distributed cost to whichever operation happens to trigger one.
    * Each size is measured ``rounds`` times and the lowest result is used.
      Interference can only make an operation look slower, never faster, so
      the minimum is a much more stable estimate of its cost than the mean.
      The two sizes are measured alternately, so that a machine that gets
      slower (or faster) while the test runs affects both alike.
    * The whole measurement is retried up to ``attempts`` times before
      failing. A change in complexity class is reproducible; a scheduling
      hiccup usually isn't.
    """
    t1 = t2 = 0.0
    for _ in range(attempts):
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            iterations1, elapsed1 = _calibrate(func, n1)
            iterations2, elapsed2 = _calibrate(func, n2)
            t1 = elapsed1 / iterations1
            t2 = elapsed2 / iterations2
            for _ in range(rounds - 1):
                t1 = min(t1, _time_calls(func, n1, iterations1) / iterations1)
                t2 = min(t2, _time_calls(func, n2, iterations2) / iterations2)
        finally:
            if gc_was_enabled:
                gc.enable()
        if t2 / t1 <= max_ratio:
            return
    raise AssertionError(
        f"{msg}: n={n1} took {t1:.4f}s and n={n2} took {t2:.4f}s, a ratio of "
        f"{t2 / t1:.1f} (limit {max_ratio}), in each of {attempts} attempts"
    )
