import functools
import os
import socket
import unittest

from tornado.platform.auto import set_close_exec

skipIfNonWindows = unittest.skipIf(os.name != "nt", "non-windows platform")


@skipIfNonWindows
class WindowsTest(unittest.TestCase):
    def test_set_close_exec(self):
        # set_close_exec works with sockets.
        s = socket.socket()
        self.addCleanup(s.close)
        set_close_exec(s.fileno())

        # But it doesn't work with pipes.
        r, w = os.pipe()
        self.addCleanup(functools.partial(os.close, r))
        self.addCleanup(functools.partial(os.close, w))
        with self.assertRaises(WindowsError):
            set_close_exec(r)
