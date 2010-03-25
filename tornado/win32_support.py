# NOTE: win32 support is currently experimental, and not recommended
# for production use.

import ctypes
import ctypes.wintypes
import os
import socket
import errno


# See: http://msdn.microsoft.com/en-us/library/ms738573(VS.85).aspx
ioctlsocket = ctypes.windll.ws2_32.ioctlsocket
ioctlsocket.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.LONG, ctypes.wintypes.ULONG)
ioctlsocket.restype = ctypes.c_int

# See: http://msdn.microsoft.com/en-us/library/ms724935(VS.85).aspx
SetHandleInformation = ctypes.windll.kernel32.SetHandleInformation
SetHandleInformation.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD)
SetHandleInformation.restype = ctypes.wintypes.BOOL

HANDLE_FLAG_INHERIT = 0x00000001


F_GETFD = 1
F_SETFD = 2
F_GETFL = 3
F_SETFL = 4

FD_CLOEXEC = 1

os.O_NONBLOCK = 2048

FIONBIO = 126


def fcntl(fd, op, arg=0):
    if op == F_GETFD or op == F_GETFL:
        return 0
    elif op == F_SETFD:
        # Check that the flag is CLOEXEC and translate
        if arg == FD_CLOEXEC:
            success = SetHandleInformation(fd, HANDLE_FLAG_INHERIT, arg)
            if not success:
                raise ctypes.GetLastError()
        else:
            raise ValueError("Unsupported arg")
    #elif op == F_SETFL:
        ## Check that the flag is NONBLOCK and translate
        #if arg == os.O_NONBLOCK:
            ##pass
            #result = ioctlsocket(fd, FIONBIO, 1)
            #if result != 0:
                #raise ctypes.GetLastError()
        #else:
            #raise ValueError("Unsupported arg")
    else:
        raise ValueError("Unsupported op")


class Pipe(object):
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

    def read(self):
        """Emulate a file descriptors read method"""
        try:
            return self.reader.recv(1)
        except socket.error, ex:
            if ex.args[0] == errno.EWOULDBLOCK:
                raise IOError
            raise

    def write(self, data):
        """Emulate a file descriptors write method"""
        return self.writer.send(data)
