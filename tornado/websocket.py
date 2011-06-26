"""Server-side implementation of the WebSocket protocol.

`WebSockets <http://dev.w3.org/html5/websockets/>`_ allow for bidirectional
communication between the browser and server.

.. warning::

   The WebSocket protocol is still in development.  This module currently
   implements the "draft76" version of the protocol, which is supported
   only by Chrome and Safari.  See this `browser compatibility table 
   <http://en.wikipedia.org/wiki/WebSockets#Browser_support>`_ on Wikipedia.
"""
# Author: Jacob Kristhammar, 2010

import functools
import hashlib
import logging
import struct
import time
import tornado.escape
import tornado.web

from tornado.util import bytes_type, b

class WebSocketHandler(tornado.web.RequestHandler):
    """Subclass this class to create a basic WebSocket handler.

    Override on_message to handle incoming messages. You can also override
    open and on_close to handle opened and closed connections.

    See http://www.w3.org/TR/2009/WD-websockets-20091222/ for details on the
    JavaScript interface. This implement the protocol as specified at
    http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76.

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
        self.client_terminated = False
        self._waiting = None

    def _execute(self, transforms, *args, **kwargs):
        self.open_args = args
        self.open_kwargs = kwargs
        try:
            self.ws_request = WebSocketRequest(self.request)
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
            "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
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

    def _handle_challenge(self, challenge):
        try:
            challenge_response = self.ws_request.challenge_response(challenge)
        except ValueError:
            logging.debug("Malformed key data in WebSocket request")
            self._abort()
            return
        self._write_response(challenge_response)

    def _write_response(self, challenge):
        self.stream.write(challenge)
        self.async_callback(self.open)(*self.open_args, **self.open_kwargs)
        self._receive_message()

    def write_message(self, message):
        """Sends the given message to the client of this Web Socket."""
        if isinstance(message, dict):
            message = tornado.escape.json_encode(message)
        if isinstance(message, unicode):
            message = message.encode("utf-8")
        assert isinstance(message, bytes_type)
        self.stream.write(b("\x00") + message + b("\xff"))

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
        if self.client_terminated and self._waiting:
            tornado.ioloop.IOLoop.instance().remove_timeout(self._waiting)
            self.stream.close()
        else:
            self.stream.write("\xff\x00")
            self._waiting = tornado.ioloop.IOLoop.instance().add_timeout(
                                time.time() + 5, self._abort)

    def async_callback(self, callback, *args, **kwargs):
        """Wrap callbacks with this if they are used on asynchronous requests.

        Catches exceptions properly and closes this Web Socket if an exception
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
            self.async_callback(self.on_message)(
                    frame[:-1].decode("utf-8", "replace"))
        if not self.client_terminated:
            self._receive_message()

    def _on_length_indicator(self, byte):
        if ord(byte) != 0x00:
            self._abort()
            return
        self.client_terminated = True
        self.close()

    def on_connection_close(self):
        self.client_terminated = True
        self.on_close()

    def _not_supported(self, *args, **kwargs):
        raise Exception("Method not supported for Web Sockets")


for method in ["write", "redirect", "set_header", "send_error", "set_cookie",
               "set_status", "flush", "finish"]:
    setattr(WebSocketHandler, method, WebSocketHandler._not_supported)


class WebSocketRequest(object):
    """A single WebSocket request.

    This class provides basic functionality to process WebSockets requests as
    specified in
    http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-76
    """
    def __init__(self, request):
        self.request = request
        self.challenge = None
        self._handle_websocket_headers()

    def challenge_response(self, challenge):
        """Generates the challange response that's needed in the handshake

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
