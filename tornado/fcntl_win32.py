import ctypes
import ctypes.wintypes
import os


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
