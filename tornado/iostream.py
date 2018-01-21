#
# Copyright 2009 Facebook
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

"""Utility classes to write to and read from non-blocking files and sockets.

Contents:

* `BaseIOStream`: Generic interface for reading and writing.
* `IOStream`: Implementation of BaseIOStream using non-blocking sockets.
* `SSLIOStream`: SSL-aware version of IOStream.
* `PipeIOStream`: Pipe-based IOStream implementation.
"""

from __future__ import absolute_import, division, print_function

import collections
import errno
import io
import numbers
import os
import socket
import sys
import re

from tornado.concurrent import Future
from tornado import ioloop
from tornado.log import gen_log, app_log
from tornado.netutil import ssl_wrap_socket, _client_ssl_defaults, _server_ssl_defaults
from tornado import stack_context
from tornado.util import errno_from_exception

try:
    from tornado.platform.posix import _set_nonblocking
except ImportError:
    _set_nonblocking = None

try:
    import ssl
except ImportError:
    # ssl is not available on Google App Engine
    ssl = None

# These errnos indicate that a non-blocking operation must be retried
# at a later time.  On most platforms they're the same value, but on
# some they differ.
_ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)

if hasattr(errno, "WSAEWOULDBLOCK"):
    _ERRNO_WOULDBLOCK += (errno.WSAEWOULDBLOCK,)  # type: ignore

# These errnos indicate that a connection has been abruptly terminated.
# They should be caught and handled less noisily than other errors.
_ERRNO_CONNRESET = (errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE,
                    errno.ETIMEDOUT)

if hasattr(errno, "WSAECONNRESET"):
    _ERRNO_CONNRESET += (errno.WSAECONNRESET, errno.WSAECONNABORTED, errno.WSAETIMEDOUT)  # type: ignore # noqa: E501

if sys.platform == 'darwin':
    # OSX appears to have a race condition that causes send(2) to return
    # EPROTOTYPE if called while a socket is being torn down:
    # http://erickt.github.io/blog/2014/11/19/adventures-in-debugging-a-potential-osx-kernel-bug/
    # Since the socket is being closed anyway, treat this as an ECONNRESET
    # instead of an unexpected error.
    _ERRNO_CONNRESET += (errno.EPROTOTYPE,)  # type: ignore

# More non-portable errnos:
_ERRNO_INPROGRESS = (errno.EINPROGRESS,)

if hasattr(errno, "WSAEINPROGRESS"):
    _ERRNO_INPROGRESS += (errno.WSAEINPROGRESS,)  # type: ignore

_WINDOWS = sys.platform.startswith('win')


class StreamClosedError(IOError):
    """Exception raised by `IOStream` methods when the stream is closed.

    Note that the close callback is scheduled to run *after* other
    callbacks on the stream (to allow for buffered data to be processed),
    so you may see this error before you see the close callback.

    The ``real_error`` attribute contains the underlying error that caused
    the stream to close (if any).

    .. versionchanged:: 4.3
       Added the ``real_error`` attribute.
    """
    def __init__(self, real_error=None):
        super(StreamClosedError, self).__init__('Stream is closed')
        self.real_error = real_error


class UnsatisfiableReadError(Exception):
    """Exception raised when a read cannot be satisfied.

    Raised by ``read_until`` and ``read_until_regex`` with a ``max_bytes``
    argument.
    """
    pass


class StreamBufferFullError(Exception):
    """Exception raised by `IOStream` methods when the buffer is full.
    """


class _StreamBuffer(object):
    """
    A specialized buffer that tries to avoid copies when large pieces
    of data are encountered.
    """

    def __init__(self):
        # A sequence of (False, bytearray) and (True, memoryview) objects
        self._buffers = collections.deque()
        # Position in the first buffer
        self._first_pos = 0
        self._size = 0

    def __len__(self):
        return self._size

    # Data above this size will be appended separately instead
    # of extending an existing bytearray
    _large_buf_threshold = 2048

    def append(self, data):
        """
        Append the given piece of data (should be a buffer-compatible object).
        """
        size = len(data)
        if size > self._large_buf_threshold:
            if not isinstance(data, memoryview):
                data = memoryview(data)
            self._buffers.append((True, data))
        elif size > 0:
            if self._buffers:
                is_memview, b = self._buffers[-1]
                new_buf = is_memview or len(b) >= self._large_buf_threshold
            else:
                new_buf = True
            if new_buf:
                self._buffers.append((False, bytearray(data)))
            else:
                b += data

        self._size += size

    def peek(self, size):
        """
        Get a view over at most ``size`` bytes (possibly fewer) at the
        current buffer position.
        """
        assert size > 0
        try:
            is_memview, b = self._buffers[0]
        except IndexError:
            return memoryview(b'')

        pos = self._first_pos
        if is_memview:
            return b[pos:pos + size]
        else:
            return memoryview(b)[pos:pos + size]

    def advance(self, size):
        """
        Advance the current buffer position by ``size`` bytes.
        """
        assert 0 < size <= self._size
        self._size -= size
        pos = self._first_pos

        buffers = self._buffers
        while buffers and size > 0:
            is_large, b = buffers[0]
            b_remain = len(b) - size - pos
            if b_remain <= 0:
                buffers.popleft()
                size -= len(b) - pos
                pos = 0
            elif is_large:
                pos += size
                size = 0
            else:
                # Amortized O(1) shrink for Python 2
                pos += size
                if len(b) <= 2 * pos:
                    del b[:pos]
                    pos = 0
                size = 0

        assert size == 0
        self._first_pos = pos


class BaseIOStream(object):
    """A utility class to write to and read from a non-blocking file or socket.

    We support a non-blocking ``write()`` and a family of ``read_*()`` methods.
    All of the methods take an optional ``callback`` argument and return a
    `.Future` only if no callback is given.  When the operation completes,
    the callback will be run or the `.Future` will resolve with the data
    read (or ``None`` for ``write()``).  All outstanding ``Futures`` will
    resolve with a `StreamClosedError` when the stream is closed; users
    of the callback interface will be notified via
    `.BaseIOStream.set_close_callback` instead.

    When a stream is closed due to an error, the IOStream's ``error``
    attribute contains the exception object.

    Subclasses must implement `fileno`, `close_fd`, `write_to_fd`,
    `read_from_fd`, and optionally `get_fd_error`.
    """
    def __init__(self, max_buffer_size=None,
                 read_chunk_size=None, max_write_buffer_size=None):
        """`BaseIOStream` constructor.

        :arg max_buffer_size: Maximum amount of incoming data to buffer;
            defaults to 100MB.
        :arg read_chunk_size: Amount of data to read at one time from the
            underlying transport; defaults to 64KB.
        :arg max_write_buffer_size: Amount of outgoing data to buffer;
            defaults to unlimited.

        .. versionchanged:: 4.0
           Add the ``max_write_buffer_size`` parameter.  Changed default
           ``read_chunk_size`` to 64KB.
        .. versionchanged:: 5.0
           The ``io_loop`` argument (deprecated since version 4.1) has been
           removed.
        """
        self.io_loop = ioloop.IOLoop.current()
        self.max_buffer_size = max_buffer_size or 104857600
        # A chunk size that is too close to max_buffer_size can cause
        # spurious failures.
        self.read_chunk_size = min(read_chunk_size or 65536,
                                   self.max_buffer_size // 2)
        self.max_write_buffer_size = max_write_buffer_size
        self.error = None
        self._read_buffer = bytearray()
        self._read_buffer_pos = 0
        self._read_buffer_size = 0
        self._user_read_buffer = False
        self._after_user_read_buffer = None
        self._write_buffer = _StreamBuffer()
        self._total_write_index = 0
        self._total_write_done_index = 0
        self._read_delimiter = None
        self._read_regex = None
        self._read_max_bytes = None
        self._read_bytes = None
        self._read_partial = False
        self._read_until_close = False
        self._read_callback = None
        self._read_future = None
        self._streaming_callback = None
        self._write_callback = None
        self._write_futures = collections.deque()
        self._close_callback = None
        self._connect_callback = None
        self._connect_future = None
        # _ssl_connect_future should be defined in SSLIOStream
        # but it's here so we can clean it up in maybe_run_close_callback.
        # TODO: refactor that so subclasses can add additional futures
        # to be cancelled.
        self._ssl_connect_future = None
        self._connecting = False
        self._state = None
        self._pending_callbacks = 0
        self._closed = False

    def fileno(self):
        """Returns the file descriptor for this stream."""
        raise NotImplementedError()

    def close_fd(self):
        """Closes the file underlying this stream.

        ``close_fd`` is called by `BaseIOStream` and should not be called
        elsewhere; other users should call `close` instead.
        """
        raise NotImplementedError()

    def write_to_fd(self, data):
        """Attempts to write ``data`` to the underlying file.

        Returns the number of bytes written.
        """
        raise NotImplementedError()

    def read_from_fd(self, buf):
        """Attempts to read from the underlying file.

        Reads up to ``len(buf)`` bytes, storing them in the buffer.
        Returns the number of bytes read. Returns None if there was
        nothing to read (the socket returned `~errno.EWOULDBLOCK` or
        equivalent), and zero on EOF.

        .. versionchanged:: 5.0

           Interface redesigned to take a buffer and return a number
           of bytes instead of a freshly-allocated object.
        """
        raise NotImplementedError()

    def get_fd_error(self):
        """Returns information about any error on the underlying file.

        This method is called after the `.IOLoop` has signaled an error on the
        file descriptor, and should return an Exception (such as `socket.error`
        with additional information, or None if no such information is
        available.
        """
        return None

    def read_until_regex(self, regex, callback=None, max_bytes=None):
        """Asynchronously read until we have matched the given regex.

        The result includes the data that matches the regex and anything
        that came before it.  If a callback is given, it will be run
        with the data as an argument; if not, this method returns a
        `.Future`.

        If ``max_bytes`` is not None, the connection will be closed
        if more than ``max_bytes`` bytes have been read and the regex is
        not satisfied.

        .. versionchanged:: 4.0
            Added the ``max_bytes`` argument.  The ``callback`` argument is
            now optional and a `.Future` will be returned if it is omitted.
        """
        future = self._set_read_callback(callback)
        self._read_regex = re.compile(regex)
        self._read_max_bytes = max_bytes
        try:
            self._try_inline_read()
        except UnsatisfiableReadError as e:
            # Handle this the same way as in _handle_events.
            gen_log.info("Unsatisfiable read, closing connection: %s" % e)
            self.close(exc_info=e)
            return future
        except:
            if future is not None:
                # Ensure that the future doesn't log an error because its
                # failure was never examined.
                future.add_done_callback(lambda f: f.exception())
            raise
        return future

    def read_until(self, delimiter, callback=None, max_bytes=None):
        """Asynchronously read until we have found the given delimiter.

        The result includes all the data read including the delimiter.
        If a callback is given, it will be run with the data as an argument;
        if not, this method returns a `.Future`.

        If ``max_bytes`` is not None, the connection will be closed
        if more than ``max_bytes`` bytes have been read and the delimiter
        is not found.

        .. versionchanged:: 4.0
            Added the ``max_bytes`` argument.  The ``callback`` argument is
            now optional and a `.Future` will be returned if it is omitted.
        """
        future = self._set_read_callback(callback)
        self._read_delimiter = delimiter
        self._read_max_bytes = max_bytes
        try:
            self._try_inline_read()
        except UnsatisfiableReadError as e:
            # Handle this the same way as in _handle_events.
            gen_log.info("Unsatisfiable read, closing connection: %s" % e)
            self.close(exc_info=e)
            return future
        except:
            if future is not None:
                future.add_done_callback(lambda f: f.exception())
            raise
        return future

    def read_bytes(self, num_bytes, callback=None, streaming_callback=None,
                   partial=False):
        """Asynchronously read a number of bytes.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the final result will be empty.
        Otherwise, the result is all the data that was read.
        If a callback is given, it will be run with the data as an argument;
        if not, this method returns a `.Future`.

        If ``partial`` is true, the callback is run as soon as we have
        any bytes to return (but never more than ``num_bytes``)

        .. versionchanged:: 4.0
            Added the ``partial`` argument.  The callback argument is now
            optional and a `.Future` will be returned if it is omitted.
        """
        future = self._set_read_callback(callback)
        assert isinstance(num_bytes, numbers.Integral)
        self._read_bytes = num_bytes
        self._read_partial = partial
        self._streaming_callback = stack_context.wrap(streaming_callback)
        try:
            self._try_inline_read()
        except:
            if future is not None:
                future.add_done_callback(lambda f: f.exception())
            raise
        return future

    def read_into(self, buf, callback=None, partial=False):
        """Asynchronously read a number of bytes.

        ``buf`` must be a writable buffer into which data will be read.
        If a callback is given, it will be run with the number of read
        bytes as an argument; if not, this method returns a `.Future`.

        If ``partial`` is true, the callback is run as soon as any bytes
        have been read.  Otherwise, it is run when the ``buf`` has been
        entirely filled with read data.

        .. versionadded:: 5.0
        """
        future = self._set_read_callback(callback)

        # First copy data already in read buffer
        available_bytes = self._read_buffer_size
        n = len(buf)
        if available_bytes >= n:
            end = self._read_buffer_pos + n
            buf[:] = memoryview(self._read_buffer)[self._read_buffer_pos:end]
            del self._read_buffer[:end]
            self._after_user_read_buffer = self._read_buffer
        elif available_bytes > 0:
            buf[:available_bytes] = memoryview(self._read_buffer)[self._read_buffer_pos:]

        # Set up the supplied buffer as our temporary read buffer.
        # The original (if it had any data remaining) has been
        # saved for later.
        self._user_read_buffer = True
        self._read_buffer = buf
        self._read_buffer_pos = 0
        self._read_buffer_size = available_bytes
        self._read_bytes = n
        self._read_partial = partial

        try:
            self._try_inline_read()
        except:
            if future is not None:
                future.add_done_callback(lambda f: f.exception())
            raise
        return future

    def read_until_close(self, callback=None, streaming_callback=None):
        """Asynchronously reads all data from the socket until it is closed.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the final result will be empty.
        Otherwise, the result is all the data that was read.
        If a callback is given, it will be run with the data as an argument;
        if not, this method returns a `.Future`.

        Note that if a ``streaming_callback`` is used, data will be
        read from the socket as quickly as it becomes available; there
        is no way to apply backpressure or cancel the reads. If flow
        control or cancellation are desired, use a loop with
        `read_bytes(partial=True) <.read_bytes>` instead.

        .. versionchanged:: 4.0
            The callback argument is now optional and a `.Future` will
            be returned if it is omitted.

        """
        future = self._set_read_callback(callback)
        self._streaming_callback = stack_context.wrap(streaming_callback)
        if self.closed():
            if self._streaming_callback is not None:
                self._run_read_callback(self._read_buffer_size, True)
            self._run_read_callback(self._read_buffer_size, False)
            return future
        self._read_until_close = True
        try:
            self._try_inline_read()
        except:
            if future is not None:
                future.add_done_callback(lambda f: f.exception())
            raise
        return future

    def write(self, data, callback=None):
        """Asynchronously write the given data to this stream.

        If ``callback`` is given, we call it when all of the buffered write
        data has been successfully written to the stream. If there was
        previously buffered write data and an old write callback, that
        callback is simply overwritten with this new callback.

        If no ``callback`` is given, this method returns a `.Future` that
        resolves (with a result of ``None``) when the write has been
        completed.

        The ``data`` argument may be of type `bytes` or `memoryview`.

        .. versionchanged:: 4.0
            Now returns a `.Future` if no callback is given.

        .. versionchanged:: 4.5
            Added support for `memoryview` arguments.
        """
        self._check_closed()
        if data:
            if (self.max_write_buffer_size is not None and
                    len(self._write_buffer) + len(data) > self.max_write_buffer_size):
                raise StreamBufferFullError("Reached maximum write buffer size")
            self._write_buffer.append(data)
            self._total_write_index += len(data)
        if callback is not None:
            self._write_callback = stack_context.wrap(callback)
            future = None
        else:
            future = Future()
            future.add_done_callback(lambda f: f.exception())
            self._write_futures.append((self._total_write_index, future))
        if not self._connecting:
            self._handle_write()
            if self._write_buffer:
                self._add_io_state(self.io_loop.WRITE)
            self._maybe_add_error_listener()
        return future

    def set_close_callback(self, callback):
        """Call the given callback when the stream is closed.

        This is not necessary for applications that use the `.Future`
        interface; all outstanding ``Futures`` will resolve with a
        `StreamClosedError` when the stream is closed.
        """
        self._close_callback = stack_context.wrap(callback)
        self._maybe_add_error_listener()

    def close(self, exc_info=False):
        """Close this stream.

        If ``exc_info`` is true, set the ``error`` attribute to the current
        exception from `sys.exc_info` (or if ``exc_info`` is a tuple,
        use that instead of `sys.exc_info`).
        """
        if not self.closed():
            if exc_info:
                if isinstance(exc_info, tuple):
                    self.error = exc_info[1]
                elif isinstance(exc_info, BaseException):
                    self.error = exc_info
                else:
                    exc_info = sys.exc_info()
                    if any(exc_info):
                        self.error = exc_info[1]
            if self._read_until_close:
                if (self._streaming_callback is not None and
                        self._read_buffer_size):
                    self._run_read_callback(self._read_buffer_size, True)
                self._read_until_close = False
                self._run_read_callback(self._read_buffer_size, False)
            if self._state is not None:
                self.io_loop.remove_handler(self.fileno())
                self._state = None
            self.close_fd()
            self._closed = True
        self._maybe_run_close_callback()

    def _maybe_run_close_callback(self):
        # If there are pending callbacks, don't run the close callback
        # until they're done (see _maybe_add_error_handler)
        if self.closed() and self._pending_callbacks == 0:
            futures = []
            if self._read_future is not None:
                futures.append(self._read_future)
                self._read_future = None
            futures += [future for _, future in self._write_futures]
            self._write_futures.clear()
            if self._connect_future is not None:
                futures.append(self._connect_future)
                self._connect_future = None
            if self._ssl_connect_future is not None:
                futures.append(self._ssl_connect_future)
                self._ssl_connect_future = None
            for future in futures:
                future.set_exception(StreamClosedError(real_error=self.error))
                future.exception()
            if self._close_callback is not None:
                cb = self._close_callback
                self._close_callback = None
                self._run_callback(cb)
            # Delete any unfinished callbacks to break up reference cycles.
            self._read_callback = self._write_callback = None
            # Clear the buffers so they can be cleared immediately even
            # if the IOStream object is kept alive by a reference cycle.
            # TODO: Clear the read buffer too; it currently breaks some tests.
            self._write_buffer = None

    def reading(self):
        """Returns true if we are currently reading from the stream."""
        return self._read_callback is not None or self._read_future is not None

    def writing(self):
        """Returns true if we are currently writing to the stream."""
        return bool(self._write_buffer)

    def closed(self):
        """Returns true if the stream has been closed."""
        return self._closed

    def set_nodelay(self, value):
        """Sets the no-delay flag for this stream.

        By default, data written to TCP streams may be held for a time
        to make the most efficient use of bandwidth (according to
        Nagle's algorithm).  The no-delay flag requests that data be
        written as soon as possible, even if doing so would consume
        additional bandwidth.

        This flag is currently defined only for TCP-based ``IOStreams``.

        .. versionadded:: 3.1
        """
        pass

    def _handle_events(self, fd, events):
        if self.closed():
            gen_log.warning("Got events for closed stream %s", fd)
            return
        try:
            if self._connecting:
                # Most IOLoops will report a write failed connect
                # with the WRITE event, but SelectIOLoop reports a
                # READ as well so we must check for connecting before
                # either.
                self._handle_connect()
            if self.closed():
                return
            if events & self.io_loop.READ:
                self._handle_read()
            if self.closed():
                return
            if events & self.io_loop.WRITE:
                self._handle_write()
            if self.closed():
                return
            if events & self.io_loop.ERROR:
                self.error = self.get_fd_error()
                # We may have queued up a user callback in _handle_read or
                # _handle_write, so don't close the IOStream until those
                # callbacks have had a chance to run.
                self.io_loop.add_callback(self.close)
                return
            state = self.io_loop.ERROR
            if self.reading():
                state |= self.io_loop.READ
            if self.writing():
                state |= self.io_loop.WRITE
            if state == self.io_loop.ERROR and self._read_buffer_size == 0:
                # If the connection is idle, listen for reads too so
                # we can tell if the connection is closed.  If there is
                # data in the read buffer we won't run the close callback
                # yet anyway, so we don't need to listen in this case.
                state |= self.io_loop.READ
            if state != self._state:
                assert self._state is not None, \
                    "shouldn't happen: _handle_events without self._state"
                self._state = state
                self.io_loop.update_handler(self.fileno(), self._state)
        except UnsatisfiableReadError as e:
            gen_log.info("Unsatisfiable read, closing connection: %s" % e)
            self.close(exc_info=e)
        except Exception as e:
            gen_log.error("Uncaught exception, closing connection.",
                          exc_info=True)
            self.close(exc_info=e)
            raise

    def _run_callback(self, callback, *args):
        def wrapper():
            self._pending_callbacks -= 1
            try:
                return callback(*args)
            except Exception as e:
                app_log.error("Uncaught exception, closing connection.",
                              exc_info=True)
                # Close the socket on an uncaught exception from a user callback
                # (It would eventually get closed when the socket object is
                # gc'd, but we don't want to rely on gc happening before we
                # run out of file descriptors)
                self.close(exc_info=e)
                # Re-raise the exception so that IOLoop.handle_callback_exception
                # can see it and log the error
                raise
            finally:
                self._maybe_add_error_listener()
        # We schedule callbacks to be run on the next IOLoop iteration
        # rather than running them directly for several reasons:
        # * Prevents unbounded stack growth when a callback calls an
        #   IOLoop operation that immediately runs another callback
        # * Provides a predictable execution context for e.g.
        #   non-reentrant mutexes
        # * Ensures that the try/except in wrapper() is run outside
        #   of the application's StackContexts
        with stack_context.NullContext():
            # stack_context was already captured in callback, we don't need to
            # capture it again for IOStream's wrapper.  This is especially
            # important if the callback was pre-wrapped before entry to
            # IOStream (as in HTTPConnection._header_callback), as we could
            # capture and leak the wrong context here.
            self._pending_callbacks += 1
            self.io_loop.add_callback(wrapper)

    def _read_to_buffer_loop(self):
        # This method is called from _handle_read and _try_inline_read.
        try:
            if self._read_bytes is not None:
                target_bytes = self._read_bytes
            elif self._read_max_bytes is not None:
                target_bytes = self._read_max_bytes
            elif self.reading():
                # For read_until without max_bytes, or
                # read_until_close, read as much as we can before
                # scanning for the delimiter.
                target_bytes = None
            else:
                target_bytes = 0
            next_find_pos = 0
            # Pretend to have a pending callback so that an EOF in
            # _read_to_buffer doesn't trigger an immediate close
            # callback.  At the end of this method we'll either
            # establish a real pending callback via
            # _read_from_buffer or run the close callback.
            #
            # We need two try statements here so that
            # pending_callbacks is decremented before the `except`
            # clause below (which calls `close` and does need to
            # trigger the callback)
            self._pending_callbacks += 1
            while not self.closed():
                # Read from the socket until we get EWOULDBLOCK or equivalent.
                # SSL sockets do some internal buffering, and if the data is
                # sitting in the SSL object's buffer select() and friends
                # can't see it; the only way to find out if it's there is to
                # try to read it.
                if self._read_to_buffer() == 0:
                    break

                self._run_streaming_callback()

                # If we've read all the bytes we can use, break out of
                # this loop.  We can't just call read_from_buffer here
                # because of subtle interactions with the
                # pending_callback and error_listener mechanisms.
                #
                # If we've reached target_bytes, we know we're done.
                if (target_bytes is not None and
                        self._read_buffer_size >= target_bytes):
                    break

                # Otherwise, we need to call the more expensive find_read_pos.
                # It's inefficient to do this on every read, so instead
                # do it on the first read and whenever the read buffer
                # size has doubled.
                if self._read_buffer_size >= next_find_pos:
                    pos = self._find_read_pos()
                    if pos is not None:
                        return pos
                    next_find_pos = self._read_buffer_size * 2
            return self._find_read_pos()
        finally:
            self._pending_callbacks -= 1

    def _handle_read(self):
        try:
            pos = self._read_to_buffer_loop()
        except UnsatisfiableReadError:
            raise
        except Exception as e:
            gen_log.warning("error on read: %s" % e)
            self.close(exc_info=e)
            return
        if pos is not None:
            self._read_from_buffer(pos)
            return
        else:
            self._maybe_run_close_callback()

    def _set_read_callback(self, callback):
        assert self._read_callback is None, "Already reading"
        assert self._read_future is None, "Already reading"
        if callback is not None:
            self._read_callback = stack_context.wrap(callback)
        else:
            self._read_future = Future()
        return self._read_future

    def _run_read_callback(self, size, streaming):
        if self._user_read_buffer:
            self._read_buffer = self._after_user_read_buffer or bytearray()
            self._after_user_read_buffer = None
            self._read_buffer_pos = 0
            self._read_buffer_size = len(self._read_buffer)
            self._user_read_buffer = False
            result = size
        else:
            result = self._consume(size)
        if streaming:
            callback = self._streaming_callback
        else:
            callback = self._read_callback
            self._read_callback = self._streaming_callback = None
            if self._read_future is not None:
                assert callback is None
                future = self._read_future
                self._read_future = None

                future.set_result(result)
        if callback is not None:
            assert (self._read_future is None) or streaming
            self._run_callback(callback, result)
        else:
            # If we scheduled a callback, we will add the error listener
            # afterwards.  If we didn't, we have to do it now.
            self._maybe_add_error_listener()

    def _try_inline_read(self):
        """Attempt to complete the current read operation from buffered data.

        If the read can be completed without blocking, schedules the
        read callback on the next IOLoop iteration; otherwise starts
        listening for reads on the socket.
        """
        # See if we've already got the data from a previous read
        self._run_streaming_callback()
        pos = self._find_read_pos()
        if pos is not None:
            self._read_from_buffer(pos)
            return
        self._check_closed()
        try:
            pos = self._read_to_buffer_loop()
        except Exception:
            # If there was an in _read_to_buffer, we called close() already,
            # but couldn't run the close callback because of _pending_callbacks.
            # Before we escape from this function, run the close callback if
            # applicable.
            self._maybe_run_close_callback()
            raise
        if pos is not None:
            self._read_from_buffer(pos)
            return
        # We couldn't satisfy the read inline, so either close the stream
        # or listen for new data.
        if self.closed():
            self._maybe_run_close_callback()
        else:
            self._add_io_state(ioloop.IOLoop.READ)

    def _read_to_buffer(self):
        """Reads from the socket and appends the result to the read buffer.

        Returns the number of bytes read.  Returns 0 if there is nothing
        to read (i.e. the read returns EWOULDBLOCK or equivalent).  On
        error closes the socket and raises an exception.
        """
        try:
            while True:
                try:
                    if self._user_read_buffer:
                        buf = memoryview(self._read_buffer)[self._read_buffer_size:]
                    else:
                        buf = bytearray(self.read_chunk_size)
                    bytes_read = self.read_from_fd(buf)
                except (socket.error, IOError, OSError) as e:
                    if errno_from_exception(e) == errno.EINTR:
                        continue
                    # ssl.SSLError is a subclass of socket.error
                    if self._is_connreset(e):
                        # Treat ECONNRESET as a connection close rather than
                        # an error to minimize log spam  (the exception will
                        # be available on self.error for apps that care).
                        self.close(exc_info=e)
                        return
                    self.close(exc_info=e)
                    raise
                break
            if bytes_read is None:
                return 0
            elif bytes_read == 0:
                self.close()
                return 0
            if not self._user_read_buffer:
                self._read_buffer += memoryview(buf)[:bytes_read]
            self._read_buffer_size += bytes_read
        finally:
            # Break the reference to buf so we don't waste a chunk's worth of
            # memory in case an exception hangs on to our stack frame.
            buf = None
        if self._read_buffer_size > self.max_buffer_size:
            gen_log.error("Reached maximum read buffer size")
            self.close()
            raise StreamBufferFullError("Reached maximum read buffer size")
        return bytes_read

    def _run_streaming_callback(self):
        if self._streaming_callback is not None and self._read_buffer_size:
            bytes_to_consume = self._read_buffer_size
            if self._read_bytes is not None:
                bytes_to_consume = min(self._read_bytes, bytes_to_consume)
                self._read_bytes -= bytes_to_consume
            self._run_read_callback(bytes_to_consume, True)

    def _read_from_buffer(self, pos):
        """Attempts to complete the currently-pending read from the buffer.

        The argument is either a position in the read buffer or None,
        as returned by _find_read_pos.
        """
        self._read_bytes = self._read_delimiter = self._read_regex = None
        self._read_partial = False
        self._run_read_callback(pos, False)

    def _find_read_pos(self):
        """Attempts to find a position in the read buffer that satisfies
        the currently-pending read.

        Returns a position in the buffer if the current read can be satisfied,
        or None if it cannot.
        """
        if (self._read_bytes is not None and
            (self._read_buffer_size >= self._read_bytes or
             (self._read_partial and self._read_buffer_size > 0))):
            num_bytes = min(self._read_bytes, self._read_buffer_size)
            return num_bytes
        elif self._read_delimiter is not None:
            # Multi-byte delimiters (e.g. '\r\n') may straddle two
            # chunks in the read buffer, so we can't easily find them
            # without collapsing the buffer.  However, since protocols
            # using delimited reads (as opposed to reads of a known
            # length) tend to be "line" oriented, the delimiter is likely
            # to be in the first few chunks.  Merge the buffer gradually
            # since large merges are relatively expensive and get undone in
            # _consume().
            if self._read_buffer:
                loc = self._read_buffer.find(self._read_delimiter,
                                             self._read_buffer_pos)
                if loc != -1:
                    loc -= self._read_buffer_pos
                    delimiter_len = len(self._read_delimiter)
                    self._check_max_bytes(self._read_delimiter,
                                          loc + delimiter_len)
                    return loc + delimiter_len
                self._check_max_bytes(self._read_delimiter,
                                      self._read_buffer_size)
        elif self._read_regex is not None:
            if self._read_buffer:
                m = self._read_regex.search(self._read_buffer,
                                            self._read_buffer_pos)
                if m is not None:
                    loc = m.end() - self._read_buffer_pos
                    self._check_max_bytes(self._read_regex, loc)
                    return loc
                self._check_max_bytes(self._read_regex, self._read_buffer_size)
        return None

    def _check_max_bytes(self, delimiter, size):
        if (self._read_max_bytes is not None and
                size > self._read_max_bytes):
            raise UnsatisfiableReadError(
                "delimiter %r not found within %d bytes" % (
                    delimiter, self._read_max_bytes))

    def _handle_write(self):
        while True:
            size = len(self._write_buffer)
            if not size:
                break
            assert size > 0
            try:
                if _WINDOWS:
                    # On windows, socket.send blows up if given a
                    # write buffer that's too large, instead of just
                    # returning the number of bytes it was able to
                    # process.  Therefore we must not call socket.send
                    # with more than 128KB at a time.
                    size = 128 * 1024

                num_bytes = self.write_to_fd(self._write_buffer.peek(size))
                if num_bytes == 0:
                    break
                self._write_buffer.advance(num_bytes)
                self._total_write_done_index += num_bytes
            except (socket.error, IOError, OSError) as e:
                if e.args[0] in _ERRNO_WOULDBLOCK:
                    break
                else:
                    if not self._is_connreset(e):
                        # Broken pipe errors are usually caused by connection
                        # reset, and its better to not log EPIPE errors to
                        # minimize log spam
                        gen_log.warning("Write error on %s: %s",
                                        self.fileno(), e)
                    self.close(exc_info=e)
                    return

        while self._write_futures:
            index, future = self._write_futures[0]
            if index > self._total_write_done_index:
                break
            self._write_futures.popleft()
            future.set_result(None)

        if not len(self._write_buffer):
            if self._write_callback:
                callback = self._write_callback
                self._write_callback = None
                self._run_callback(callback)

    def _consume(self, loc):
        # Consume loc bytes from the read buffer and return them
        if loc == 0:
            return b""
        assert loc <= self._read_buffer_size
        # Slice the bytearray buffer into bytes, without intermediate copying
        b = (memoryview(self._read_buffer)
             [self._read_buffer_pos:self._read_buffer_pos + loc]
             ).tobytes()
        self._read_buffer_pos += loc
        self._read_buffer_size -= loc
        # Amortized O(1) shrink
        # (this heuristic is implemented natively in Python 3.4+
        #  but is replicated here for Python 2)
        if self._read_buffer_pos > self._read_buffer_size:
            del self._read_buffer[:self._read_buffer_pos]
            self._read_buffer_pos = 0
        return b

    def _check_closed(self):
        if self.closed():
            raise StreamClosedError(real_error=self.error)

    def _maybe_add_error_listener(self):
        # This method is part of an optimization: to detect a connection that
        # is closed when we're not actively reading or writing, we must listen
        # for read events.  However, it is inefficient to do this when the
        # connection is first established because we are going to read or write
        # immediately anyway.  Instead, we insert checks at various times to
        # see if the connection is idle and add the read listener then.
        if self._pending_callbacks != 0:
            return
        if self._state is None or self._state == ioloop.IOLoop.ERROR:
            if self.closed():
                self._maybe_run_close_callback()
            elif (self._read_buffer_size == 0 and
                  self._close_callback is not None):
                self._add_io_state(ioloop.IOLoop.READ)

    def _add_io_state(self, state):
        """Adds `state` (IOLoop.{READ,WRITE} flags) to our event handler.

        Implementation notes: Reads and writes have a fast path and a
        slow path.  The fast path reads synchronously from socket
        buffers, while the slow path uses `_add_io_state` to schedule
        an IOLoop callback.  Note that in both cases, the callback is
        run asynchronously with `_run_callback`.

        To detect closed connections, we must have called
        `_add_io_state` at some point, but we want to delay this as
        much as possible so we don't have to set an `IOLoop.ERROR`
        listener that will be overwritten by the next slow-path
        operation.  As long as there are callbacks scheduled for
        fast-path ops, those callbacks may do more reads.
        If a sequence of fast-path ops do not end in a slow-path op,
        (e.g. for an @asynchronous long-poll request), we must add
        the error handler.  This is done in `_run_callback` and `write`
        (since the write callback is optional so we can have a
        fast-path write with no `_run_callback`)
        """
        if self.closed():
            # connection has been closed, so there can be no future events
            return
        if self._state is None:
            self._state = ioloop.IOLoop.ERROR | state
            with stack_context.NullContext():
                self.io_loop.add_handler(
                    self.fileno(), self._handle_events, self._state)
        elif not self._state & state:
            self._state = self._state | state
            self.io_loop.update_handler(self.fileno(), self._state)

    def _is_connreset(self, exc):
        """Return true if exc is ECONNRESET or equivalent.

        May be overridden in subclasses.
        """
        return (isinstance(exc, (socket.error, IOError)) and
                errno_from_exception(exc) in _ERRNO_CONNRESET)


class IOStream(BaseIOStream):
    r"""Socket-based `IOStream` implementation.

    This class supports the read and write methods from `BaseIOStream`
    plus a `connect` method.

    The ``socket`` parameter may either be connected or unconnected.
    For server operations the socket is the result of calling
    `socket.accept <socket.socket.accept>`.  For client operations the
    socket is created with `socket.socket`, and may either be
    connected before passing it to the `IOStream` or connected with
    `IOStream.connect`.

    A very simple (and broken) HTTP client using this class:

    .. testcode::

        import tornado.ioloop
        import tornado.iostream
        import socket

        def send_request():
            stream.write(b"GET / HTTP/1.0\r\nHost: friendfeed.com\r\n\r\n")
            stream.read_until(b"\r\n\r\n", on_headers)

        def on_headers(data):
            headers = {}
            for line in data.split(b"\r\n"):
               parts = line.split(b":")
               if len(parts) == 2:
                   headers[parts[0].strip()] = parts[1].strip()
            stream.read_bytes(int(headers[b"Content-Length"]), on_body)

        def on_body(data):
            print(data)
            stream.close()
            tornado.ioloop.IOLoop.current().stop()

        if __name__ == '__main__':
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
            stream = tornado.iostream.IOStream(s)
            stream.connect(("friendfeed.com", 80), send_request)
            tornado.ioloop.IOLoop.current().start()

    .. testoutput::
       :hide:

    """
    def __init__(self, socket, *args, **kwargs):
        self.socket = socket
        self.socket.setblocking(False)
        super(IOStream, self).__init__(*args, **kwargs)

    def fileno(self):
        return self.socket

    def close_fd(self):
        self.socket.close()
        self.socket = None

    def get_fd_error(self):
        errno = self.socket.getsockopt(socket.SOL_SOCKET,
                                       socket.SO_ERROR)
        return socket.error(errno, os.strerror(errno))

    def read_from_fd(self, buf):
        try:
            return self.socket.recv_into(buf)
        except socket.error as e:
            if e.args[0] in _ERRNO_WOULDBLOCK:
                return None
            else:
                raise
        finally:
            buf = None

    def write_to_fd(self, data):
        try:
            return self.socket.send(data)
        finally:
            # Avoid keeping to data, which can be a memoryview.
            # See https://github.com/tornadoweb/tornado/pull/2008
            del data

    def connect(self, address, callback=None, server_hostname=None):
        """Connects the socket to a remote address without blocking.

        May only be called if the socket passed to the constructor was
        not previously connected.  The address parameter is in the
        same format as for `socket.connect <socket.socket.connect>` for
        the type of socket passed to the IOStream constructor,
        e.g. an ``(ip, port)`` tuple.  Hostnames are accepted here,
        but will be resolved synchronously and block the IOLoop.
        If you have a hostname instead of an IP address, the `.TCPClient`
        class is recommended instead of calling this method directly.
        `.TCPClient` will do asynchronous DNS resolution and handle
        both IPv4 and IPv6.

        If ``callback`` is specified, it will be called with no
        arguments when the connection is completed; if not this method
        returns a `.Future` (whose result after a successful
        connection will be the stream itself).

        In SSL mode, the ``server_hostname`` parameter will be used
        for certificate validation (unless disabled in the
        ``ssl_options``) and SNI (if supported; requires Python
        2.7.9+).

        Note that it is safe to call `IOStream.write
        <BaseIOStream.write>` while the connection is pending, in
        which case the data will be written as soon as the connection
        is ready.  Calling `IOStream` read methods before the socket is
        connected works on some platforms but is non-portable.

        .. versionchanged:: 4.0
            If no callback is given, returns a `.Future`.

        .. versionchanged:: 4.2
           SSL certificates are validated by default; pass
           ``ssl_options=dict(cert_reqs=ssl.CERT_NONE)`` or a
           suitably-configured `ssl.SSLContext` to the
           `SSLIOStream` constructor to disable.
        """
        self._connecting = True
        if callback is not None:
            self._connect_callback = stack_context.wrap(callback)
            future = None
        else:
            future = self._connect_future = Future()
        try:
            self.socket.connect(address)
        except socket.error as e:
            # In non-blocking mode we expect connect() to raise an
            # exception with EINPROGRESS or EWOULDBLOCK.
            #
            # On freebsd, other errors such as ECONNREFUSED may be
            # returned immediately when attempting to connect to
            # localhost, so handle them the same way as an error
            # reported later in _handle_connect.
            if (errno_from_exception(e) not in _ERRNO_INPROGRESS and
                    errno_from_exception(e) not in _ERRNO_WOULDBLOCK):
                if future is None:
                    gen_log.warning("Connect error on fd %s: %s",
                                    self.socket.fileno(), e)
                self.close(exc_info=e)
                return future
        self._add_io_state(self.io_loop.WRITE)
        return future

    def start_tls(self, server_side, ssl_options=None, server_hostname=None):
        """Convert this `IOStream` to an `SSLIOStream`.

        This enables protocols that begin in clear-text mode and
        switch to SSL after some initial negotiation (such as the
        ``STARTTLS`` extension to SMTP and IMAP).

        This method cannot be used if there are outstanding reads
        or writes on the stream, or if there is any data in the
        IOStream's buffer (data in the operating system's socket
        buffer is allowed).  This means it must generally be used
        immediately after reading or writing the last clear-text
        data.  It can also be used immediately after connecting,
        before any reads or writes.

        The ``ssl_options`` argument may be either an `ssl.SSLContext`
        object or a dictionary of keyword arguments for the
        `ssl.wrap_socket` function.  The ``server_hostname`` argument
        will be used for certificate validation unless disabled
        in the ``ssl_options``.

        This method returns a `.Future` whose result is the new
        `SSLIOStream`.  After this method has been called,
        any other operation on the original stream is undefined.

        If a close callback is defined on this stream, it will be
        transferred to the new stream.

        .. versionadded:: 4.0

        .. versionchanged:: 4.2
           SSL certificates are validated by default; pass
           ``ssl_options=dict(cert_reqs=ssl.CERT_NONE)`` or a
           suitably-configured `ssl.SSLContext` to disable.
        """
        if (self._read_callback or self._read_future or
                self._write_callback or self._write_futures or
                self._connect_callback or self._connect_future or
                self._pending_callbacks or self._closed or
                self._read_buffer or self._write_buffer):
            raise ValueError("IOStream is not idle; cannot convert to SSL")
        if ssl_options is None:
            if server_side:
                ssl_options = _server_ssl_defaults
            else:
                ssl_options = _client_ssl_defaults

        socket = self.socket
        self.io_loop.remove_handler(socket)
        self.socket = None
        socket = ssl_wrap_socket(socket, ssl_options,
                                 server_hostname=server_hostname,
                                 server_side=server_side,
                                 do_handshake_on_connect=False)
        orig_close_callback = self._close_callback
        self._close_callback = None

        future = Future()
        ssl_stream = SSLIOStream(socket, ssl_options=ssl_options)
        # Wrap the original close callback so we can fail our Future as well.
        # If we had an "unwrap" counterpart to this method we would need
        # to restore the original callback after our Future resolves
        # so that repeated wrap/unwrap calls don't build up layers.

        def close_callback():
            if not future.done():
                # Note that unlike most Futures returned by IOStream,
                # this one passes the underlying error through directly
                # instead of wrapping everything in a StreamClosedError
                # with a real_error attribute. This is because once the
                # connection is established it's more helpful to raise
                # the SSLError directly than to hide it behind a
                # StreamClosedError (and the client is expecting SSL
                # issues rather than network issues since this method is
                # named start_tls).
                future.set_exception(ssl_stream.error or StreamClosedError())
            if orig_close_callback is not None:
                orig_close_callback()
        ssl_stream.set_close_callback(close_callback)
        ssl_stream._ssl_connect_callback = lambda: future.set_result(ssl_stream)
        ssl_stream.max_buffer_size = self.max_buffer_size
        ssl_stream.read_chunk_size = self.read_chunk_size
        return future

    def _handle_connect(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            self.error = socket.error(err, os.strerror(err))
            # IOLoop implementations may vary: some of them return
            # an error state before the socket becomes writable, so
            # in that case a connection failure would be handled by the
            # error path in _handle_events instead of here.
            if self._connect_future is None:
                gen_log.warning("Connect error on fd %s: %s",
                                self.socket.fileno(), errno.errorcode[err])
            self.close()
            return
        if self._connect_callback is not None:
            callback = self._connect_callback
            self._connect_callback = None
            self._run_callback(callback)
        if self._connect_future is not None:
            future = self._connect_future
            self._connect_future = None
            future.set_result(self)
        self._connecting = False

    def set_nodelay(self, value):
        if (self.socket is not None and
                self.socket.family in (socket.AF_INET, socket.AF_INET6)):
            try:
                self.socket.setsockopt(socket.IPPROTO_TCP,
                                       socket.TCP_NODELAY, 1 if value else 0)
            except socket.error as e:
                # Sometimes setsockopt will fail if the socket is closed
                # at the wrong time.  This can happen with HTTPServer
                # resetting the value to false between requests.
                if e.errno != errno.EINVAL and not self._is_connreset(e):
                    raise


class SSLIOStream(IOStream):
    """A utility class to write to and read from a non-blocking SSL socket.

    If the socket passed to the constructor is already connected,
    it should be wrapped with::

        ssl.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)

    before constructing the `SSLIOStream`.  Unconnected sockets will be
    wrapped when `IOStream.connect` is finished.
    """
    def __init__(self, *args, **kwargs):
        """The ``ssl_options`` keyword argument may either be an
        `ssl.SSLContext` object or a dictionary of keywords arguments
        for `ssl.wrap_socket`
        """
        self._ssl_options = kwargs.pop('ssl_options', _client_ssl_defaults)
        super(SSLIOStream, self).__init__(*args, **kwargs)
        self._ssl_accepting = True
        self._handshake_reading = False
        self._handshake_writing = False
        self._ssl_connect_callback = None
        self._server_hostname = None

        # If the socket is already connected, attempt to start the handshake.
        try:
            self.socket.getpeername()
        except socket.error:
            pass
        else:
            # Indirectly start the handshake, which will run on the next
            # IOLoop iteration and then the real IO state will be set in
            # _handle_events.
            self._add_io_state(self.io_loop.WRITE)

    def reading(self):
        return self._handshake_reading or super(SSLIOStream, self).reading()

    def writing(self):
        return self._handshake_writing or super(SSLIOStream, self).writing()

    def _do_ssl_handshake(self):
        # Based on code from test_ssl.py in the python stdlib
        try:
            self._handshake_reading = False
            self._handshake_writing = False
            self.socket.do_handshake()
        except ssl.SSLError as err:
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self._handshake_reading = True
                return
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self._handshake_writing = True
                return
            elif err.args[0] in (ssl.SSL_ERROR_EOF,
                                 ssl.SSL_ERROR_ZERO_RETURN):
                return self.close(exc_info=err)
            elif err.args[0] == ssl.SSL_ERROR_SSL:
                try:
                    peer = self.socket.getpeername()
                except Exception:
                    peer = '(not connected)'
                gen_log.warning("SSL Error on %s %s: %s",
                                self.socket.fileno(), peer, err)
                return self.close(exc_info=err)
            raise
        except socket.error as err:
            # Some port scans (e.g. nmap in -sT mode) have been known
            # to cause do_handshake to raise EBADF and ENOTCONN, so make
            # those errors quiet as well.
            # https://groups.google.com/forum/?fromgroups#!topic/python-tornado/ApucKJat1_0
            if (self._is_connreset(err) or
                    err.args[0] in (errno.EBADF, errno.ENOTCONN)):
                return self.close(exc_info=err)
            raise
        except AttributeError as err:
            # On Linux, if the connection was reset before the call to
            # wrap_socket, do_handshake will fail with an
            # AttributeError.
            return self.close(exc_info=err)
        else:
            self._ssl_accepting = False
            if not self._verify_cert(self.socket.getpeercert()):
                self.close()
                return
            self._run_ssl_connect_callback()

    def _run_ssl_connect_callback(self):
        if self._ssl_connect_callback is not None:
            callback = self._ssl_connect_callback
            self._ssl_connect_callback = None
            self._run_callback(callback)
        if self._ssl_connect_future is not None:
            future = self._ssl_connect_future
            self._ssl_connect_future = None
            future.set_result(self)

    def _verify_cert(self, peercert):
        """Returns True if peercert is valid according to the configured
        validation mode and hostname.

        The ssl handshake already tested the certificate for a valid
        CA signature; the only thing that remains is to check
        the hostname.
        """
        if isinstance(self._ssl_options, dict):
            verify_mode = self._ssl_options.get('cert_reqs', ssl.CERT_NONE)
        elif isinstance(self._ssl_options, ssl.SSLContext):
            verify_mode = self._ssl_options.verify_mode
        assert verify_mode in (ssl.CERT_NONE, ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL)
        if verify_mode == ssl.CERT_NONE or self._server_hostname is None:
            return True
        cert = self.socket.getpeercert()
        if cert is None and verify_mode == ssl.CERT_REQUIRED:
            gen_log.warning("No SSL certificate given")
            return False
        try:
            ssl.match_hostname(peercert, self._server_hostname)
        except ssl.CertificateError as e:
            gen_log.warning("Invalid SSL certificate: %s" % e)
            return False
        else:
            return True

    def _handle_read(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        super(SSLIOStream, self)._handle_read()

    def _handle_write(self):
        if self._ssl_accepting:
            self._do_ssl_handshake()
            return
        super(SSLIOStream, self)._handle_write()

    def connect(self, address, callback=None, server_hostname=None):
        self._server_hostname = server_hostname
        # Pass a dummy callback to super.connect(), which is slightly
        # more efficient than letting it return a Future we ignore.
        super(SSLIOStream, self).connect(address, callback=lambda: None)
        return self.wait_for_handshake(callback)

    def _handle_connect(self):
        # Call the superclass method to check for errors.
        super(SSLIOStream, self)._handle_connect()
        if self.closed():
            return
        # When the connection is complete, wrap the socket for SSL
        # traffic.  Note that we do this by overriding _handle_connect
        # instead of by passing a callback to super().connect because
        # user callbacks are enqueued asynchronously on the IOLoop,
        # but since _handle_events calls _handle_connect immediately
        # followed by _handle_write we need this to be synchronous.
        #
        # The IOLoop will get confused if we swap out self.socket while the
        # fd is registered, so remove it now and re-register after
        # wrap_socket().
        self.io_loop.remove_handler(self.socket)
        old_state = self._state
        self._state = None
        self.socket = ssl_wrap_socket(self.socket, self._ssl_options,
                                      server_hostname=self._server_hostname,
                                      do_handshake_on_connect=False)
        self._add_io_state(old_state)

    def wait_for_handshake(self, callback=None):
        """Wait for the initial SSL handshake to complete.

        If a ``callback`` is given, it will be called with no
        arguments once the handshake is complete; otherwise this
        method returns a `.Future` which will resolve to the
        stream itself after the handshake is complete.

        Once the handshake is complete, information such as
        the peer's certificate and NPN/ALPN selections may be
        accessed on ``self.socket``.

        This method is intended for use on server-side streams
        or after using `IOStream.start_tls`; it should not be used
        with `IOStream.connect` (which already waits for the
        handshake to complete). It may only be called once per stream.

        .. versionadded:: 4.2
        """
        if (self._ssl_connect_callback is not None or
                self._ssl_connect_future is not None):
            raise RuntimeError("Already waiting")
        if callback is not None:
            self._ssl_connect_callback = stack_context.wrap(callback)
            future = None
        else:
            future = self._ssl_connect_future = Future()
        if not self._ssl_accepting:
            self._run_ssl_connect_callback()
        return future

    def write_to_fd(self, data):
        try:
            return self.socket.send(data)
        except ssl.SSLError as e:
            if e.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                # In Python 3.5+, SSLSocket.send raises a WANT_WRITE error if
                # the socket is not writeable; we need to transform this into
                # an EWOULDBLOCK socket.error or a zero return value,
                # either of which will be recognized by the caller of this
                # method. Prior to Python 3.5, an unwriteable socket would
                # simply return 0 bytes written.
                return 0
            raise
        finally:
            # Avoid keeping to data, which can be a memoryview.
            # See https://github.com/tornadoweb/tornado/pull/2008
            del data

    def read_from_fd(self, buf):
        try:
            if self._ssl_accepting:
                # If the handshake hasn't finished yet, there can't be anything
                # to read (attempting to read may or may not raise an exception
                # depending on the SSL version)
                return None
            try:
                return self.socket.recv_into(buf)
            except ssl.SSLError as e:
                # SSLError is a subclass of socket.error, so this except
                # block must come first.
                if e.args[0] == ssl.SSL_ERROR_WANT_READ:
                    return None
                else:
                    raise
            except socket.error as e:
                if e.args[0] in _ERRNO_WOULDBLOCK:
                    return None
                else:
                    raise
        finally:
            buf = None

    def _is_connreset(self, e):
        if isinstance(e, ssl.SSLError) and e.args[0] == ssl.SSL_ERROR_EOF:
            return True
        return super(SSLIOStream, self)._is_connreset(e)


class PipeIOStream(BaseIOStream):
    """Pipe-based `IOStream` implementation.

    The constructor takes an integer file descriptor (such as one returned
    by `os.pipe`) rather than an open file object.  Pipes are generally
    one-way, so a `PipeIOStream` can be used for reading or writing but not
    both.
    """
    def __init__(self, fd, *args, **kwargs):
        self.fd = fd
        self._fio = io.FileIO(self.fd, "r+")
        _set_nonblocking(fd)
        super(PipeIOStream, self).__init__(*args, **kwargs)

    def fileno(self):
        return self.fd

    def close_fd(self):
        self._fio.close()

    def write_to_fd(self, data):
        try:
            return os.write(self.fd, data)
        finally:
            # Avoid keeping to data, which can be a memoryview.
            # See https://github.com/tornadoweb/tornado/pull/2008
            del data

    def read_from_fd(self, buf):
        try:
            return self._fio.readinto(buf)
        except (IOError, OSError) as e:
            if errno_from_exception(e) == errno.EBADF:
                # If the writing half of a pipe is closed, select will
                # report it as readable but reads will fail with EBADF.
                self.close(exc_info=e)
                return None
            else:
                raise
        finally:
            buf = None


def doctests():
    import doctest
    return doctest.DocTestSuite()
