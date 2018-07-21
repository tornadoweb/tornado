# NOTE: win32 support is currently experimental, and not recommended
# for production use.

import ctypes
import ctypes.wintypes

# See: http://msdn.microsoft.com/en-us/library/ms724935(VS.85).aspx
SetHandleInformation = ctypes.windll.kernel32.SetHandleInformation  # type: ignore
SetHandleInformation.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD)  # noqa: E501
SetHandleInformation.restype = ctypes.wintypes.BOOL

HANDLE_FLAG_INHERIT = 0x00000001


def set_close_exec(fd):
    success = SetHandleInformation(fd, HANDLE_FLAG_INHERIT, 0)
    if not success:
        raise ctypes.WinError()
