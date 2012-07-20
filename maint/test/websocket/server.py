#!/usr/bin/env python

from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.util import bytes_type
from tornado.websocket import WebSocketHandler
from tornado.web import Application

define('port', default=9000)

class EchoHandler(WebSocketHandler):
    def on_message(self, message):
        self.write_message(message, binary=isinstance(message, bytes_type))

if __name__ == '__main__':
    parse_command_line()
    app = Application([
            ('/', EchoHandler),
            ])
    app.listen(options.port, address='127.0.0.1')
    IOLoop.instance().start()
