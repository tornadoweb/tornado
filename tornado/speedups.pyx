# -*- python -*-
from cpython.mem cimport PyMem_Malloc, PyMem_Free

def websocket_mask(bytes mask_bytes, bytes data_bytes):
    cdef size_t data_len = len(data_bytes)
    cdef char* data = data_bytes
    cdef char* mask = mask_bytes
    cdef size_t i
    cdef char* buf = <char*> PyMem_Malloc(data_len)
    try:
        for i in xrange(data_len):
            buf[i] = data[i] ^ mask[i % 4]
        # Is there a zero-copy equivalent of this?
        return <bytes>(buf[:data_len])
    finally:
        PyMem_Free(buf)
