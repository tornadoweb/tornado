"""Implementations of JVM-specific functionality"""

from __future__ import absolute_import, division, with_statement

import zlib

from tornado.platform import interface


def set_close_exec(fd):
    pass


class GzipDecompressor(interface.GzipDecompressor):
    def __init__(self):
        # Passing a negative windowBits to Jython's decompressobj results
        # in nowrap=true being passed to java.util.zip.Inflater's constructor
        self._decompressobj = zlib.decompressobj(-zlib.MAX_WBITS)
        self._header_read = 10

    def decompress(self, value):
        # Consume gzip's 10-byte header
        if self._header_read > 0:
            header_read = min(len(value), self._header_read)
            value = value[header_read:]
            self._header_read -= header_read
        if self._header_read == 0:
            return self._decompressobj.decompress(value)
        return ''

    def flush(self):
        return self._decompressobj.flush()
