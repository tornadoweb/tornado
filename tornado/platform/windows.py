# NOTE: win32 support is currently experimental, and not recommended
# for production use.

import ctypes
import ctypes.wintypes
import socket
import errno

from tornado.platform import interface
from tornado.util import b

# See: http://msdn.microsoft.com/en-us/library/ms724935(VS.85).aspx
SetHandleInformation = ctypes.windll.kernel32.SetHandleInformation
SetHandleInformation.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD)
SetHandleInformation.restype = ctypes.wintypes.BOOL

HANDLE_FLAG_INHERIT = 0x00000001


def set_close_exec(fd):
    success = SetHandleInformation(fd, HANDLE_FLAG_INHERIT, 0)
    if not success:
        raise ctypes.GetLastError()


class Waker(interface.Waker):
    """Create an OS independent asynchronous pipe"""
    def __init__(self):
        # Based on Zope async.py: http://svn.zope.org/zc.ngi/trunk/src/zc/ngi/async.py

        self.writer = socket.socket()
        # Disable buffering -- pulling the trigger sends 1 byte,
        # and we want that sent immediately, to wake up ASAP.
        self.writer.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        count = 0
        while 1:
            count += 1
            # Bind to a local port; for efficiency, let the OS pick
            # a free port for us.
            # Unfortunately, stress tests showed that we may not
            # be able to connect to that port ("Address already in
            # use") despite that the OS picked it.  This appears
            # to be a race bug in the Windows socket implementation.
            # So we loop until a connect() succeeds (almost always
            # on the first try).  See the long thread at
            # http://mail.zope.org/pipermail/zope/2005-July/160433.html
            # for hideous details.
            a = socket.socket()
            a.bind(("127.0.0.1", 0))
            connect_address = a.getsockname()  # assigned (host, port) pair
            a.listen(1)
            try:
                self.writer.connect(connect_address)
                break    # success
            except socket.error, detail:
                if detail[0] != errno.WSAEADDRINUSE:
                    # "Address already in use" is the only error
                    # I've seen on two WinXP Pro SP2 boxes, under
                    # Pythons 2.3.5 and 2.4.1.
                    raise
                # (10048, 'Address already in use')
                # assert count <= 2 # never triggered in Tim's tests
                if count >= 10:  # I've never seen it go above 2
                    a.close()
                    self.writer.close()
                    raise socket.error("Cannot bind trigger!")
                # Close `a` and try again.  Note:  I originally put a short
                # sleep() here, but it didn't appear to help or hurt.
                a.close()

        self.reader, addr = a.accept()
        self.reader.setblocking(0)
        self.writer.setblocking(0)
        a.close()
        self.reader_fd = self.reader.fileno()

    def fileno(self):
        return self.reader.fileno()

    def wake(self):
        try:
            self.writer.send(b("x"))
        except IOError:
            pass

    def consume(self):
        try:
            while True:
                result = self.reader.recv(1024)
                if not result: break
        except IOError:
            pass

    def close(self):
        self.reader.close()
        self.writer.close()
