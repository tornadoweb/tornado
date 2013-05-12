#!/usr/bin/env python

"""
c_zlib - zlib for Python using ctypes.

This is a quick and nasty implementation of zlib using Python ctypes, in order
to expose the ability to set a compression dictionary (which isn't available
in the zlib module).
"""

__license__ = """
Copyright (c) 2009 Mark Nottingham <mnot@pobox.com>
 
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
 
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
 
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import ctypes as C
from ctypes import util

_zlib = C.cdll.LoadLibrary(util.find_library('zlib' if os.name == 'nt' else 'libz'))

class _z_stream(C.Structure):
    _fields_ = [
        ("next_in", C.POINTER(C.c_ubyte)),
        ("avail_in", C.c_uint),
        ("total_in", C.c_ulong),
        ("next_out", C.POINTER(C.c_ubyte)),
        ("avail_out", C.c_uint),
        ("total_out", C.c_ulong),
        ("msg", C.c_char_p),
        ("state", C.c_void_p),
        ("zalloc", C.c_void_p),
        ("zfree", C.c_void_p),
        ("opaque", C.c_void_p),
        ("data_type", C.c_int),
        ("adler", C.c_ulong),
        ("reserved", C.c_ulong),
        
    ]

# TODO: get zlib version with ctypes
ZLIB_VERSION = C.c_char_p(b"1.2.3")
Z_NULL = 0x00
Z_OK = 0x00
Z_STREAM_END = 0x01
Z_NEED_DICT = 0x02
Z_BUF_ERR = -0x05

Z_NO_FLUSH = 0x00
Z_SYNC_FLUSH = 0x02
Z_FINISH = 0x04

CHUNK = 1024 * 128  # FIXME: need to be smarter than this.

Z_DEFAULT_COMPRESSION = -1

class Compressor:
    def __init__(self, level=Z_DEFAULT_COMPRESSION, dictionary=None):
        self.level = level
        self.st = _z_stream()
        err = _zlib.deflateInit_(C.byref(self.st), self.level, ZLIB_VERSION, C.sizeof(self.st))
        assert err == Z_OK, err  # FIXME: specific error
        if dictionary:
            err = _zlib.deflateSetDictionary(
                C.byref(self.st),
                C.cast(C.c_char_p(dictionary), C.POINTER(C.c_ubyte)),
                len(dictionary)
            )
            assert err == Z_OK, err  # FIXME: more specific error

    def __call__(self, input):
        outbuf = C.create_string_buffer(CHUNK)
        self.st.avail_in  = len(input)
        self.st.next_in   = C.cast(C.c_char_p(input), C.POINTER(C.c_ubyte))
        self.st.next_out  = C.cast(outbuf, C.POINTER(C.c_ubyte))
        self.st.avail_out = CHUNK
        err = _zlib.deflate(C.byref(self.st), Z_SYNC_FLUSH)

        assert err in [Z_OK, Z_STREAM_END]  # FIXME: more specific error

        return outbuf[:CHUNK-self.st.avail_out]

    def __del__(self):
        err = _zlib.deflateEnd(C.byref(self.st))
        assert err == Z_OK, err  # FIXME: more specific error

    
class Decompressor:
    def __init__(self, dictionary=None):
        self.dictionary = dictionary
        self.st = _z_stream()
        err = _zlib.inflateInit2_(C.byref(self.st), 15, ZLIB_VERSION, C.sizeof(self.st))
        assert err == Z_OK, err  # FIXME: more specific error

    def __call__(self, input):
        outbuf = C.create_string_buffer(CHUNK)
        self.st.avail_in  = len(input)
        self.st.next_in   = C.cast(C.c_char_p(input), C.POINTER(C.c_ubyte))
        self.st.avail_out = CHUNK
        self.st.next_out  = C.cast(outbuf, C.POINTER(C.c_ubyte))
        err = _zlib.inflate(C.byref(self.st), Z_SYNC_FLUSH)
        if err == Z_NEED_DICT:
            assert self.dictionary, "no dictionary provided"  # FIXME: more specific error

            err = _zlib.inflateSetDictionary(
                C.byref(self.st),
                C.cast(C.c_char_p(self.dictionary), C.POINTER(C.c_ubyte)),
                len(self.dictionary)
            )
            assert err == Z_OK, err  # FIXME: more specific error
            err = _zlib.inflate(C.byref(self.st), Z_SYNC_FLUSH)
        assert err in [Z_OK, Z_STREAM_END]  # FIXME: more specific error

        return outbuf[:CHUNK-self.st.avail_out]

    def __del__(self):
        err = _zlib.inflateEnd(C.byref(self.st))
        assert err == Z_OK, err # FIXME: more specific error
    
