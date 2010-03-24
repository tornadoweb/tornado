#!/usr/bin/env python
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

import functools
import logging
import tornado.escape
import tornado.web

_log = logging.getLogger('tornado.websocket')

class WebSocketHandler(tornado.web.RequestHandler):
    """A request handler for HTML 5 Web Sockets.

    See http://www.w3.org/TR/2009/WD-websockets-20091222/ for details on the
    JavaScript interface. We implement the protocol as specified at
    http://tools.ietf.org/html/draft-hixie-thewebsocketprotocol-55.

    Here is an example Web Socket handler that echos back all received messages
    back to the client:

      class EchoWebSocket(websocket.WebSocketHandler):
          def open(self):
              self.receive_message(self.on_message)

          def on_message(self, message):
             self.write_message(u"You said: " + message)

    Web Sockets are not standard HTTP connections. The "handshake" is HTTP,
    but after the handshake, the protocol is message-based. Consequently,
    most of the Tornado HTTP facilities are not available in handlers of this
    type. The only communication methods available to you are send_message()
    and receive_message(). Likewise, your request handler class should
    implement open() method rather than get() or post().

    If you map the handler above to "/websocket" in your application, you can
    invoke it in JavaScript with:

      var ws = new WebSocket("ws://localhost:8888/websocket");
      ws.onopen = function() {
         ws.send("Hello, world");
      };
      ws.onmessage = function (evt) {
         alert(evt.data);
      };

    This script pops up an alert box that says "You said: Hello, world".
    """
    def __init__(self, application, request):
        tornado.web.RequestHandler.__init__(self, application, request)
        self.stream = request.connection.stream

    def _execute(self, transforms, *args, **kwargs):
        if self.request.headers.get("Upgrade") != "WebSocket" or \
           self.request.headers.get("Connection") != "Upgrade" or \
           not self.request.headers.get("Origin"):
            message = "Expected WebSocket headers"
            self.stream.write(
                "HTTP/1.1 403 Forbidden\r\nContent-Length: " +
                str(len(message)) + "\r\n\r\n" + message)
            return
        self.stream.write(
            "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
            "Upgrade: WebSocket\r\n"
            "Connection: Upgrade\r\n"
            "Server: TornadoServer/0.1\r\n"
            "WebSocket-Origin: " + self.request.headers["Origin"] + "\r\n"
            "WebSocket-Location: ws://" + self.request.host +
            self.request.path + "\r\n\r\n")
        self.async_callback(self.open)(*args, **kwargs)

    def write_message(self, message):
        """Sends the given message to the client of this Web Socket."""
        if isinstance(message, dict):
            message = tornado.escape.json_encode(message)
        if isinstance(message, unicode):
            message = message.encode("utf-8")
        assert isinstance(message, str)
        self.stream.write("\x00" + message + "\xff")

    def receive_message(self, callback):
        """Calls callback when the browser calls send() on this Web Socket."""
        callback = self.async_callback(callback)
        self.stream.read_bytes(
            1, functools.partial(self._on_frame_type, callback))

    def close(self):
        """Closes this Web Socket.

        The browser will receive the onclose event for the open web socket
        when this method is called.
        """
        self.stream.close()

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
            except Exception, e:
                _log.error("Uncaught exception in %s",
                              self.request.path, exc_info=True)
                self.stream.close()
        return wrapper

    def _on_frame_type(self, callback, byte):
        if ord(byte) & 0x80 == 0x80:
            raise Exception("Length-encoded format not yet supported")
        self.stream.read_until(
            "\xff", functools.partial(self._on_end_delimiter, callback))

    def _on_end_delimiter(self, callback, frame):
        callback(frame[:-1].decode("utf-8", "replace"))

    def _not_supported(self, *args, **kwargs):
        raise Exception("Method not supported for Web Sockets")

for method in ["write", "redirect", "set_header", "send_error", "set_cookie",
               "set_status", "flush", "finish"]:
    setattr(WebSocketHandler, method, WebSocketHandler._not_supported)
