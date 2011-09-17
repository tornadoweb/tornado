"""Server-side implementation of the WebSocket protocol.

`WebSockets <http://dev.w3.org/html5/websockets/>`_ allow for bidirectional
communication between the browser and server.

.. warning::

   The WebSocket protocol is still in development.  This module currently
   implements the "hixie-76" and "hybi-10" versions of the protocol.  
   See this `browser compatibility table 
   <http://en.wikipedia.org/wiki/WebSockets#Browser_support>`_ on Wikipedia.
"""
# Author: Jacob Kristhammar, 2010

import functools
import hashlib
import logging
import struct
import time
import base64
import tornado.escape
import tornado.web

from tornado.util import bytes_type, b

class WebSocketHandler(tornado.web.RequestHandler):
    """Subclass this class to create a basic WebSocket handler.

    Override on_message to handle incoming messages. You can also override
    open and on_close to handle opened and closed connections.

    See http://dev.w3.org/html5/websockets/ for details on the
    JavaScript interface. This implement the protocol as specified at
    http://tools.ietf.org/html/draft-ietf-hybi-thewebsocketprotocol-10
    The older protocol version specified at
    http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76.
    is also supported.

    Here is an example Web Socket handler that echos back all received messages
    back to the client::

      class EchoWebSocket(websocket.WebSocketHandler):
          def open(self):
              print "WebSocket opened"

          def on_message(self, message):
              self.write_message(u"You said: " + message)

          def on_close(self):
              print "WebSocket closed"

    Web Sockets are not standard HTTP connections. The "handshake" is HTTP,
    but after the handshake, the protocol is message-based. Consequently,
    most of the Tornado HTTP facilities are not available in handlers of this
    type. The only communication methods available to you are write_message()
    and close(). Likewise, your request handler class should
    implement open() method rather than get() or post().

    If you map the handler above to "/websocket" in your application, you can
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

        if (self.request.headers.get("Sec-WebSocket-Version") == "8" or
            self.request.headers.get("Sec-WebSocket-Version") == "7"):
            self.ws_connection = WebSocketProtocol8(self)
            self.ws_connection.accept_connection()
            
        elif self.request.headers.get("Sec-WebSocket-Version"):
            self.stream.write(tornado.escape.utf8(
                "HTTP/1.1 426 Upgrade Required\r\n"
                "Sec-WebSocket-Version: 8\r\n\r\n"))
            self.stream.close()
            
        else:
            self.ws_connection = WebSocketProtocol76(self)
            self.ws_connection.accept_connection()

    def write_message(self, message):
        """Sends the given message to the client of this Web Socket."""
        self.ws_connection.write_message(message)

    def open(self, *args, **kwargs):
        """Invoked when a new WebSocket is opened."""
        pass

    def on_message(self, message):
        """Handle incoming messages on the WebSocket

        This method must be overloaded
        """
        raise NotImplementedError

    def on_close(self):
        """Invoked when the WebSocket is closed."""
        pass

    def close(self):
        """Closes this Web Socket.

        Once the close handshake is successful the socket will be closed.
        """
        self.ws_connection.close()

    def async_callback(self, callback, *args, **kwargs):
        """Wrap callbacks with this if they are used on asynchronous requests.

        Catches exceptions properly and closes this WebSocket if an exception
        is uncaught.
        """
        return self.ws_connection.async_callback(callback, *args, **kwargs)

    def _not_supported(self, *args, **kwargs):
        raise Exception("Method not supported for Web Sockets")

    def on_connection_close(self):
        if self.ws_connection:
            self.ws_connection.client_terminated = True
            self.on_close()

    def _set_client_terminated(self, value):
        self.ws_connection.client_terminated = value

    client_terminated = property(lambda self: self.ws_connection.client_terminated,
                                 _set_client_terminated)


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
                logging.error("Uncaught exception in %s",
                              self.request.path, exc_info=True)
                self._abort()
        return wrapper

    def _abort(self):
        """Instantly aborts the WebSocket connection by closing the socket"""
        self.client_terminated = True
        self.stream.close()


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
            logging.debug("Malformed WebSocket request received")
            self._abort()
            return
        scheme = "wss" if self.request.protocol == "https" else "ws"
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
            "Sec-WebSocket-Location: %(scheme)s://%(host)s%(uri)s\r\n\r\n" % (dict(
                    version=tornado.version,
                    origin=self.request.headers["Origin"],
                    scheme=scheme,
                    host=self.request.host,
                    uri=self.request.uri))))
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
            logging.debug("Malformed key data in WebSocket request")
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
        headers = self.request.headers
        fields = ("Origin", "Host", "Sec-Websocket-Key1",
                  "Sec-Websocket-Key2")
        if headers.get("Upgrade", '').lower() != "websocket" or \
           headers.get("Connection", '').lower() != "upgrade" or \
           not all(map(lambda f: self.request.headers.get(f), fields)):
            raise ValueError("Missing/Invalid WebSocket headers")

    def _calculate_part(self, key):
        """Processes the key headers and calculates their key value.

        Raises ValueError when feed invalid key."""
        number = int(''.join(c for c in key if c.isdigit()))
        spaces = len([c for c in key if c.isspace()])
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
            self.stream.read_until(b("\xff"), self._on_end_delimiter)
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

    def write_message(self, message):
        """Sends the given message to the client of this Web Socket."""
        if isinstance(message, dict):
            message = tornado.escape.json_encode(message)
        if isinstance(message, unicode):
            message = message.encode("utf-8")
        assert isinstance(message, bytes_type)
        self.stream.write(b("\x00") + message + b("\xff"))

    def close(self):
        """Closes the WebSocket connection."""
        if self.client_terminated and self._waiting:
            tornado.ioloop.IOLoop.instance().remove_timeout(self._waiting)
            self.stream.close()
        else:
            self.stream.write("\xff\x00")
            self._waiting = tornado.ioloop.IOLoop.instance().add_timeout(
                                time.time() + 5, self._abort)


class WebSocketProtocol8(WebSocketProtocol):
    """Implementation of the WebSocket protocol, version 8 (draft version 10).

    Compare
    http://tools.ietf.org/html/draft-ietf-hybi-thewebsocketprotocol-10
    """
    def __init__(self, handler):
        WebSocketProtocol.__init__(self, handler)
        self._final_frame = False
        self._frame_opcode = None
        self._frame_mask = None
        self._frame_length = None
        self._fragmented_message_buffer = None
        self._fragmented_message_opcode = None
        self._started_closing_handshake = False

    def accept_connection(self):
        try:
            self._handle_websocket_headers()
            self._accept_connection()
        except ValueError:
            logging.debug("Malformed WebSocket request received")
            self._abort()
            return
    
    def _handle_websocket_headers(self):
        """Verifies all invariant- and required headers

        If a header is missing or have an incorrect value ValueError will be
        raised
        """
        headers = self.request.headers
        fields = ("Host", "Sec-Websocket-Key", "Sec-Websocket-Version")
        connection = map(lambda s: s.strip().lower(), headers.get("Connection", '').split(","))
        if (self.request.method != "GET" or
            headers.get("Upgrade", '').lower() != "websocket" or
            "upgrade" not in connection or
            not all(map(lambda f: self.request.headers.get(f), fields))):
            raise ValueError("Missing/Invalid WebSocket headers")

    def _challenge_response(self):
        sha1 = hashlib.sha1()
        sha1.update(tornado.escape.utf8(
                self.request.headers.get("Sec-Websocket-Key")))
        sha1.update(b("258EAFA5-E914-47DA-95CA-C5AB0DC85B11")) # Magic value
        return tornado.escape.native_str(base64.b64encode(sha1.digest()))

    def _accept_connection(self):
        self.stream.write(tornado.escape.utf8(
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n\r\n" % self._challenge_response()))

        self.async_callback(self.handler.open)(*self.handler.open_args, **self.handler.open_kwargs)
        self._receive_frame()

    def _write_frame(self, fin, opcode, data):
        if fin:
            finbit = 0x80
        else:
            finbit = 0
        frame = struct.pack("B", finbit | opcode)
        l = len(data)
        if l < 126:
            frame += struct.pack("B", l)
        elif l <= 0xFFFF:
            frame += struct.pack("!BH", 126, l)
        else:
            frame += struct.pack("!BQ", 127, l)
        frame += data
        self.stream.write(frame)

    def write_message(self, message, binary=False):
        """Sends the given message to the client of this Web Socket."""
        if isinstance(message, dict):
            message = tornado.escape.json_encode(message)
        if isinstance(message, unicode):
            message = message.encode("utf-8")
        assert isinstance(message, bytes_type)
        if not binary:
            opcode = 0x1
        else:
            opcode = 0x2
        self._write_frame(True, opcode, message)

    def _receive_frame(self):
        self.stream.read_bytes(2, self._on_frame_start)

    def _on_frame_start(self, data):
        header, payloadlen = struct.unpack("BB", data)
        self._final_frame = header & 0x80
        self._frame_opcode = header & 0xf
        if not (payloadlen & 0x80):
            # Unmasked frame -> abort connection
            self._abort()
        payloadlen = payloadlen & 0x7f
        if payloadlen < 126:
            self._frame_length = payloadlen
            self.stream.read_bytes(4, self._on_masking_key)
        elif payloadlen == 126:
            self.stream.read_bytes(2, self._on_frame_length_16)
        elif payloadlen == 127:
            self.stream.read_bytes(8, self._on_frame_length_64)

    def _on_frame_length_16(self, data):
        self._frame_length = struct.unpack("!H", data)[0];
        self.stream.read_bytes(4, self._on_masking_key);
        
    def _on_frame_length_64(self, data):
        self._frame_length = struct.unpack("!Q", data)[0];
        self.stream.read_bytes(4, self._on_masking_key);

    def _on_masking_key(self, data):
        self._frame_mask = bytearray(data)
        self.stream.read_bytes(self._frame_length, self._on_frame_data)

    def _on_frame_data(self, data):
        unmasked = bytearray(data)
        for i in xrange(len(data)):
            unmasked[i] = unmasked[i] ^ self._frame_mask[i % 4]

        if not self._final_frame:
            if self._fragmented_message_buffer:
                self._fragmented_message_buffer += unmasked
            else:
                self._fragmented_message_opcode = self._frame_opcode
                self._fragmented_message_buffer = unmasked
        else:
            if self._frame_opcode == 0:
                unmasked = self._fragmented_message_buffer + unmasked
                opcode = self._fragmented_message_opcode
                self._fragmented_message_buffer = None
            else:
                opcode = self._frame_opcode

            self._handle_message(opcode, bytes_type(unmasked))

        if not self.client_terminated:
            self._receive_frame()
        

    def _handle_message(self, opcode, data):
        if self.client_terminated: return
        
        if opcode == 0x1:
            # UTF-8 data
            self.async_callback(self.handler.on_message)(data.decode("utf-8", "replace"))
        elif opcode == 0x2:
            # Binary data
            self.async_callback(self.handler.on_message)(data)
        elif opcode == 0x8:
            # Close
            self.client_terminated = True
            if not self._started_closing_handshake:
                self._write_frame(True, 0x8, b(""))
            self.stream.close()
        elif opcode == 0x9:
            # Ping
            self._write_frame(True, 0xA, data)
        elif opcode == 0xA:
            # Pong
            pass
        else:
            self._abort()
        
    def close(self):
        """Closes the WebSocket connection."""
        self._write_frame(True, 0x8, b(""))
        self._started_closing_handshake = True
        self._waiting = tornado.ioloop.IOLoop.instance().add_timeout(time.time() + 5, self._abort)

