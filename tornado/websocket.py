"""Implementation of the WebSocket protocol.

`WebSockets <http://dev.w3.org/html5/websockets/>`_ allow for bidirectional
communication between the browser and server.

.. warning::

   The WebSocket protocol was recently finalized as `RFC 6455
   <http://tools.ietf.org/html/rfc6455>`_ and is not yet supported in
   all browsers.  Refer to http://caniuse.com/websockets for details
   on compatibility.  In addition, during development the protocol
   went through several incompatible versions, and some browsers only
   support older versions.  By default this module only supports the
   latest version of the protocol, but optional support for an older
   version (known as "draft 76" or "hixie-76") can be enabled by
   overriding `WebSocketHandler.allow_draft76` (see that method's
   documentation for caveats).
"""

from __future__ import absolute_import, division, print_function, with_statement
# Author: Jacob Kristhammar, 2010

import array
import base64
import collections
import functools
import hashlib
import os
import struct
import time
import tornado.escape
import tornado.web

from tornado.concurrent import TracebackFuture
from tornado.escape import utf8, native_str
from tornado import httpclient, httputil
from tornado.ioloop import IOLoop
from tornado.iostream import StreamClosedError
from tornado.log import gen_log, app_log
from tornado.netutil import Resolver
from tornado import simple_httpclient
from tornado.util import bytes_type, unicode_type

try:
    xrange  # py2
except NameError:
    xrange = range  # py3


class WebSocketError(Exception):
    pass


class WebSocketClosedError(WebSocketError):
    """Raised by operations on a closed connection.

    .. versionadded:: 3.2
    """
    pass


class WebSocketHandler(tornado.web.RequestHandler):
    """Subclass this class to create a basic WebSocket handler.

    Override `on_message` to handle incoming messages, and use
    `write_message` to send messages to the client. You can also
    override `open` and `on_close` to handle opened and closed
    connections.

    See http://dev.w3.org/html5/websockets/ for details on the
    JavaScript interface.  The protocol is specified at
    http://tools.ietf.org/html/rfc6455.

    Here is an example WebSocket handler that echos back all received messages
    back to the client::

      class EchoWebSocket(websocket.WebSocketHandler):
          def open(self):
              print "WebSocket opened"

          def on_message(self, message):
              self.write_message(u"You said: " + message)

          def on_close(self):
              print "WebSocket closed"

    WebSockets are not standard HTTP connections. The "handshake" is
    HTTP, but after the handshake, the protocol is
    message-based. Consequently, most of the Tornado HTTP facilities
    are not available in handlers of this type. The only communication
    methods available to you are `write_message()`, `ping()`, and
    `close()`. Likewise, your request handler class should implement
    `open()` method rather than ``get()`` or ``post()``.

    If you map the handler above to ``/websocket`` in your application, you can
    invoke it in JavaScript with::

      var ws = new WebSocket("ws://localhost:8888/websocket");
      ws.onopen = function() {
         ws.send("Hello, world");
      };
      ws.onmessage = function (evt) {
         alert(evt.data);
      };

    This script pops up an alert box that says "You said: Hello, world".
    """
    def __init__(self, application, request, **kwargs):
        tornado.web.RequestHandler.__init__(self, application, request,
                                            **kwargs)
        self.stream = request.connection.stream
        self.ws_connection = None

    def _execute(self, transforms, *args, **kwargs):
        self.open_args = args
        self.open_kwargs = kwargs

        # Websocket only supports GET method
        if self.request.method != 'GET':
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 405 Method Not Allowed\r\n\r\n"
            ))
            self.stream.close()
            return

        # Upgrade header should be present and should be equal to WebSocket
        if self.request.headers.get("Upgrade", "").lower() != 'websocket':
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 400 Bad Request\r\n\r\n"
                "Can \"Upgrade\" only to \"WebSocket\"."
            ))
            self.stream.close()
            return

        # Connection header should be upgrade. Some proxy servers/load balancers
        # might mess with it.
        headers = self.request.headers
        connection = map(lambda s: s.strip().lower(), headers.get("Connection", "").split(","))
        if 'upgrade' not in connection:
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 400 Bad Request\r\n\r\n"
                "\"Connection\" must be \"Upgrade\"."
            ))
            self.stream.close()
            return

        # The difference between version 8 and 13 is that in 8 the
        # client sends a "Sec-Websocket-Origin" header and in 13 it's
        # simply "Origin".
        if self.request.headers.get("Sec-WebSocket-Version") in ("7", "8", "13"):
            self.ws_connection = WebSocketProtocol13(self)
            self.ws_connection.accept_connection()
        elif (self.allow_draft76() and
              "Sec-WebSocket-Version" not in self.request.headers):
            self.ws_connection = WebSocketProtocol76(self)
            self.ws_connection.accept_connection()
        else:
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 426 Upgrade Required\r\n"
                "Sec-WebSocket-Version: 8\r\n\r\n"))
            self.stream.close()

    def write_message(self, message, binary=False):
        """Sends the given message to the client of this Web Socket.

        The message may be either a string or a dict (which will be
        encoded as json).  If the ``binary`` argument is false, the
        message will be sent as utf8; in binary mode any byte string
        is allowed.

        If the connection is already closed, raises `WebSocketClosedError`.

        .. versionchanged:: 3.2
           `WebSocketClosedError` was added (previously a closed connection
           would raise an `AttributeError`)
        """
        if self.ws_connection is None:
            raise WebSocketClosedError()
        if isinstance(message, dict):
            message = tornado.escape.json_encode(message)
        self.ws_connection.write_message(message, binary=binary)

    def select_subprotocol(self, subprotocols):
        """Invoked when a new WebSocket requests specific subprotocols.

        ``subprotocols`` is a list of strings identifying the
        subprotocols proposed by the client.  This method may be
        overridden to return one of those strings to select it, or
        ``None`` to not select a subprotocol.  Failure to select a
        subprotocol does not automatically abort the connection,
        although clients may close the connection if none of their
        proposed subprotocols was selected.
        """
        return None

    def open(self):
        """Invoked when a new WebSocket is opened.

        The arguments to `open` are extracted from the `tornado.web.URLSpec`
        regular expression, just like the arguments to
        `tornado.web.RequestHandler.get`.
        """
        pass

    def on_message(self, message):
        """Handle incoming messages on the WebSocket

        This method must be overridden.
        """
        raise NotImplementedError

    def ping(self, data):
        """Send ping frame to the remote end."""
        if self.ws_connection is None:
            raise WebSocketClosedError()
        self.ws_connection.write_ping(data)

    def on_pong(self, data):
        """Invoked when the response to a ping frame is received."""
        pass

    def on_close(self):
        """Invoked when the WebSocket is closed."""
        pass

    def close(self):
        """Closes this Web Socket.

        Once the close handshake is successful the socket will be closed.
        """
        if self.ws_connection:
            self.ws_connection.close()
            self.ws_connection = None

    def allow_draft76(self):
        """Override to enable support for the older "draft76" protocol.

        The draft76 version of the websocket protocol is disabled by
        default due to security concerns, but it can be enabled by
        overriding this method to return True.

        Connections using the draft76 protocol do not support the
        ``binary=True`` flag to `write_message`.

        Support for the draft76 protocol is deprecated and will be
        removed in a future version of Tornado.
        """
        return False

    def set_nodelay(self, value):
        """Set the no-delay flag for this stream.

        By default, small messages may be delayed and/or combined to minimize
        the number of packets sent.  This can sometimes cause 200-500ms delays
        due to the interaction between Nagle's algorithm and TCP delayed
        ACKs.  To reduce this delay (at the expense of possibly increasing
        bandwidth usage), call ``self.set_nodelay(True)`` once the websocket
        connection is established.

        See `.BaseIOStream.set_nodelay` for additional details.

        .. versionadded:: 3.1
        """
        self.stream.set_nodelay(value)

    def get_websocket_scheme(self):
        """Return the url scheme used for this request, either "ws" or "wss".

        This is normally decided by HTTPServer, but applications
        may wish to override this if they are using an SSL proxy
        that does not provide the X-Scheme header as understood
        by HTTPServer.

        Note that this is only used by the draft76 protocol.
        """
        return "wss" if self.request.protocol == "https" else "ws"

    def async_callback(self, callback, *args, **kwargs):
        """Obsolete - catches exceptions from the wrapped function.

        This function is normally unncecessary thanks to
        `tornado.stack_context`.
        """
        return self.ws_connection.async_callback(callback, *args, **kwargs)

    def _not_supported(self, *args, **kwargs):
        raise Exception("Method not supported for Web Sockets")

    def on_connection_close(self):
        if self.ws_connection:
            self.ws_connection.on_connection_close()
            self.ws_connection = None
            self.on_close()


for method in ["write", "redirect", "set_header", "send_error", "set_cookie",
               "set_status", "flush", "finish"]:
    setattr(WebSocketHandler, method, WebSocketHandler._not_supported)


class WebSocketProtocol(object):
    """Base class for WebSocket protocol versions.
    """
    def __init__(self, handler):
        self.handler = handler
        self.request = handler.request
        self.stream = handler.stream
        self.client_terminated = False
        self.server_terminated = False

    def async_callback(self, callback, *args, **kwargs):
        """Wrap callbacks with this if they are used on asynchronous requests.

        Catches exceptions properly and closes this WebSocket if an exception
        is uncaught.
        """
        if args or kwargs:
            callback = functools.partial(callback, *args, **kwargs)

        def wrapper(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except Exception:
                app_log.error("Uncaught exception in %s",
                              self.request.path, exc_info=True)
                self._abort()
        return wrapper

    def on_connection_close(self):
        self._abort()

    def _abort(self):
        """Instantly aborts the WebSocket connection by closing the socket"""
        self.client_terminated = True
        self.server_terminated = True
        self.stream.close()  # forcibly tear down the connection
        self.close()  # let the subclass cleanup


class WebSocketProtocol76(WebSocketProtocol):
    """Implementation of the WebSockets protocol, version hixie-76.

    This class provides basic functionality to process WebSockets requests as
    specified in
    http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76
    """
    def __init__(self, handler):
        WebSocketProtocol.__init__(self, handler)
        self.challenge = None
        self._waiting = None

    def accept_connection(self):
        try:
            self._handle_websocket_headers()
        except ValueError:
            gen_log.debug("Malformed WebSocket request received")
            self._abort()
            return

        scheme = self.handler.get_websocket_scheme()

        # draft76 only allows a single subprotocol
        subprotocol_header = ''
        subprotocol = self.request.headers.get("Sec-WebSocket-Protocol", None)
        if subprotocol:
            selected = self.handler.select_subprotocol([subprotocol])
            if selected:
                assert selected == subprotocol
                subprotocol_header = "Sec-WebSocket-Protocol: %s\r\n" % selected

        # Write the initial headers before attempting to read the challenge.
        # This is necessary when using proxies (such as HAProxy), which
        # need to see the Upgrade headers before passing through the
        # non-HTTP traffic that follows.
        self.stream.write(tornado.escape.utf8(
            "HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
            "Upgrade: WebSocket\r\n"
            "Connection: Upgrade\r\n"
            "Server: TornadoServer/%(version)s\r\n"
            "Sec-WebSocket-Origin: %(origin)s\r\n"
            "Sec-WebSocket-Location: %(scheme)s://%(host)s%(uri)s\r\n"
            "%(subprotocol)s"
            "\r\n" % (dict(
                version=tornado.version,
                origin=self.request.headers["Origin"],
                scheme=scheme,
                host=self.request.host,
                uri=self.request.uri,
                subprotocol=subprotocol_header))))
        self.stream.read_bytes(8, self._handle_challenge)

    def challenge_response(self, challenge):
        """Generates the challenge response that's needed in the handshake

        The challenge parameter should be the raw bytes as sent from the
        client.
        """
        key_1 = self.request.headers.get("Sec-Websocket-Key1")
        key_2 = self.request.headers.get("Sec-Websocket-Key2")
        try:
            part_1 = self._calculate_part(key_1)
            part_2 = self._calculate_part(key_2)
        except ValueError:
            raise ValueError("Invalid Keys/Challenge")
        return self._generate_challenge_response(part_1, part_2, challenge)

    def _handle_challenge(self, challenge):
        try:
            challenge_response = self.challenge_response(challenge)
        except ValueError:
            gen_log.debug("Malformed key data in WebSocket request")
            self._abort()
            return
        self._write_response(challenge_response)

    def _write_response(self, challenge):
        self.stream.write(challenge)
        self.async_callback(self.handler.open)(*self.handler.open_args, **self.handler.open_kwargs)
        self._receive_message()

    def _handle_websocket_headers(self):
        """Verifies all invariant- and required headers

        If a header is missing or have an incorrect value ValueError will be
        raised
        """
        fields = ("Origin", "Host", "Sec-Websocket-Key1",
                  "Sec-Websocket-Key2")
        if not all(map(lambda f: self.request.headers.get(f), fields)):
            raise ValueError("Missing/Invalid WebSocket headers")

    def _calculate_part(self, key):
        """Processes the key headers and calculates their key value.

        Raises ValueError when feed invalid key."""
        # pyflakes complains about variable reuse if both of these lines use 'c'
        number = int(''.join(c for c in key if c.isdigit()))
        spaces = len([c2 for c2 in key if c2.isspace()])
        try:
            key_number = number // spaces
        except (ValueError, ZeroDivisionError):
            raise ValueError
        return struct.pack(">I", key_number)

    def _generate_challenge_response(self, part_1, part_2, part_3):
        m = hashlib.md5()
        m.update(part_1)
        m.update(part_2)
        m.update(part_3)
        return m.digest()

    def _receive_message(self):
        self.stream.read_bytes(1, self._on_frame_type)

    def _on_frame_type(self, byte):
        frame_type = ord(byte)
        if frame_type == 0x00:
            self.stream.read_until(b"\xff", self._on_end_delimiter)
        elif frame_type == 0xff:
            self.stream.read_bytes(1, self._on_length_indicator)
        else:
            self._abort()

    def _on_end_delimiter(self, frame):
        if not self.client_terminated:
            self.async_callback(self.handler.on_message)(
                frame[:-1].decode("utf-8", "replace"))
        if not self.client_terminated:
            self._receive_message()

    def _on_length_indicator(self, byte):
        if ord(byte) != 0x00:
            self._abort()
            return
        self.client_terminated = True
        self.close()

    def write_message(self, message, binary=False):
        """Sends the given message to the client of this Web Socket."""
        if binary:
            raise ValueError(
                "Binary messages not supported by this version of websockets")
        if isinstance(message, unicode_type):
            message = message.encode("utf-8")
        assert isinstance(message, bytes_type)
        self.stream.write(b"\x00" + message + b"\xff")

    def write_ping(self, data):
        """Send ping frame."""
        raise ValueError("Ping messages not supported by this version of websockets")

    def close(self):
        """Closes the WebSocket connection."""
        if not self.server_terminated:
            if not self.stream.closed():
                self.stream.write("\xff\x00")
            self.server_terminated = True
        if self.client_terminated:
            if self._waiting is not None:
                self.stream.io_loop.remove_timeout(self._waiting)
            self._waiting = None
            self.stream.close()
        elif self._waiting is None:
            self._waiting = self.stream.io_loop.add_timeout(
                time.time() + 5, self._abort)


class WebSocketProtocol13(WebSocketProtocol):
    """Implementation of the WebSocket protocol from RFC 6455.

    This class supports versions 7 and 8 of the protocol in addition to the
    final version 13.
    """
    def __init__(self, handler, mask_outgoing=False):
        WebSocketProtocol.__init__(self, handler)
        self.mask_outgoing = mask_outgoing
        self._final_frame = False
        self._frame_opcode = None
        self._masked_frame = None
        self._frame_mask = None
        self._frame_length = None
        self._fragmented_message_buffer = None
        self._fragmented_message_opcode = None
        self._waiting = None

    def accept_connection(self):
        try:
            self._handle_websocket_headers()
            self._accept_connection()
        except ValueError:
            gen_log.debug("Malformed WebSocket request received", exc_info=True)
            self._abort()
            return

    def _handle_websocket_headers(self):
        """Verifies all invariant- and required headers

        If a header is missing or have an incorrect value ValueError will be
        raised
        """
        fields = ("Host", "Sec-Websocket-Key", "Sec-Websocket-Version")
        if not all(map(lambda f: self.request.headers.get(f), fields)):
            raise ValueError("Missing/Invalid WebSocket headers")

    @staticmethod
    def compute_accept_value(key):
        """Computes the value for the Sec-WebSocket-Accept header,
        given the value for Sec-WebSocket-Key.
        """
        sha1 = hashlib.sha1()
        sha1.update(utf8(key))
        sha1.update(b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11")  # Magic value
        return native_str(base64.b64encode(sha1.digest()))

    def _challenge_response(self):
        return WebSocketProtocol13.compute_accept_value(
            self.request.headers.get("Sec-Websocket-Key"))

    def _accept_connection(self):
        subprotocol_header = ''
        subprotocols = self.request.headers.get("Sec-WebSocket-Protocol", '')
        subprotocols = [s.strip() for s in subprotocols.split(',')]
        if subprotocols:
            selected = self.handler.select_subprotocol(subprotocols)
            if selected:
                assert selected in subprotocols
                subprotocol_header = "Sec-WebSocket-Protocol: %s\r\n" % selected

        self.stream.write(tornado.escape.utf8(
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n"
            "%s"
            "\r\n" % (self._challenge_response(), subprotocol_header)))

        self.async_callback(self.handler.open)(*self.handler.open_args, **self.handler.open_kwargs)
        self._receive_frame()

    def _write_frame(self, fin, opcode, data):
        if fin:
            finbit = 0x80
        else:
            finbit = 0
        frame = struct.pack("B", finbit | opcode)
        l = len(data)
        if self.mask_outgoing:
            mask_bit = 0x80
        else:
            mask_bit = 0
        if l < 126:
            frame += struct.pack("B", l | mask_bit)
        elif l <= 0xFFFF:
            frame += struct.pack("!BH", 126 | mask_bit, l)
        else:
            frame += struct.pack("!BQ", 127 | mask_bit, l)
        if self.mask_outgoing:
            mask = os.urandom(4)
            data = mask + _websocket_mask(mask, data)
        frame += data
        self.stream.write(frame)

    def write_message(self, message, binary=False):
        """Sends the given message to the client of this Web Socket."""
        if binary:
            opcode = 0x2
        else:
            opcode = 0x1
        message = tornado.escape.utf8(message)
        assert isinstance(message, bytes_type)
        try:
            self._write_frame(True, opcode, message)
        except StreamClosedError:
            self._abort()

    def write_ping(self, data):
        """Send ping frame."""
        assert isinstance(data, bytes_type)
        self._write_frame(True, 0x9, data)

    def _receive_frame(self):
        try:
            self.stream.read_bytes(2, self._on_frame_start)
        except StreamClosedError:
            self._abort()

    def _on_frame_start(self, data):
        header, payloadlen = struct.unpack("BB", data)
        self._final_frame = header & 0x80
        reserved_bits = header & 0x70
        self._frame_opcode = header & 0xf
        self._frame_opcode_is_control = self._frame_opcode & 0x8
        if reserved_bits:
            # client is using as-yet-undefined extensions; abort
            self._abort()
            return
        self._masked_frame = bool(payloadlen & 0x80)
        payloadlen = payloadlen & 0x7f
        if self._frame_opcode_is_control and payloadlen >= 126:
            # control frames must have payload < 126
            self._abort()
            return
        try:
            if payloadlen < 126:
                self._frame_length = payloadlen
                if self._masked_frame:
                    self.stream.read_bytes(4, self._on_masking_key)
                else:
                    self.stream.read_bytes(self._frame_length, self._on_frame_data)
            elif payloadlen == 126:
                self.stream.read_bytes(2, self._on_frame_length_16)
            elif payloadlen == 127:
                self.stream.read_bytes(8, self._on_frame_length_64)
        except StreamClosedError:
            self._abort()

    def _on_frame_length_16(self, data):
        self._frame_length = struct.unpack("!H", data)[0]
        try:
            if self._masked_frame:
                self.stream.read_bytes(4, self._on_masking_key)
            else:
                self.stream.read_bytes(self._frame_length, self._on_frame_data)
        except StreamClosedError:
            self._abort()

    def _on_frame_length_64(self, data):
        self._frame_length = struct.unpack("!Q", data)[0]
        try:
            if self._masked_frame:
                self.stream.read_bytes(4, self._on_masking_key)
            else:
                self.stream.read_bytes(self._frame_length, self._on_frame_data)
        except StreamClosedError:
            self._abort()

    def _on_masking_key(self, data):
        self._frame_mask = data
        try:
            self.stream.read_bytes(self._frame_length, self._on_masked_frame_data)
        except StreamClosedError:
            self._abort()

    def _on_masked_frame_data(self, data):
        self._on_frame_data(_websocket_mask(self._frame_mask, data))

    def _on_frame_data(self, data):
        if self._frame_opcode_is_control:
            # control frames may be interleaved with a series of fragmented
            # data frames, so control frames must not interact with
            # self._fragmented_*
            if not self._final_frame:
                # control frames must not be fragmented
                self._abort()
                return
            opcode = self._frame_opcode
        elif self._frame_opcode == 0:  # continuation frame
            if self._fragmented_message_buffer is None:
                # nothing to continue
                self._abort()
                return
            self._fragmented_message_buffer += data
            if self._final_frame:
                opcode = self._fragmented_message_opcode
                data = self._fragmented_message_buffer
                self._fragmented_message_buffer = None
        else:  # start of new data message
            if self._fragmented_message_buffer is not None:
                # can't start new message until the old one is finished
                self._abort()
                return
            if self._final_frame:
                opcode = self._frame_opcode
            else:
                self._fragmented_message_opcode = self._frame_opcode
                self._fragmented_message_buffer = data

        if self._final_frame:
            self._handle_message(opcode, data)

        if not self.client_terminated:
            self._receive_frame()

    def _handle_message(self, opcode, data):
        if self.client_terminated:
            return

        if opcode == 0x1:
            # UTF-8 data
            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError:
                self._abort()
                return
            self.async_callback(self.handler.on_message)(decoded)
        elif opcode == 0x2:
            # Binary data
            self.async_callback(self.handler.on_message)(data)
        elif opcode == 0x8:
            # Close
            self.client_terminated = True
            self.close()
        elif opcode == 0x9:
            # Ping
            self._write_frame(True, 0xA, data)
        elif opcode == 0xA:
            # Pong
            self.async_callback(self.handler.on_pong)(data)
        else:
            self._abort()

    def close(self):
        """Closes the WebSocket connection."""
        if not self.server_terminated:
            if not self.stream.closed():
                self._write_frame(True, 0x8, b"")
            self.server_terminated = True
        if self.client_terminated:
            if self._waiting is not None:
                self.stream.io_loop.remove_timeout(self._waiting)
                self._waiting = None
            self.stream.close()
        elif self._waiting is None:
            # Give the client a few seconds to complete a clean shutdown,
            # otherwise just close the connection.
            self._waiting = self.stream.io_loop.add_timeout(
                self.stream.io_loop.time() + 5, self._abort)


class WebSocketClientConnection(simple_httpclient._HTTPConnection):
    """WebSocket client connection.

    This class should not be instantiated directly; use the
    `websocket_connect` function instead.
    """
    def __init__(self, io_loop, request):
        self.connect_future = TracebackFuture()
        self.read_future = None
        self.read_queue = collections.deque()
        self.key = base64.b64encode(os.urandom(16))

        scheme, sep, rest = request.url.partition(':')
        scheme = {'ws': 'http', 'wss': 'https'}[scheme]
        request.url = scheme + sep + rest
        request.headers.update({
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
            'Sec-WebSocket-Key': self.key,
            'Sec-WebSocket-Version': '13',
        })

        self.resolver = Resolver(io_loop=io_loop)
        super(WebSocketClientConnection, self).__init__(
            io_loop, None, request, lambda: None, self._on_http_response,
            104857600, self.resolver)

    def close(self):
        """Closes the websocket connection.

        .. versionadded:: 3.2
        """
        if self.protocol is not None:
            self.protocol.close()
            self.protocol = None

    def _on_close(self):
        self.on_message(None)
        self.resolver.close()
        super(WebSocketClientConnection, self)._on_close()

    def _on_http_response(self, response):
        if not self.connect_future.done():
            if response.error:
                self.connect_future.set_exception(response.error)
            else:
                self.connect_future.set_exception(WebSocketError(
                    "Non-websocket response"))

    def _handle_1xx(self, code):
        assert code == 101
        assert self.headers['Upgrade'].lower() == 'websocket'
        assert self.headers['Connection'].lower() == 'upgrade'
        accept = WebSocketProtocol13.compute_accept_value(self.key)
        assert self.headers['Sec-Websocket-Accept'] == accept

        self.protocol = WebSocketProtocol13(self, mask_outgoing=True)
        self.protocol._receive_frame()

        if self._timeout is not None:
            self.io_loop.remove_timeout(self._timeout)
            self._timeout = None

        self.connect_future.set_result(self)

    def write_message(self, message, binary=False):
        """Sends a message to the WebSocket server."""
        self.protocol.write_message(message, binary)

    def read_message(self, callback=None):
        """Reads a message from the WebSocket server.

        Returns a future whose result is the message, or None
        if the connection is closed.  If a callback argument
        is given it will be called with the future when it is
        ready.
        """
        assert self.read_future is None
        future = TracebackFuture()
        if self.read_queue:
            future.set_result(self.read_queue.popleft())
        else:
            self.read_future = future
        if callback is not None:
            self.io_loop.add_future(future, callback)
        return future

    def on_message(self, message):
        if self.read_future is not None:
            self.read_future.set_result(message)
            self.read_future = None
        else:
            self.read_queue.append(message)

    def on_pong(self, data):
        pass


def websocket_connect(url, io_loop=None, callback=None, connect_timeout=None):
    """Client-side websocket support.

    Takes a url and returns a Future whose result is a
    `WebSocketClientConnection`.

    .. versionchanged:: 3.2
       Also accepts ``HTTPRequest`` objects in place of urls.
    """
    if io_loop is None:
        io_loop = IOLoop.current()
    if isinstance(url, httpclient.HTTPRequest):
        assert connect_timeout is None
        request = url
        # Copy and convert the headers dict/object (see comments in
        # AsyncHTTPClient.fetch)
        request.headers = httputil.HTTPHeaders(request.headers)
    else:
        request = httpclient.HTTPRequest(url, connect_timeout=connect_timeout)
    request = httpclient._RequestProxy(
        request, httpclient.HTTPRequest._DEFAULTS)
    conn = WebSocketClientConnection(io_loop, request)
    if callback is not None:
        io_loop.add_future(conn.connect_future, callback)
    return conn.connect_future


def _websocket_mask_python(mask, data):
    """Websocket masking function.

    `mask` is a `bytes` object of length 4; `data` is a `bytes` object of any length.
    Returns a `bytes` object of the same length as `data` with the mask applied
    as specified in section 5.3 of RFC 6455.

    This pure-python implementation may be replaced by an optimized version when available.
    """
    mask = array.array("B", mask)
    unmasked = array.array("B", data)
    for i in xrange(len(data)):
        unmasked[i] = unmasked[i] ^ mask[i % 4]
    if hasattr(unmasked, 'tobytes'):
        # tostring was deprecated in py32.  It hasn't been removed,
        # but since we turn on deprecation warnings in our tests
        # we need to use the right one.
        return unmasked.tobytes()
    else:
        return unmasked.tostring()

if (os.environ.get('TORNADO_NO_EXTENSION') or
    os.environ.get('TORNADO_EXTENSION') == '0'):
    # These environment variables exist to make it easier to do performance
    # comparisons; they are not guaranteed to remain supported in the future.
    _websocket_mask = _websocket_mask_python
else:
    try:
        from tornado.speedups import websocket_mask as _websocket_mask
    except ImportError:
        if os.environ.get('TORNADO_EXTENSION') == '1':
            raise
        _websocket_mask = _websocket_mask_python
